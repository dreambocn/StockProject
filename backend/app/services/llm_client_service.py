import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.core.settings import Settings, get_settings


def build_openai_base_url(base_url: str) -> str:
    normalized_base_url = base_url.rstrip("/")
    if normalized_base_url.endswith("/v1"):
        return normalized_base_url
    return f"{normalized_base_url}/v1"


def _build_responses_input(
    prompt: str,
    *,
    system_instruction: str | None = None,
) -> list[dict[str, object]]:
    # 使用 Responses API 的结构化 content 形式，避免网关把纯字符串输入解析到错误分支。
    input_items: list[dict[str, object]] = []
    if system_instruction and system_instruction.strip():
        input_items.append(
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_instruction.strip(),
                    }
                ],
            }
        )

    input_items.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": prompt,
                }
            ],
        }
    )
    return input_items


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


@dataclass
class LlmTextResult:
    text: str
    used_web_search: bool
    web_search_status: str
    web_sources: list[dict[str, object]]


def build_openai_client(settings: Settings | None = None):
    resolved_settings = settings or get_settings()
    from openai import OpenAI

    return OpenAI(
        base_url=build_openai_base_url(resolved_settings.llm_base_url),
        api_key=resolved_settings.llm_api_key,
    )


def _build_create_kwargs(
    *,
    prompt: str,
    system_instruction: str | None,
    resolved_settings: Settings,
    model: str | None,
    reasoning_effort: str | None,
    max_output_tokens: int,
    use_web_search: bool,
) -> dict[str, object]:
    request_kwargs: dict[str, object] = {
        "model": model or resolved_settings.llm_model,
        "input": _build_responses_input(
            prompt,
            system_instruction=system_instruction,
        ),
        "store": False,
        "reasoning": {
            "effort": reasoning_effort or resolved_settings.llm_reasoning_effort
        },
        "max_output_tokens": max_output_tokens,
    }
    if use_web_search and resolved_settings.llm_web_search_enabled:
        # 联网增强默认关闭；只有显式开启且全局允许时才尝试挂载 web search tool。
        request_kwargs["tools"] = [{"type": "web_search_preview"}]
    return request_kwargs


def _is_web_search_unsupported(error: Exception) -> bool:
    message = str(error).lower()
    return "web_search" in message or "tool" in message or "unsupported" in message


def _extract_web_sources(_: object) -> list[dict[str, object]]:
    # 当前兼容网关未稳定暴露标准 citation 结构时，先返回空列表；
    # 后续若网关补齐 annotations，可在这里统一解析。
    return []


async def generate_llm_result(
    prompt: str,
    *,
    client: Any | None = None,
    settings: Settings | None = None,
    system_instruction: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int = 512,
    use_web_search: bool = False,
) -> LlmTextResult:
    resolved_settings = settings or get_settings()
    if not resolved_settings.llm_api_key.strip():
        raise RuntimeError("llm api key not configured")

    if resolved_settings.llm_wire_api != "responses":
        raise RuntimeError(
            f"unsupported llm wire api: {resolved_settings.llm_wire_api}"
        )

    resolved_client = client or build_openai_client(resolved_settings)
    request_kwargs = _build_create_kwargs(
        prompt=prompt,
        system_instruction=system_instruction,
        resolved_settings=resolved_settings,
        model=model,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        use_web_search=use_web_search,
    )
    web_search_requested = bool(
        use_web_search and resolved_settings.llm_web_search_enabled
    )
    try:
        response = await asyncio.to_thread(
            resolved_client.responses.create,
            **request_kwargs,
        )
        return LlmTextResult(
            text=_extract_output_text(response),
            used_web_search=web_search_requested,
            web_search_status="used" if web_search_requested else "disabled",
            web_sources=_extract_web_sources(response),
        )
    except Exception as exc:
        if not web_search_requested or not _is_web_search_unsupported(exc):
            raise

        fallback_kwargs = _build_create_kwargs(
            prompt=prompt,
            system_instruction=system_instruction,
            resolved_settings=resolved_settings,
            model=model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            use_web_search=False,
        )
        response = await asyncio.to_thread(
            resolved_client.responses.create,
            **fallback_kwargs,
        )
        return LlmTextResult(
            text=_extract_output_text(response),
            used_web_search=False,
            web_search_status="unsupported",
            web_sources=[],
        )


async def generate_llm_text(
    prompt: str,
    *,
    client: Any | None = None,
    settings: Settings | None = None,
    system_instruction: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int = 512,
    use_web_search: bool = False,
) -> str:
    result = await generate_llm_result(
        prompt,
        client=client,
        settings=settings,
        system_instruction=system_instruction,
        model=model,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        use_web_search=use_web_search,
    )
    return result.text


async def stream_llm_text(
    prompt: str,
    *,
    client: Any | None = None,
    settings: Settings | None = None,
    system_instruction: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int = 512,
    use_web_search: bool = False,
) -> AsyncIterator[str]:
    resolved_settings = settings or get_settings()
    resolved_client = client or build_openai_client(resolved_settings)

    if not resolved_settings.llm_stream_enabled:
        yield await generate_llm_text(
            prompt,
            client=resolved_client,
            settings=resolved_settings,
            system_instruction=system_instruction,
            model=model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            use_web_search=use_web_search,
        )
        return

    request_kwargs = _build_create_kwargs(
        prompt=prompt,
        system_instruction=system_instruction,
        resolved_settings=resolved_settings,
        model=model,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        use_web_search=use_web_search,
    )

    queue: asyncio.Queue[tuple[str, object | None]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _run_stream() -> None:
        try:
            with resolved_client.responses.stream(**request_kwargs) as stream:
                for event in stream:
                    event_type = str(getattr(event, "type", "") or "")
                    if event_type == "response.output_text.delta":
                        delta = str(getattr(event, "delta", "") or "")
                        if delta:
                            loop.call_soon_threadsafe(
                                queue.put_nowait, ("delta", delta)
                            )
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    worker = asyncio.create_task(asyncio.to_thread(_run_stream))
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "delta":
                yield str(payload or "")
                continue
            if kind == "error":
                raise payload if isinstance(payload, Exception) else RuntimeError(
                    "llm stream failed"
                )
            break
    finally:
        await worker
