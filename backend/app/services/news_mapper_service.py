from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_instrument import StockInstrument
from app.schemas.news import HotNewsItemResponse, NewsEventResponse, StockRelatedNewsItemResponse


MACRO_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "geopolitical_conflict": (
        "中东",
        "战争",
        "冲突",
        "袭击",
        "地缘",
        "停火",
    ),
    "monetary_policy": (
        "降息",
        "加息",
        "美联储",
        "央行",
        "利率",
        "货币政策",
    ),
    "commodity_supply": (
        "原油",
        "石油",
        "黄金",
        "天然气",
        "opec",
        "贵金属",
    ),
    "regulation_policy": (
        "政策",
        "监管",
        "条例",
        "产业政策",
        "发改委",
        "财政部",
        "工信部",
    ),
}


MACRO_IMPACT_PROFILES: dict[str, dict[str, list[str]]] = {
    "geopolitical_conflict": {
        "affected_assets": ["原油", "黄金", "天然气"],
        "beneficiary_sectors": ["油气开采", "黄金采选", "军工"],
        "pressure_sectors": ["航空运输", "化工中下游", "高耗能制造"],
        "a_share_targets": ["中国海油", "山东黄金", "中远海能"],
    },
    "monetary_policy": {
        "affected_assets": ["国债", "成长股估值", "美元指数"],
        "beneficiary_sectors": ["券商", "科技成长", "地产链"],
        "pressure_sectors": ["银行净息差", "高分红防御"],
        "a_share_targets": ["中信证券", "东方财富", "万科A"],
    },
    "commodity_supply": {
        "affected_assets": ["原油", "黄金", "有色金属"],
        "beneficiary_sectors": ["能源", "有色", "资源品航运"],
        "pressure_sectors": ["航空", "化纤", "下游加工"],
        "a_share_targets": ["紫金矿业", "中国石油", "招商轮船"],
    },
    "regulation_policy": {
        "affected_assets": ["行业风险偏好", "融资成本", "信用利差"],
        "beneficiary_sectors": ["政策支持产业", "合规龙头"],
        "pressure_sectors": ["高杠杆弱资质", "受限产能"],
        "a_share_targets": ["宁德时代", "隆基绿能", "三一重工"],
    },
    "other": {
        "affected_assets": ["市场风险偏好"],
        "beneficiary_sectors": ["需结合事件细分"],
        "pressure_sectors": ["需结合事件细分"],
        "a_share_targets": ["待人工研判"],
    },
}

MACRO_TOPIC_INDUSTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "geopolitical_conflict": ("石油", "黄金", "军工", "航运", "航空"),
    "monetary_policy": ("证券", "银行", "地产", "科技"),
    "commodity_supply": ("石油", "黄金", "有色", "煤炭", "航运"),
    "regulation_policy": ("新能源", "高端制造", "半导体", "医药"),
    "other": (),
}


def detect_macro_topic(*, title: str, summary: str | None) -> str:
    haystack = f"{title} {summary or ''}".lower()
    for topic, keywords in MACRO_TOPIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in haystack:
                return topic
    return "other"


def list_macro_impact_profiles(
    topic: str,
) -> list[dict[str, object]]:
    normalized_topic = topic.strip().lower() or "all"
    if normalized_topic == "all":
        topics = list(MACRO_IMPACT_PROFILES.keys())
    else:
        topics = [normalized_topic]

    profiles: list[dict[str, object]] = []
    for key in topics:
        profile = MACRO_IMPACT_PROFILES.get(key)
        if profile is None:
            continue
        profiles.append(
            {
                "topic": key,
                "affected_assets": profile["affected_assets"],
                "beneficiary_sectors": profile["beneficiary_sectors"],
                "pressure_sectors": profile["pressure_sectors"],
                "a_share_targets": profile["a_share_targets"],
                "a_share_candidates": [],
            }
        )
    return profiles


async def attach_dynamic_a_share_candidates(
    *,
    session: AsyncSession,
    profiles: list[dict[str, object]],
    per_topic_limit: int = 6,
) -> list[dict[str, object]]:
    statement = select(StockInstrument).where(StockInstrument.list_status == "L")
    instruments = (await session.execute(statement)).scalars().all()

    for profile in profiles:
        topic = str(profile.get("topic") or "other")
        keywords = MACRO_TOPIC_INDUSTRY_KEYWORDS.get(topic, ())
        matches: list[dict[str, str | None]] = []
        seen_ts_codes: set[str] = set()

        for instrument in instruments:
            haystack = f"{instrument.industry or ''} {instrument.name or ''} {instrument.fullname or ''}"
            if keywords and not any(keyword in haystack for keyword in keywords):
                continue
            if instrument.ts_code in seen_ts_codes:
                continue
            seen_ts_codes.add(instrument.ts_code)
            matches.append(
                {
                    "ts_code": instrument.ts_code,
                    "symbol": instrument.symbol,
                    "name": instrument.name,
                    "industry": instrument.industry,
                }
            )
            if len(matches) >= per_topic_limit:
                break

        profile["a_share_candidates"] = matches

    return profiles


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d", "%Y%m%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    normalized = text.replace("/", "-")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def map_hot_news_rows(rows: list[dict[str, object]]) -> list[HotNewsItemResponse]:
    mapped: list[HotNewsItemResponse] = []
    seen_urls: set[str] = set()

    for row in rows:
        title = _as_text(row.get("标题"))
        if not title:
            continue
        url = _as_text(row.get("链接"))
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        mapped.append(
            HotNewsItemResponse(
                title=title,
                summary=_as_text(row.get("摘要")),
                published_at=_parse_datetime(row.get("发布时间")),
                url=url,
                source="eastmoney_global",
                macro_topic=detect_macro_topic(
                    title=title,
                    summary=_as_text(row.get("摘要")),
                ),
            )
        )

    mapped.sort(
        key=lambda item: item.published_at or datetime.min,
        reverse=True,
    )
    return mapped


def map_stock_news_rows(
    *,
    ts_code: str,
    symbol: str,
    rows: list[dict[str, object]],
) -> list[StockRelatedNewsItemResponse]:
    mapped: list[StockRelatedNewsItemResponse] = []
    seen_urls: set[str] = set()

    for row in rows:
        title = _as_text(row.get("新闻标题"))
        if not title:
            continue
        url = _as_text(row.get("新闻链接"))
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        mapped.append(
            StockRelatedNewsItemResponse(
                ts_code=ts_code,
                symbol=symbol,
                title=title,
                summary=_as_text(row.get("新闻内容")),
                published_at=_parse_datetime(row.get("发布时间")),
                url=url,
                publisher=_as_text(row.get("文章来源")),
                source="eastmoney_stock",
            )
        )

    mapped.sort(
        key=lambda item: item.published_at or datetime.min,
        reverse=True,
    )
    return mapped


def map_stock_announcement_rows(
    *,
    ts_code: str,
    symbol: str,
    rows: list[dict[str, object]],
) -> list[StockRelatedNewsItemResponse]:
    mapped: list[StockRelatedNewsItemResponse] = []
    seen_urls: set[str] = set()

    for row in rows:
        title = _as_text(row.get("公告标题"))
        if not title:
            continue
        url = _as_text(row.get("公告链接"))
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        mapped.append(
            StockRelatedNewsItemResponse(
                ts_code=ts_code,
                symbol=symbol,
                title=title,
                summary=None,
                published_at=_parse_datetime(row.get("公告时间")),
                url=url,
                publisher="巨潮资讯",
                source="cninfo_announcement",
            )
        )

    mapped.sort(
        key=lambda item: item.published_at or datetime.min,
        reverse=True,
    )
    return mapped


def map_policy_news_rows(rows: list[dict[str, object]]) -> list[NewsEventResponse]:
    mapped: list[NewsEventResponse] = []
    for row in rows:
        title = _as_text(row.get("title"))
        if not title:
            continue
        mapped.append(
            NewsEventResponse(
                scope="policy",
                cache_variant="policy_source",
                ts_code=None,
                symbol=None,
                title=title,
                summary=_as_text(row.get("summary")),
                published_at=_parse_datetime(row.get("published_at")),
                url=_as_text(row.get("link")),
                publisher="政策网关",
                source="policy_gateway",
                macro_topic="regulation_policy",
                fetched_at=datetime.now(UTC),
            )
        )
    return mapped
