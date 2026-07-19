import json
import hashlib
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.orm import Session

from app.models import (
    Patent, AITask, AIFieldValue, CustomField, AIFieldValue,
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

    def _build_prompt(self, patent: Patent, field_def: CustomField) -> str:
        ai_config = field_def.ai_config or {}
        template = ai_config.get("prompt_template", "")

        if template:
            text = template
        else:
            text = f"""请分析以下专利信息，完成任务：{field_def.description or field_def.name}

专利标题：{patent.title}
专利摘要：{patent.abstract or ''}
申请人：{patent.applicant or ''}
发明人：{patent.inventor or ''}

请直接给出结果，不要多余的解释。"""

        return text

    def _calculate_input_hash(self, patent: Patent, field_def: CustomField) -> str:
        content = f"{patent.title}|{patent.abstract or ''}|{field_def.key}|{field_def.ai_config or ''}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def _get_cached_value(self, patent_id: int, field_key: str, input_hash: str) -> Optional[AIFieldValue]:
        return self.db.query(AIFieldValue).filter(
            AIFieldValue.patent_id == patent_id,
            AIFieldValue.field_key == field_key,
            AIFieldValue.input_hash == input_hash,
            AIFieldValue.is_overridden == False,
        ).first()

    def process_single(self, patent: Patent, field_def: CustomField, force: bool = False) -> Optional[str]:
        input_hash = self._calculate_input_hash(patent, field_def)

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

            current = patent.ai_fields or {}
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
