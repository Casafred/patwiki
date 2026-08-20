"""统一的 OpenAI-compatible LLM 调用边界。

设置页测试连接和数据库 AI 任务必须经过同一套配置解析、URL 规范化、超时
和错误转换逻辑，避免“测试成功、实际任务 NetworkError”这种不可定位的分叉。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


class LLMServiceError(RuntimeError):
    """可直接展示给任务监控和设置页的 LLM 错误。"""


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    temperature: float = 0.0
    max_tokens: int = 2000


def normalize_base_url(value: str | None) -> str:
    base_url = (value or "https://api.openai.com/v1").strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
    return base_url.rstrip("/")


def load_llm_config(overrides: dict[str, Any] | None = None) -> LLMConfig:
    """读取当前运行配置；overrides 只用于未保存的设置页测试。"""
    from app.api.settings import get_app_settings

    app_settings = get_app_settings()
    llm = app_settings.llm
    overrides = overrides or {}
    api_key = overrides.get("api_key") or overrides.get("llm_api_key") or llm.llm_api_key
    base_url = overrides.get("base_url") or overrides.get("llm_base_url") or llm.llm_base_url
    model = overrides.get("model") or overrides.get("llm_model") or llm.llm_model
    temperature = overrides.get("temperature", overrides.get("llm_temperature", llm.llm_temperature))
    max_tokens = overrides.get("max_tokens", overrides.get("llm_max_tokens", llm.llm_max_tokens))
    if not api_key:
        raise LLMServiceError("未配置 LLM API Key，请先在设置页保存 API Key")
    if not model:
        raise LLMServiceError("未配置 LLM 模型名称")
    return LLMConfig(
        provider=llm.llm_provider,
        api_key=str(api_key),
        model=str(model),
        base_url=normalize_base_url(str(base_url)),
        temperature=float(temperature or 0),
        max_tokens=max(1, int(max_tokens or 1)),
    )


def chat_completion(
    prompt: str,
    config: LLMConfig | None = None,
    *,
    max_tokens: int | None = None,
    retries: int = 2,
) -> dict[str, Any]:
    """执行一次兼容 Chat Completions 调用，并返回统一结构。"""
    config = config or load_llm_config()
    url = f"{config.base_url}/chat/completions"
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": config.temperature,
        "max_tokens": max_tokens if max_tokens is not None else config.max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(90.0, connect=20.0)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                detail = response.text[:500].replace("\n", " ")
                raise LLMServiceError(f"LLM HTTP {response.status_code}（{config.model}）：{detail}")
            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise LLMServiceError(f"LLM 返回格式无法解析：{response.text[:500]}") from exc
            if isinstance(content, list):
                content = "".join(
                    str(item.get("text", "")) if isinstance(item, dict) else str(item)
                    for item in content
                )
            if not str(content or "").strip():
                raise LLMServiceError("LLM 返回内容为空")
            return {
                "content": str(content or ""),
                "model": body.get("model") or config.model,
                "raw": body,
            }
        except LLMServiceError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise LLMServiceError(
                f"LLM 网络请求失败（已重试 {retries} 次，{config.base_url}）：{exc}"
            ) from exc
        except Exception as exc:
            raise LLMServiceError(f"LLM 调用失败：{exc}") from exc
    raise LLMServiceError(f"LLM 调用失败：{last_error or 'unknown error'}")


class UnifiedLLM:
    """保留现有 engine.invoke 接口，同时使用统一 HTTP 实现。"""

    def __init__(self, config: LLMConfig):
        self.config = config

    def invoke(self, prompt: str):
        result = chat_completion(prompt, self.config)

        class Response:
            content = result["content"]
            response_model = result["model"]

        return Response()
