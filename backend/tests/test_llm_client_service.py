import asyncio
from types import SimpleNamespace

from app.core.settings import Settings
from app.services.llm_client_service import build_openai_base_url, generate_llm_text


class _FakeResponsesApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text="OK")


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
