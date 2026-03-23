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
    async def fake_generator(prompt: str, client=None, max_output_tokens=512, use_web_search=False):
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
    async def fake_generator(prompt: str, client=None, max_output_tokens=512, use_web_search=False):
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
