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
        # 优先从 settings.json 读取最新配置（用户可能通过设置页修改过）
        try:
            from app.api.settings import get_app_settings, apply_llm_to_settings
            app_settings = get_app_settings()
            apply_llm_to_settings(app_settings)
        except Exception:
            pass

        if not settings.LLM_API_KEY:
            raise ValueError("LLM API key not configured. 请在设置页配置 LLM API Key。")

        try:
            from langchain_openai import ChatOpenAI
            kwargs = {
                "model": settings.LLM_MODEL,
                "api_key": settings.LLM_API_KEY,
                "temperature": 0.0,
            }
            if settings.LLM_BASE_URL:
                kwargs["base_url"] = settings.LLM_BASE_URL
            return ChatOpenAI(**kwargs)
        except ImportError:
            # 兜底：直接用 openai SDK
            try:
                from openai import OpenAI
                class _OpenAICompat:
                    def __init__(self):
                        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL or None)
                        self._model = settings.LLM_MODEL
                    def invoke(self, prompt: str):
                        resp = self._client.chat.completions.create(
                            model=self._model,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.0,
                        )
                        class _R:
                            def __init__(self, content):
                                self.content = content
                        return _R(resp.choices[0].message.content or "")
                return _OpenAICompat()
            except ImportError:
                raise ImportError(" neither langchain-openai nor openai installed，请安装其中一个")

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

    def process_single(self, patent: Patent, field_def: CustomField, force: bool = False) -> Optional[Any]:
        input_hash = self._calculate_input_hash(patent, field_def)

        current_value = self.db.query(AIFieldValue).filter(
            AIFieldValue.patent_id == patent.id,
            AIFieldValue.field_key == field_def.key,
        ).first()

        # 人工值是当前生效值。普通批处理不能覆盖人工判断，只有强制重算才允许刷新。
        if not force and current_value and current_value.is_overridden:
            return self._decode_override_value(current_value.overridden_value)

        if not force:
            cached = self._get_cached_value(patent.id, field_def.key, input_hash)
            if cached:
                return cached.value

        llm = self._get_llm()
        prompt = self._build_prompt(patent, field_def)

        import time
        start = time.time()

        try:
            response = llm.invoke(prompt)
            result = response.content.strip()

            duration = int((time.time() - start) * 1000)

            ai_value = self.db.query(AIFieldValue).filter(
                AIFieldValue.patent_id == patent.id,
                AIFieldValue.field_key == field_def.key,
            ).first()

            if not ai_value:
                ai_value = AIFieldValue(
                    patent_id=patent.id,
                    field_key=field_def.key,
                    model_name=settings.LLM_MODEL,
                    temperature=0.0,
                )
                self.db.add(ai_value)

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
            return result

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
            task.errors = {"error": f"Field '{field_key}' not found"}
            task.completed_at = datetime.now()
            self.db.commit()
            return

        task.status = "processing"
        self.db.commit()

        success = 0
        failed = 0
        errors = []

        for idx, patent_id in enumerate(patent_ids):
            patent = self.db.query(Patent).filter(Patent.id == patent_id).first()
            if not patent:
                failed += 1
                continue

            try:
                self.process_single(patent, field_def, force=force)
                success += 1
            except Exception as e:
                failed += 1
                errors.append({"patent_id": patent_id, "error": str(e)})

            task.processed_items = idx + 1
            task.success_count = success
            task.failed_count = failed
            task.errors = errors if errors else None

            if (idx + 1) % 10 == 0:
                self.db.commit()

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
        return {}

    def quick_analyze_single(self, patent: Patent, input_fields: list[str],
                             user_prompt: str, extraction_targets: list[dict]) -> dict:
        """对单条专利执行快速分析，返回 {field_key: value} 映射。

        extraction_targets: [{"name": "技术问题", "target_field_key": "cf_xxx", ...}, ...]
        """
        extraction_names = [t["name"] for t in extraction_targets]
        prompt = self._build_quick_prompt(patent, input_fields, user_prompt, extraction_names)

        llm = self._get_llm()
        response = llm.invoke(prompt)
        raw = response.content.strip()
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
        return results

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

        for idx, patent_id in enumerate(patent_ids):
            patent = self.db.query(Patent).filter(Patent.id == patent_id).first()
            if not patent:
                failed += 1
                continue
            try:
                self.quick_analyze_single(patent, input_fields, user_prompt, extraction_targets)
                success += 1
            except Exception as e:
                failed += 1
                errors.append({"patent_id": patent_id, "error": str(e)})

            task.processed_items = idx + 1
            task.success_count = success
            task.failed_count = failed
            task.errors = errors if errors else None
            if (idx + 1) % 5 == 0:
                self.db.commit()

        task.status = "completed" if failed == 0 else ("completed_with_errors" if success > 0 else "failed")
        task.completed_at = datetime.now()
        self.db.commit()
