import asyncio

import akshare as ak


def _to_records(frame) -> list[dict[str, object]]:
    if frame is None:
        return []
    return frame.to_dict(orient="records")


async def fetch_hot_news() -> list[dict[str, object]]:
    def _run() -> list[dict[str, object]]:
        frame = ak.stock_info_global_em()
        return _to_records(frame)

    return await asyncio.to_thread(_run)


async def fetch_stock_news(symbol: str) -> list[dict[str, object]]:
    normalized_symbol = symbol.strip()
    if not normalized_symbol:
        return []

    def _run() -> list[dict[str, object]]:
        frame = ak.stock_news_em(symbol=normalized_symbol)
        return _to_records(frame)

    return await asyncio.to_thread(_run)


async def fetch_stock_announcements(
    *,
    symbol: str,
    market: str = "沪深京",
    keyword: str = "",
    category: str = "",
    start_date: str = "",
    end_date: str = "",
) -> list[dict[str, object]]:
    normalized_symbol = symbol.strip()
    if not normalized_symbol:
        return []

    def _run() -> list[dict[str, object]]:
        frame = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=normalized_symbol,
            market=market,
            keyword=keyword,
            category=category,
            start_date=start_date,
            end_date=end_date,
        )
        return _to_records(frame)

    return await asyncio.to_thread(_run)
