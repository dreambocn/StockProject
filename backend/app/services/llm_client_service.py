import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.core.settings import Settings, get_settings


def build_openai_base_url(base_url: str) -> str:
    normalized_base_url = base_url.rstrip("/")
    # 统一保证以 /v1 结尾，避免配置了根域时调用错误路径。
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
    # 优先读取 output_text，兼容不同 SDK 的响应字段形态。
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


def _iter_output_text_contents(response: object) -> list[object]:
    # 收集可能包含引用标注的输出内容，为 web_sources 提取做准备。
    output_items = getattr(response, "output", None) or []
    contents: list[object] = []
    for item in output_items:
        content_items = getattr(item, "content", None) or []
        for content in content_items:
            content_type = str(getattr(content, "type", "") or "")
            if content_type == "output_text" or getattr(content, "annotations", None):
                contents.append(content)
    return contents


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
        # base_url 允许自定义网关，避免直连被防火墙阻断。
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
    # 只要异常信息包含 web_search/tool/unsupported 即视为不支持。
    message = str(error).lower()
    return "web_search" in message or "tool" in message or "unsupported" in message


def _extract_web_sources(response: object) -> list[dict[str, object]]:
    extracted_sources: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for content in _iter_output_text_contents(response):
        annotations = getattr(content, "annotations", None) or []
        content_text = str(getattr(content, "text", "") or "")
        for annotation in annotations:
            annotation_type = str(getattr(annotation, "type", "") or "")
            if annotation_type != "url_citation":
                continue
            url = str(getattr(annotation, "url", "") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            snippet: str | None = None
            start_index = getattr(annotation, "start_index", None)
            end_index = getattr(annotation, "end_index", None)
            if isinstance(start_index, int) and isinstance(end_index, int):
                if 0 <= start_index < end_index <= len(content_text):
                    snippet_text = content_text[start_index:end_index].strip()
                    if snippet_text:
                        snippet = snippet_text

            extracted_sources.append(
                {
                    "title": getattr(annotation, "title", None),
                    "url": url,
                    "source": getattr(annotation, "source", None),
                    "published_at": getattr(annotation, "published_at", None),
                    "snippet": snippet,
                }
            )

    return extracted_sources


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
        # web_search 不支持时降级为普通请求，保持主流程可用。

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


async def generate_streamed_llm_result(
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
    resolved_client = client or build_openai_client(resolved_settings)

    if not resolved_settings.llm_stream_enabled:
        # 未开启流式时直接复用非流式逻辑，避免两套分支重复。
        return await generate_llm_result(
            prompt,
            client=resolved_client,
            settings=resolved_settings,
            system_instruction=system_instruction,
            model=model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            use_web_search=use_web_search,
        )

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
                            # 使用线程安全回调写入队列，避免跨线程竞争。
                            loop.call_soon_threadsafe(queue.put_nowait, ("delta", delta))
                final_response = stream.get_final_response()
                loop.call_soon_threadsafe(queue.put_nowait, ("final", final_response))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            # 无论成功/失败都发送 done，保证消费者退出循环。
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    worker = asyncio.create_task(asyncio.to_thread(_run_stream))
    chunks: list[str] = []
    final_response: object | None = None
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "delta":
                chunks.append(str(payload or ""))
                continue
            if kind == "final":
                final_response = payload
                continue
            if kind == "error":
                error = payload if isinstance(payload, Exception) else RuntimeError("llm stream failed")
                if not web_search_requested or not _is_web_search_unsupported(error):
                    raise error
                # 流式失败且不支持 web_search 时，降级为非流式结果。
                fallback_result = await generate_llm_result(
                    prompt,
                    client=resolved_client,
                    settings=resolved_settings,
                    system_instruction=system_instruction,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    max_output_tokens=max_output_tokens,
                    use_web_search=False,
                )
                return LlmTextResult(
                    text=fallback_result.text,
                    used_web_search=False,
                    web_search_status="unsupported",
                    web_sources=[],
                )
            break
    finally:
        await worker

    resolved_text = "".join(chunks).strip()
    if not resolved_text and final_response is not None:
        resolved_text = _extract_output_text(final_response)

    return LlmTextResult(
        text=resolved_text,
        used_web_search=web_search_requested,
        web_search_status="used" if web_search_requested else "disabled",
        web_sources=_extract_web_sources(final_response) if final_response is not None else [],
    )


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
        # 流式关闭时直接 yield 完整文本，保持调用方统一消费接口。
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
                            # 仅投递增量文本，避免占用过多内存。
                            loop.call_soon_threadsafe(
                                queue.put_nowait, ("delta", delta)
                            )
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            # 发送 done 表示流结束，调用方可退出消费循环。
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
