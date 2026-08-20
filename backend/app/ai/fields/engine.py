import json
import hashlib
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.orm import Session

from app.models import (
    Patent, AITask, AIFieldValue, CustomField,
)
from app.config import settings


class AIFieldEngine:
    def __init__(self, db: Session):
        self.db = db

    def _get_llm(self):
        """获取统一 LLM 客户端；设置页测试和后台任务使用同一配置边界。"""
        from app.services.llm_service import UnifiedLLM, load_llm_config

        config = load_llm_config()
        return UnifiedLLM(config), config.model

    def _resolve_field_value(self, patent: Patent, key: str) -> str:
        """根据字段key从patent中解析出值，支持系统字段、custom_fields.xxx、ai_fields.xxx"""
        if key.startswith("custom_fields."):
            ck = key[len("custom_fields."):]
            return str((patent.custom_fields or {}).get(ck, "") or "")
        if key.startswith("ai_fields."):
            ak = key[len("ai_fields."):]
            return str((patent.ai_fields or {}).get(ak, "") or "")
        # 系统字段
        val = getattr(patent, key, None)
        if val is None:
            return ""
        if hasattr(val, "isoformat"):  # date/datetime
            return val.isoformat()
        return str(val)

    def _build_prompt(self, patent: Patent, field_def: CustomField) -> str:
        ai_config = field_def.ai_config or {}
        template = ai_config.get("prompt_template", "")

        if template:
            import re
            # 支持任意 {field_key} 变量替换，包括 {title}/{abstract}/{applicant}/{custom_fields.xxx}/{ai_fields.xxx} 等
            def _replace(m):
                k = m.group(1).strip()
                v = self._resolve_field_value(patent, k)
                return v if v else ""
            text = re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}", _replace, template)
        else:
            text = f"""请分析以下专利信息，完成任务：{field_def.description or field_def.name}

专利标题：{patent.title}
专利摘要：{patent.abstract or ''}
申请人：{patent.applicant or ''}
发明人：{patent.inventor or ''}

请直接给出结果，不要多余的解释。"""

        return text

    def _calculate_input_hash(self, patent: Patent, field_def: CustomField) -> str:
        ai_config = field_def.ai_config or {}
        template = ai_config.get("prompt_template", "")
        # 收集 prompt 中引用的所有字段值参与 hash，保证引用值变化时重新计算
        import re
        keys = set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}", template))
        parts = [field_def.key, template]
        for k in sorted(keys):
            parts.append(f"{k}={self._resolve_field_value(patent, k)}")
        content = "|".join(parts)
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def _get_cached_value(self, patent_id: int, field_key: str, input_hash: str) -> Optional[AIFieldValue]:
        return self.db.query(AIFieldValue).filter(
            AIFieldValue.patent_id == patent_id,
            AIFieldValue.field_key == field_key,
            AIFieldValue.input_hash == input_hash,
            AIFieldValue.is_overridden == False,
        ).first()

    def _decode_override_value(self, value: Optional[str]) -> Any:
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value

    def process_single(self, patent: Patent, field_def: CustomField, force: bool = False) -> tuple[Optional[Any], Optional[dict]]:
        """处理单条专利的 AI 字段。

        返回 (result, call_info)，其中 call_info 包含 prompt/response/model（命中缓存时为 None）。
        """
        input_hash = self._calculate_input_hash(patent, field_def)

        current_value = self.db.query(AIFieldValue).filter(
            AIFieldValue.patent_id == patent.id,
            AIFieldValue.field_key == field_def.key,
        ).first()

        # 人工值是当前生效值。普通批处理不能覆盖人工判断，只有强制重算才允许刷新。
        if not force and current_value and current_value.is_overridden:
            return self._decode_override_value(current_value.overridden_value), None

        if not force:
            cached = self._get_cached_value(patent.id, field_def.key, input_hash)
            if cached:
                return cached.value, None

        llm, actual_model = self._get_llm()
        prompt = self._build_prompt(patent, field_def)

        import time
        start = time.time()

        try:
            response = llm.invoke(prompt)
            result = response.content.strip()
            # 优先取 API 返回的 response_model（可能解析别名→具体快照）
            response_model = getattr(response, "response_model", None) or actual_model

            duration = int((time.time() - start) * 1000)

            ai_value = self.db.query(AIFieldValue).filter(
                AIFieldValue.patent_id == patent.id,
                AIFieldValue.field_key == field_def.key,
            ).first()

            if not ai_value:
                ai_value = AIFieldValue(
                    patent_id=patent.id,
                    field_key=field_def.key,
                    model_name=response_model,
                    temperature=0.0,
                )
                self.db.add(ai_value)
            else:
                ai_value.model_name = response_model

            ai_value.value = result
            ai_value.input_hash = input_hash
            ai_value.duration_ms = duration
            ai_value.prompt_version = "1.0"
            ai_value.is_overridden = False
            ai_value.overridden_value = None
            ai_value.overridden_at = None

            current = dict(patent.ai_fields or {})
            current[field_def.key] = result
            patent.ai_fields = current

            self.db.commit()
            call_info = {
                "patent_id": patent.id,
                "prompt": prompt,
                "response": result,
                "model": response_model,
            }
            return result, call_info

        except Exception as e:
            self.db.rollback()
            raise e

    def process_batch(self, task_id: int, patent_ids: list[int], field_key: str, force: bool = False):
        task = self.db.query(AITask).filter(AITask.id == task_id).first()
        if not task:
            return

        field_def = self.db.query(CustomField).filter(CustomField.key == field_key).first()
        if not field_def:
            task.status = "failed"
            task.errors = [{"stage": "prepare", "error": f"Field '{field_key}' not found"}]
            task.failed_count = task.total_items or 0
            task.processed_items = task.total_items or 0
            task.completed_at = datetime.now()
            self.db.commit()
            return

        task.status = "processing"
        task.started_at = datetime.now()
        self.db.commit()

        success = 0
        failed = 0
        errors = []
        request_samples = []  # 最多保留前 5 条 prompt 样本
        response_samples = []  # 最多保留前 5 条 response 样本
        recorded_model = None
        max_samples = 5

        for idx, patent_id in enumerate(patent_ids):
            patent = self.db.query(Patent).filter(Patent.id == patent_id).first()
            if not patent:
                failed += 1
                errors.append({"patent_id": patent_id, "stage": "execute", "error": "Patent not found"})
            else:
                try:
                    _, call_info = self.process_single(patent, field_def, force=force)
                    success += 1
                    # 记录请求/返回样本（仅前若干条）
                    if call_info and len(request_samples) < max_samples:
                        request_samples.append({
                            "patent_id": call_info["patent_id"],
                            "prompt": call_info["prompt"][:4000],  # 截断避免超大
                        })
                        response_samples.append({
                            "patent_id": call_info["patent_id"],
                            "response": call_info["response"][:4000],
                            "model": call_info["model"],
                        })
                        if recorded_model is None:
                            recorded_model = call_info["model"]
                except Exception as e:
                    failed += 1
                    errors.append({"patent_id": patent_id, "stage": "execute", "error": str(e)})

            task.processed_items = idx + 1
            task.success_count = success
            task.failed_count = failed
            task.errors = errors if errors else None

            if (idx + 1) % 10 == 0:
                self.db.commit()

        # P0-15：用实际调用时使用的模型名覆盖任务记录（修复记录与实际不一致的问题）
        if recorded_model:
            task.model_name = recorded_model
        task.request_content = request_samples if request_samples else None
        task.response_content = response_samples if response_samples else None
        task.status = "completed" if failed == 0 else ("completed_with_errors" if success > 0 else "failed")
        task.completed_at = datetime.now()
        self.db.commit()

    # ------------------------------------------------------------------
    # AI 快速分析（ad-hoc）：用户自定义输入列、提示词、抽取目标
    # ------------------------------------------------------------------

    def _build_quick_prompt(self, patent: Patent, input_fields: list[str],
                           user_prompt: str, extraction_names: list[str]) -> str:
        """构建快速分析的完整 prompt：用户自定义内容 + 输入列上下文 + JSON 输出指令。"""
        import re

        # 1) 替换用户 prompt 中的 {field_key} 变量
        def _replace(m):
            k = m.group(1).strip()
            v = self._resolve_field_value(patent, k)
            return v if v else ""

        text = re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}", _replace, user_prompt)

        # 2) 追加输入列上下文（如果用户 prompt 中没有用变量引用某些列，仍把选中的列内容附上）
        context_parts = []
        for field_key in input_fields:
            val = self._resolve_field_value(patent, field_key)
            if val:
                context_parts.append(f"【{field_key}】{val}")
        if context_parts:
            text += "\n\n" + "\n".join(context_parts)

        # 3) 追加 JSON 输出指令
        fields_desc = "\n".join(f'- "{name}"' for name in extraction_names)
        text += f"""

请以 JSON 对象格式返回分析结果，包含以下字段：
{fields_desc}

只返回 JSON 对象，不要包含其他内容或 markdown 代码块标记。"""
        return text

    def _parse_llm_json(self, raw: str) -> dict:
        """从 LLM 响应中解析 JSON 对象，兼容 markdown 代码块包裹。"""
        text = raw.strip()
        # 去除 ```json ... ``` 包裹
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首行 ```json 和末行 ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            pass
        # 兜底：正则提取第一个 {...} 块
        import re
        m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, TypeError):
                pass
        raise ValueError("LLM 返回内容无法解析为 JSON 对象")

    def quick_analyze_single(self, patent: Patent, input_fields: list[str],
                             user_prompt: str, extraction_targets: list[dict]) -> tuple[dict, Optional[dict]]:
        """对单条专利执行快速分析，返回 ({field_key: value}, call_info)。

        extraction_targets: [{"name": "技术问题", "target_field_key": "cf_xxx", ...}, ...]
        """
        extraction_names = [t["name"] for t in extraction_targets]
        prompt = self._build_quick_prompt(patent, input_fields, user_prompt, extraction_names)

        llm, actual_model = self._get_llm()
        response = llm.invoke(prompt)
        raw = response.content.strip()
        response_model = getattr(response, "response_model", None) or actual_model
        parsed = self._parse_llm_json(raw)

        results = {}
        for target in extraction_targets:
            name = target["name"]
            value = parsed.get(name, "")
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            field_key = target.get("target_field_key")
            if not field_key:
                continue

            # 写入：AI 字段 → ai_fields JSON；普通自定义字段 → custom_fields JSON
            field_def = self.db.query(CustomField).filter(CustomField.key == field_key).first()
            if field_def and field_def.field_type == "ai_field":
                current = dict(patent.ai_fields or {})
                current[field_key] = str(value)
                patent.ai_fields = current
            else:
                current = dict(patent.custom_fields or {})
                current[field_key] = str(value)
                patent.custom_fields = current
            results[field_key] = str(value)

        self.db.commit()
        call_info = {
            "patent_id": patent.id,
            "prompt": prompt,
            "response": raw,
            "model": response_model,
        }
        return results, call_info

    def quick_analyze_batch(self, task_id: int, patent_ids: list[int],
                            input_fields: list[str], user_prompt: str,
                            extraction_targets: list[dict]):
        """批量快速分析：创建新字段 → 逐条处理 → 更新任务进度。"""
        task = self.db.query(AITask).filter(AITask.id == task_id).first()
        if not task:
            return

        task.status = "processing"
        task.started_at = datetime.now()
        self.db.commit()

        success = 0
        failed = 0
        errors = []
        request_samples = []
        response_samples = []
        recorded_model = None
        max_samples = 5

        for idx, patent_id in enumerate(patent_ids):
            patent = self.db.query(Patent).filter(Patent.id == patent_id).first()
            if not patent:
                failed += 1
                errors.append({"patent_id": patent_id, "stage": "execute", "error": "Patent not found"})
            else:
                try:
                    _, call_info = self.quick_analyze_single(patent, input_fields, user_prompt, extraction_targets)
                    success += 1
                    if call_info and len(request_samples) < max_samples:
                        request_samples.append({
                            "patent_id": call_info["patent_id"],
                            "prompt": call_info["prompt"][:4000],
                        })
                        response_samples.append({
                            "patent_id": call_info["patent_id"],
                            "response": call_info["response"][:4000],
                            "model": call_info["model"],
                        })
                        if recorded_model is None:
                            recorded_model = call_info["model"]
                except Exception as e:
                    failed += 1
                    errors.append({"patent_id": patent_id, "stage": "execute", "error": str(e)})

            task.processed_items = idx + 1
            task.success_count = success
            task.failed_count = failed
            task.errors = errors if errors else None
            if (idx + 1) % 5 == 0:
                self.db.commit()

        # P0-15：用实际调用时使用的模型名覆盖任务记录
        if recorded_model:
            task.model_name = recorded_model
        task.request_content = request_samples if request_samples else None
        task.response_content = response_samples if response_samples else None
        task.status = "completed" if failed == 0 else ("completed_with_errors" if success > 0 else "failed")
        task.completed_at = datetime.now()
        self.db.commit()
