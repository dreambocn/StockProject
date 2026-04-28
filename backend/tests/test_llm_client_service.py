import asyncio
from types import SimpleNamespace

from app.core.settings import Settings
from app.services.llm_client_service import (
    build_openai_base_url,
    generate_llm_result,
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

            def get_final_response(self_inner):
                return SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            content=[
                                SimpleNamespace(
                                    type="output_text",
                                    text="Hello Markdown",
                                    annotations=[
                                        SimpleNamespace(
                                            type="url_citation",
                                            title="国际油价收涨",
                                            url="https://finance.example.com/oil",
                                        )
                                    ],
                                )
                            ]
                        )
                    ]
                )

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


def test_generate_llm_text_supports_system_instruction() -> None:
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

        await generate_llm_text(
            "请输出股票分析",
            client=fake_client,
            settings=settings,
            system_instruction="你是股票分析助手，不要输出过程说明，不要描述工具调用。",
        )

        payload = fake_client.responses.calls[0]
        assert payload["input"][0]["role"] == "system"
        system_text = payload["input"][0]["content"][0]["text"]
        assert "不要输出过程说明" in system_text
        assert "不要描述工具调用" in system_text

    asyncio.run(_run())


def test_generate_llm_result_extracts_web_sources_from_annotations() -> None:
    async def _run() -> None:
        class _AnnotatedResponsesApi(_FakeResponsesApi):
            def create(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(
                    output_text="OK",
                    output=[
                        SimpleNamespace(
                            content=[
                                SimpleNamespace(
                                    type="output_text",
                                    text="OK",
                                    annotations=[
                                        SimpleNamespace(
                                            type="url_citation",
                                            title="国际油价收涨",
                                            url="https://finance.example.com/oil",
                                        ),
                                        SimpleNamespace(
                                            type="url_citation",
                                            title="国际油价收涨",
                                            url="https://finance.example.com/oil",
                                        ),
                                    ],
                                )
                            ],
                        )
                    ],
                )

        fake_client = _FakeClient()
        fake_client.responses = _AnnotatedResponsesApi()
        settings = Settings(
            _env_file=None,
            llm_base_url="https://aixj.vip",
            llm_wire_api="responses",
            llm_api_key="test-key",
            llm_model="gpt-5.1-codex-mini",
            llm_reasoning_effort="high",
            llm_web_search_enabled=True,
        )

        result = await generate_llm_result(
            "请总结最新消息",
            client=fake_client,
            settings=settings,
            use_web_search=True,
        )

        assert result.web_sources == [
            {
                "title": "国际油价收涨",
                "url": "https://finance.example.com/oil",
                "source": None,
                "published_at": None,
                "snippet": None,
            }
        ]

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


def test_stream_llm_text_falls_back_when_web_search_stream_is_unsupported() -> None:
    async def _run() -> None:
        class _UnsupportedStreamResponsesApi(_FakeResponsesApi):
            def stream(self, **kwargs):
                self.calls.append(kwargs)
                raise RuntimeError("web_search tool unsupported")

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(output_text="fallback text")

        fake_client = _FakeClient()
        fake_client.responses = _UnsupportedStreamResponsesApi()
        settings = Settings(
            _env_file=None,
            llm_base_url="https://aixj.vip",
            llm_wire_api="responses",
            llm_api_key="test-key",
            llm_model="gpt-5.1-codex-mini",
            llm_reasoning_effort="high",
            llm_stream_enabled=True,
            llm_web_search_enabled=True,
        )

        chunks: list[str] = []
        async for chunk in stream_llm_text(
            "请总结最新消息",
            client=fake_client,
            settings=settings,
            use_web_search=True,
        ):
            chunks.append(chunk)

        assert chunks == ["fallback text"]
        assert fake_client.responses.calls[0]["tools"] == [{"type": "web_search_preview"}]
        assert "tools" not in fake_client.responses.calls[1]

    asyncio.run(_run())
