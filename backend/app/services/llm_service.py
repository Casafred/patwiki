"""统一的 OpenAI-compatible LLM 调用边界。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_FLASH_MODEL = "deepseek-v4-flash"
_DEEPSEEK_MODEL_ALIASES = {
    "v4flash": DEEPSEEK_FLASH_MODEL,
    "v4-flash": DEEPSEEK_FLASH_MODEL,
    "deepseek-v4flash": DEEPSEEK_FLASH_MODEL,
}


class LLMServiceError(RuntimeError):
    """可直接展示给任务监控和设置页的 LLM 错误。"""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    temperature: float = 0.0
    max_tokens: int = 2000
    thinking_mode: str = "disabled"
    reasoning_effort: str = "low"


def normalize_base_url(value: str | None) -> str:
    base_url = (value or "https://api.openai.com/v1").strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
    return base_url.rstrip("/")


def normalize_model(provider: str, model: str | None) -> str:
    """Resolve documented friendly aliases without replacing custom models."""
    normalized = (model or "").strip()
    if provider.strip().lower() == "deepseek":
        return _DEEPSEEK_MODEL_ALIASES.get(normalized.lower(), normalized)
    return normalized


def load_llm_config(overrides: dict[str, Any] | None = None) -> LLMConfig:
    """读取当前运行配置；overrides 只用于未保存的设置页测试。"""
    from app.api.settings import get_app_settings

    app_settings = get_app_settings()
    llm = app_settings.llm
    overrides = overrides or {}
    provider = str(overrides.get("provider") or overrides.get("llm_provider") or llm.llm_provider).strip().lower()
    api_key = overrides.get("api_key") or overrides.get("llm_api_key") or llm.llm_api_key
    base_url = overrides.get("base_url") or overrides.get("llm_base_url") or llm.llm_base_url
    model = overrides.get("model") or overrides.get("llm_model") or llm.llm_model
    temperature = overrides.get("temperature", overrides.get("llm_temperature", llm.llm_temperature))
    max_tokens = overrides.get("max_tokens", overrides.get("llm_max_tokens", llm.llm_max_tokens))
    thinking_mode = overrides.get("thinking_mode", overrides.get("llm_thinking_mode", llm.llm_thinking_mode))
    reasoning_effort = overrides.get("reasoning_effort", overrides.get("llm_reasoning_effort", llm.llm_reasoning_effort))
    if not api_key:
        raise LLMServiceError("未配置 LLM API Key，请先在设置页保存 API Key")
    if not model:
        raise LLMServiceError("未配置 LLM 模型名称")
    if str(thinking_mode) not in {"enabled", "disabled"}:
        raise LLMServiceError("思考模式必须为 enabled 或 disabled")
    if str(reasoning_effort) not in {"low", "high", "max"}:
        raise LLMServiceError("推理强度必须为 low、high 或 max")
    normalized_provider = provider or "openai"
    return LLMConfig(
        provider=normalized_provider,
        api_key=str(api_key),
        model=normalize_model(normalized_provider, str(model)),
        base_url=normalize_base_url(str(base_url)),
        temperature=min(2.0, max(0.0, float(temperature or 0))),
        max_tokens=max(1, int(max_tokens or 1)),
        thinking_mode=str(thinking_mode),
        reasoning_effort=str(reasoning_effort),
    )


def _build_payload(prompt: str, config: LLMConfig, *, max_tokens: int | None,
                   response_format: dict[str, str] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": config.temperature,
        "max_tokens": max_tokens if max_tokens is not None else config.max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    if config.provider == "deepseek":
        # V4 defaults to thinking. The explicit setting keeps field extraction
        # deterministic and avoids paying for an unused reasoning trace.
        payload["thinking"] = {"type": config.thinking_mode}
        if config.thinking_mode == "enabled":
            payload["reasoning_effort"] = config.reasoning_effort
    return payload


def _content_to_text(content: Any) -> str:
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    return str(content or "")


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        try:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                return min(30.0, max(0.0, float(retry_after)))
        except ValueError:
            pass
    return min(8.0, 0.75 * (2 ** attempt))


def chat_completion(prompt: str, config: LLMConfig | None = None, *,
                    max_tokens: int | None = None, retries: int = 2,
                    response_format: dict[str, str] | None = None) -> dict[str, Any]:
    """执行 Chat Completions；返回文本及模型、推理、终止和用量元数据。"""
    config = config or load_llm_config()
    url = f"{config.base_url}/chat/completions"
    payload = _build_payload(prompt, config, max_tokens=max_tokens, response_format=response_format)
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(180.0, connect=20.0)
    for attempt in range(retries + 1):
        response: httpx.Response | None = None
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                detail = response.text[:500].replace("\n", " ")
                error = LLMServiceError(
                    f"LLM HTTP {response.status_code}（{config.model}）：{detail}",
                    retryable=response.status_code == 429 or response.status_code >= 500,
                )
                if error.retryable and attempt < retries:
                    time.sleep(_retry_delay(response, attempt))
                    continue
                raise error
            try:
                body = response.json()
                choice = body["choices"][0]
                message = choice["message"]
                content = _content_to_text(message.get("content"))
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise LLMServiceError(f"LLM 返回格式无法解析：{response.text[:500]}") from exc
            if not content.strip():
                raise LLMServiceError("LLM 返回内容为空")
            return {
                "content": content,
                "model": body.get("model") or config.model,
                "reasoning_content": _content_to_text(message.get("reasoning_content")),
                "finish_reason": choice.get("finish_reason"),
                "usage": body.get("usage"),
                "raw": body,
            }
        except LLMServiceError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt < retries:
                time.sleep(_retry_delay(None, attempt))
                continue
            raise LLMServiceError(
                f"LLM 网络请求失败（已重试 {retries} 次，{config.base_url}）：{exc}",
                retryable=True,
            ) from exc
        except Exception as exc:
            raise LLMServiceError(f"LLM 调用失败：{exc}") from exc
    raise LLMServiceError("LLM 调用失败：未知错误")


class UnifiedLLM:
    """保留现有 engine.invoke 接口，同时使用统一 HTTP 实现。"""

    def __init__(self, config: LLMConfig):
        self.config = config

    def invoke(self, prompt: str, *, response_format: dict[str, str] | None = None):
        result = chat_completion(prompt, self.config, response_format=response_format)

        class Response:
            content = result["content"]
            response_model = result["model"]
            reasoning_content = result["reasoning_content"]
            finish_reason = result["finish_reason"]
            usage = result["usage"]

        return Response()
