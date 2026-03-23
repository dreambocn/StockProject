import asyncio

from app.services.factor_weight_service import FactorWeight
from app.services.llm_analysis_service import generate_stock_analysis_report


class FakeClient:
    async def responses(self):
        return None


class FakeGenerator:
    async def __call__(self, prompt: str, client=None, max_output_tokens=512):
        return "模拟中文分析摘要"


def test_llm_analysis_service_returns_summary(monkeypatch) -> None:
    async def fake_generator(
        prompt: str,
        client=None,
        system_instruction=None,
        max_output_tokens=512,
        use_web_search=False,
    ):
        _ = prompt, client, system_instruction, max_output_tokens, use_web_search
        class FakeResult:
            text = "模拟中文分析摘要"
            used_web_search = False
            web_search_status = "disabled"
            web_sources = []

        return FakeResult()

    monkeypatch.setattr(
        "app.services.llm_analysis_service.generate_llm_result", fake_generator
    )

    async def run_test():
        result = await generate_stock_analysis_report(
            ts_code="600519.SH",
            instrument_name="贵州茅台",
            events=[{"title": "政策鼓励消费"}],
            factor_weights=[FactorWeight("policy", "政策", 0.5, "positive", [], "基于政策")],
        )
        assert "中文分析" in result.summary

    asyncio.run(run_test())


def test_llm_analysis_service_fallback_on_error(monkeypatch) -> None:
    async def fake_generator(
        prompt: str,
        client=None,
        system_instruction=None,
        max_output_tokens=512,
        use_web_search=False,
    ):
        _ = prompt, client, system_instruction, max_output_tokens, use_web_search
        raise RuntimeError("fail")

    monkeypatch.setattr(
        "app.services.llm_analysis_service.generate_llm_result", fake_generator
    )

    async def run_test():
        result = await generate_stock_analysis_report(
            ts_code="000001.SZ",
            instrument_name="平安银行",
            events=[{"title": "监管加强"}],
            factor_weights=[FactorWeight("policy", "政策", 0.8, "negative", [], "")],
        )
        assert result.status == "partial"

    asyncio.run(run_test())


def test_llm_analysis_service_sanitizes_agentic_output(monkeypatch) -> None:
    async def fake_generator(
        prompt: str,
        client=None,
        system_instruction=None,
        max_output_tokens=512,
        use_web_search=False,
    ):
        _ = prompt, client, system_instruction, max_output_tokens, use_web_search
        class FakeResult:
            text = (
                "先看结论，再回溯证据与风险。\n"
                "当前分析状态 · 已生成\n"
                "准备先查看仓库根目录以了解文件结构和现有文档。"
            )
            used_web_search = True
            web_search_status = "used"
            web_sources = []

        return FakeResult()

    monkeypatch.setattr(
        "app.services.llm_analysis_service.generate_llm_result", fake_generator
    )

    async def run_test():
        result = await generate_stock_analysis_report(
            ts_code="600519.SH",
            instrument_name="贵州茅台",
            events=[{"title": "政策鼓励消费"}],
            factor_weights=[FactorWeight("policy", "政策", 0.5, "positive", [], "基于政策")],
            use_web_search=True,
        )
        assert "准备先查看仓库根目录" not in result.summary
        assert result.summary

    asyncio.run(run_test())


def test_llm_analysis_service_filters_streaming_agentic_output(monkeypatch) -> None:
    async def fake_stream(*args, **kwargs):
        _ = args, kwargs
        yield "先看结论，再回溯证据与风险。\n"
        yield "当前分析状态 · 已生成\n"
        yield "准备先查看仓库根目录以了解文件结构和现有文档。"

    monkeypatch.setattr(
        "app.services.llm_analysis_service.stream_llm_text", fake_stream
    )

    async def run_test():
        deltas: list[str] = []
        async def capture_delta(delta: str) -> None:
            deltas.append(delta)

        result = await generate_stock_analysis_report(
            ts_code="600519.SH",
            instrument_name="贵州茅台",
            events=[{"title": "政策鼓励消费"}],
            factor_weights=[FactorWeight("policy", "政策", 0.5, "positive", [], "基于政策")],
            use_web_search=True,
            on_delta=capture_delta,
        )
        assert deltas == []
        assert "准备先查看仓库根目录" not in result.summary
        assert result.summary

    asyncio.run(run_test())
