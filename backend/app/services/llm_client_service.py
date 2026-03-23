import asyncio
from typing import Any

from app.core.settings import Settings, get_settings


def build_openai_base_url(base_url: str) -> str:
    normalized_base_url = base_url.rstrip("/")
    if normalized_base_url.endswith("/v1"):
        return normalized_base_url
    return f"{normalized_base_url}/v1"


def _build_responses_input(prompt: str) -> list[dict[str, object]]:
    # 使用 Responses API 的结构化 content 形式，避免网关把纯字符串输入解析到错误分支。
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": prompt,
                }
            ],
        }
    ]


def _extract_output_text(response: object) -> str:
    output_text = str(getattr(response, "output_text", "") or "").strip()
    if output_text:
        return output_text

    output_items = getattr(response, "output", None) or []
    for item in output_items:
        content_items = getattr(item, "content", None) or []
        for content in content_items:
            text_value = getattr(content, "text", None)
            if text_value:
                normalized_text = str(text_value).strip()
                if normalized_text:
                    return normalized_text

    raise RuntimeError("llm response missing output text")


def build_openai_client(settings: Settings | None = None):
    resolved_settings = settings or get_settings()
    from openai import OpenAI

    return OpenAI(
        base_url=build_openai_base_url(resolved_settings.llm_base_url),
        api_key=resolved_settings.llm_api_key,
    )


async def generate_llm_text(
    prompt: str,
    *,
    client: Any | None = None,
    settings: Settings | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int = 512,
) -> str:
    resolved_settings = settings or get_settings()
    if not resolved_settings.llm_api_key.strip():
        raise RuntimeError("llm api key not configured")

    if resolved_settings.llm_wire_api != "responses":
        raise RuntimeError(
            f"unsupported llm wire api: {resolved_settings.llm_wire_api}"
        )

    resolved_client = client or build_openai_client(resolved_settings)
    response = await asyncio.to_thread(
        resolved_client.responses.create,
        model=model or resolved_settings.llm_model,
        input=_build_responses_input(prompt),
        store=False,
        reasoning={
            "effort": reasoning_effort or resolved_settings.llm_reasoning_effort
        },
        max_output_tokens=max_output_tokens,
    )
    return _extract_output_text(response)
