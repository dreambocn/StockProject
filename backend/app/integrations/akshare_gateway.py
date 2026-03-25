import asyncio

import akshare as ak


def _to_records(frame) -> list[dict[str, object]]:
    # akshare 返回 DataFrame；统一转成 records 便于后续映射与缓存。
    if frame is None:
        return []
    return frame.to_dict(orient="records")


async def fetch_hot_news() -> list[dict[str, object]]:
    def _run() -> list[dict[str, object]]:
        # akshare 调用为同步 IO，放入线程池避免阻塞事件循环。
        frame = ak.stock_info_global_em()
        return _to_records(frame)

    return await asyncio.to_thread(_run)


async def fetch_stock_news(symbol: str) -> list[dict[str, object]]:
    normalized_symbol = symbol.strip()
    # 空股票代码直接短路，避免无意义请求与异常数据。
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
    # 证券代码为空时不触发第三方请求，降低外部接口压力。
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


async def fetch_stock_hot_search() -> list[dict[str, object]]:
    def _run() -> list[dict[str, object]]:
        # 热搜接口无需入参，按默认口径拉取。
        frame = ak.stock_hot_search_baidu()
        return _to_records(frame)

    return await asyncio.to_thread(_run)


async def fetch_stock_research_reports() -> list[dict[str, object]]:
    def _run() -> list[dict[str, object]]:
        # 传空 symbol 表示全市场研报列表。
        frame = ak.stock_research_report_em(symbol="")
        return _to_records(frame)

    return await asyncio.to_thread(_run)
