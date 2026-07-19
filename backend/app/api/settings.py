"""系统设置 API：LLM API key 等配置的读写。
配置持久化到数据目录的 settings.json，不进数据库（便于打包后用户直接编辑）。
"""
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.config import settings
from app.api.deps import get_pagination_params

router = APIRouter()

# 配置文件路径
SETTINGS_FILE = settings.DATA_DIR / "settings.json"

# 敏感字段：返回时做脱敏
SENSITIVE_KEYS = {"llm_api_key", "embedding_api_key"}


class LLMSettings(BaseModel):
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2000
    # Embedding（向量检索，暂留接口）
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str = ""


class AppSettings(BaseModel):
    """应用设置：LLM + 通用配置"""
    llm: LLMSettings = LLMSettings()
    # 是否启用 AI 功能
    ai_enabled: bool = False
    # 批量处理并发数
    ai_batch_concurrency: int = 3
    # 缓存命中是否跳过 API 调用
    ai_use_cache: bool = True


def _load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(data: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _mask_sensitive(data: dict) -> dict:
    """脱敏敏感字段"""
    masked = {}
    for k, v in data.items():
        if k in SENSITIVE_KEYS and v:
            masked[k] = v[:4] + "****" + v[-4:] if len(v) > 8 else "****"
        else:
            masked[k] = v
    return masked


def get_app_settings() -> AppSettings:
    """供其他模块（AI 引擎）调用：读取当前配置"""
    data = _load_settings()
    llm_data = data.get("llm", {})
    # 环境变量优先级更高（开发模式 .env）
    if settings.LLM_API_KEY and not llm_data.get("llm_api_key"):
        llm_data["llm_api_key"] = settings.LLM_API_KEY
    if settings.LLM_MODEL and not llm_data.get("llm_model"):
        llm_data["llm_model"] = settings.LLM_MODEL
    if settings.LLM_BASE_URL and not llm_data.get("llm_base_url"):
        llm_data["llm_base_url"] = settings.LLM_BASE_URL
    llm = LLMSettings(**{k: v for k, v in llm_data.items() if k in LLMSettings.model_fields})
    ai_enabled = data.get("ai_enabled", bool(llm.llm_api_key))
    return AppSettings(
        llm=llm,
        ai_enabled=ai_enabled,
        ai_batch_concurrency=data.get("ai_batch_concurrency", 3),
        ai_use_cache=data.get("ai_use_cache", True),
    )


def apply_llm_to_settings(app_settings: AppSettings) -> None:
    """把 LLM 配置同步到 app.config.settings，供 AI 引擎使用"""
    import app.config as cfg
    cfg.settings.LLM_PROVIDER = app_settings.llm.llm_provider
    cfg.settings.LLM_API_KEY = app_settings.llm.llm_api_key
    cfg.settings.LLM_MODEL = app_settings.llm.llm_model
    cfg.settings.LLM_BASE_URL = app_settings.llm.llm_base_url


@router.get("/settings")
async def get_settings():
    """读取设置（敏感字段脱敏）"""
    data = _load_settings()
    llm_data = data.get("llm", {})
    if settings.LLM_API_KEY and not llm_data.get("llm_api_key"):
        llm_data["llm_api_key"] = settings.LLM_API_KEY
    if settings.LLM_MODEL and not llm_data.get("llm_model"):
        llm_data["llm_model"] = settings.LLM_MODEL
    if settings.LLM_BASE_URL and not llm_data.get("llm_base_url"):
        llm_data["llm_base_url"] = settings.LLM_BASE_URL
    masked_llm = _mask_sensitive(llm_data)
    return {
        "llm": masked_llm,
        "ai_enabled": data.get("ai_enabled", bool(llm_data.get("llm_api_key"))),
        "ai_batch_concurrency": data.get("ai_batch_concurrency", 3),
        "ai_use_cache": data.get("ai_use_cache", True),
        # 标识 API key 是否已配置
        "has_api_key": bool(llm_data.get("llm_api_key")),
    }


@router.put("/settings")
async def update_settings(payload: dict):
    """更新设置。
    若字段值为空字符串或未提供，则保留原值（避免脱敏后的 **** 覆盖真实值）。
    """
    current = _load_settings()

    # 处理 llm 子配置
    new_llm = payload.get("llm", {})
    current_llm = current.get("llm", {})

    # 环境变量兜底
    if settings.LLM_API_KEY and not current_llm.get("llm_api_key"):
        current_llm["llm_api_key"] = settings.LLM_API_KEY

    for k, v in new_llm.items():
        # 跳过脱敏字段（值为 **** 开头说明是前端回显，不覆盖）
        if k in SENSITIVE_KEYS and isinstance(v, str) and ("****" in v or v == ""):
            continue
        current_llm[k] = v

    current["llm"] = current_llm

    if "ai_enabled" in payload:
        current["ai_enabled"] = payload["ai_enabled"]
    else:
        current["ai_enabled"] = bool(current_llm.get("llm_api_key"))

    if "ai_batch_concurrency" in payload:
        current["ai_batch_concurrency"] = payload["ai_batch_concurrency"]
    if "ai_use_cache" in payload:
        current["ai_use_cache"] = payload["ai_use_cache"]

    _save_settings(current)

    # 同步到运行时
    app_settings = get_app_settings()
    apply_llm_to_settings(app_settings)

    return {"success": True, "message": "设置已保存"}


@router.post("/settings/test-llm")
async def test_llm_connection(payload: dict):
    """测试 LLM 连接是否可用"""
    api_key = payload.get("api_key", "")
    base_url = payload.get("base_url", "https://api.openai.com/v1")
    model = payload.get("model", "gpt-4o-mini")

    # 若传的是脱敏值，用已存的
    if not api_key or "****" in api_key:
        app_settings = get_app_settings()
        api_key = app_settings.llm.llm_api_key

    if not api_key:
        return {"success": False, "message": "未配置 API Key"}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            # OpenAI 兼容接口：发送一个极小的请求
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
            )
            if resp.status_code == 200:
                return {"success": True, "message": f"连接成功，模型: {model}"}
            else:
                detail = resp.text[:200]
                return {"success": False, "message": f"HTTP {resp.status_code}: {detail}"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}"}
