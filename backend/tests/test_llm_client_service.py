import asyncio
from types import SimpleNamespace

from app.core.settings import Settings
from app.services.llm_client_service import (
    build_openai_base_url,
    generate_llm_text,
    stream_llm_text,
)


class _FakeResponsesApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text="OK")

    def stream(self, **kwargs):
        self.calls.append(kwargs)

        class _StreamContext:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                return False

            def __iter__(self_inner):
                yield SimpleNamespace(type="response.output_text.delta", delta="Hello")
                yield SimpleNamespace(type="response.output_text.delta", delta=" Markdown")
                yield SimpleNamespace(type="response.completed")

        return _StreamContext()


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponsesApi()


def test_build_openai_base_url_appends_v1_suffix() -> None:
    assert build_openai_base_url("https://aixj.vip") == "https://aixj.vip/v1"
    assert build_openai_base_url("https://aixj.vip/v1") == "https://aixj.vip/v1"


def test_generate_llm_text_uses_responses_input_text_shape() -> None:
    async def _run() -> None:
        fake_client = _FakeClient()
        settings = Settings(
            _env_file=None,
            llm_base_url="https://aixj.vip",
            llm_wire_api="responses",
            llm_api_key="test-key",
            llm_model="gpt-5.1-codex-mini",
            llm_reasoning_effort="high",
        )

        result = await generate_llm_text(
            "请只返回OK",
            client=fake_client,
            settings=settings,
            max_output_tokens=32,
        )

        assert result == "OK"
        assert len(fake_client.responses.calls) == 1
        payload = fake_client.responses.calls[0]
        assert payload["model"] == "gpt-5.1-codex-mini"
        assert payload["store"] is False
        assert payload["reasoning"] == {"effort": "high"}
        assert payload["max_output_tokens"] == 32
        assert payload["input"] == [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "请只返回OK",
                    }
                ],
            }
        ]

    asyncio.run(_run())


def test_generate_llm_text_passes_web_search_tool_when_enabled() -> None:
    async def _run() -> None:
        fake_client = _FakeClient()
        settings = Settings(
            _env_file=None,
            llm_base_url="https://aixj.vip",
            llm_wire_api="responses",
            llm_api_key="test-key",
            llm_model="gpt-5.1-codex-mini",
            llm_reasoning_effort="high",
            llm_web_search_enabled=True,
        )

        result = await generate_llm_text(
            "请总结最新消息",
            client=fake_client,
            settings=settings,
            use_web_search=True,
        )

        assert result == "OK"
        payload = fake_client.responses.calls[0]
        assert payload["tools"] == [{"type": "web_search_preview"}]

    asyncio.run(_run())


def test_stream_llm_text_yields_incremental_chunks() -> None:
    async def _run() -> None:
        fake_client = _FakeClient()
        settings = Settings(
            _env_file=None,
            llm_base_url="https://aixj.vip",
            llm_wire_api="responses",
            llm_api_key="test-key",
            llm_model="gpt-5.1-codex-mini",
            llm_reasoning_effort="high",
            llm_stream_enabled=True,
        )

        chunks: list[str] = []
        async for chunk in stream_llm_text(
            "请用 Markdown 输出",
            client=fake_client,
            settings=settings,
        ):
            chunks.append(chunk)

        assert chunks == ["Hello", " Markdown"]

    asyncio.run(_run())
