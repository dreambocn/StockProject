from collections import defaultdict
from datetime import UTC, datetime, timedelta
import hashlib
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_event import NewsEvent
from app.models.stock_instrument import StockInstrument
from app.schemas.news import (
    CandidateEvidenceItemResponse,
    CandidateEvidenceSummaryResponse,
    HotNewsItemResponse,
    NewsEventResponse,
    StockRelatedNewsItemResponse,
)
from app.services.candidate_evidence_service import get_candidate_evidence_snapshots


MACRO_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "geopolitical_conflict": ("中东", "战争", "冲突", "袭击", "地缘", "停火"),
    "monetary_policy": ("降息", "加息", "美联储", "央行", "利率", "货币政策"),
    "commodity_supply": ("原油", "石油", "黄金", "天然气", "opec", "贵金属"),
    "regulation_policy": ("政策", "监管", "条例", "产业政策", "发改委", "财政部", "工信部"),
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
        "a_share_targets": ["中国海油", "山东黄金", "招商轮船"],
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

SOURCE_PRIORITY_MAP: dict[str, int] = {
    "tushare": 30,
    "akshare": 20,
    "internal": 10,
}

SOURCE_COVERAGE_MAP: dict[str, str] = {
    "akshare": "AK",
    "tushare": "TS",
    "internal": "IN",
}


def detect_macro_topic(*, title: str, summary: str | None) -> str:
    haystack = f"{title} {summary or ''}".lower()
    for topic, keywords in MACRO_TOPIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in haystack:
                return topic
    return "other"


def normalize_provider(provider: str | None, source: str | None = None) -> str:
    provider_text = str(provider or "").strip().lower()
    source_text = str(source or "").strip().lower()
    if provider_text and provider_text != "internal":
        return provider_text
    if "tushare" in source_text:
        return "tushare"
    if source_text:
        return "akshare"
    return "internal"


def providers_to_source_coverage(providers: list[str]) -> str:
    normalized = sorted({normalize_provider(provider) for provider in providers if provider})
    if not normalized:
        return "IN"
    labels = [SOURCE_COVERAGE_MAP.get(provider, provider.upper()) for provider in normalized]
    return "+".join(labels)


def _normalize_title(title: str) -> str:
    lowered = title.strip().lower()
    lowered = re.sub(r"[：:|｜\-—_·•\s]+", "", lowered)
    lowered = re.sub(r"(财联社|证券时报|东方财富|巨潮资讯|央视新闻)$", "", lowered)
    return lowered


def build_cluster_key(
    *,
    title: str,
    published_at: datetime | None,
    macro_topic: str | None,
) -> str:
    normalized_date = (published_at or datetime.min).strftime("%Y%m%d")
    normalized_title = _normalize_title(title)
    digest = hashlib.sha1(f"{normalized_title}|{normalized_date}|{macro_topic or ''}".encode("utf-8")).hexdigest()
    return digest[:24]


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d", "%Y%m%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    normalized = text.replace("/", "-")
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _build_candidate_freshness_score(latest_published_at: datetime | None) -> int:
    normalized_published_at = _normalize_datetime(latest_published_at)
    if normalized_published_at is None:
        return 0

    age_seconds = (datetime.now(UTC) - normalized_published_at).total_seconds()
    if age_seconds <= 86400:
        return 100
    if age_seconds <= 3 * 86400:
        return 85
    if age_seconds <= 7 * 86400:
        return 70
    if age_seconds <= 14 * 86400:
        return 50
    if age_seconds <= 30 * 86400:
        return 30
    return 10


def _build_candidate_confidence(score: int, source_hit_count: int) -> str:
    if score >= 60 and source_hit_count >= 4:
        return "高"
    if score >= 40 and source_hit_count >= 2:
        return "中"
    return "低"


def _to_evidence_item_payload(
    items: list[CandidateEvidenceItemResponse],
    *,
    limit: int,
) -> list[dict[str, object | None]]:
    return [item.model_dump(mode="json") for item in items[: max(1, min(limit, 5))]]


def list_macro_impact_profiles(topic: str) -> list[dict[str, object]]:
    normalized_topic = topic.strip().lower() or "all"
    topics = list(MACRO_IMPACT_PROFILES.keys()) if normalized_topic == "all" else [normalized_topic]

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
                "anchor_event": None,
                "a_share_candidates": [],
            }
        )
    return profiles


def _build_hot_news_item(
    *,
    title: str,
    summary: str | None,
    published_at: datetime | None,
    url: str | None,
    source: str,
    provider: str,
    external_id: str | None = None,
) -> HotNewsItemResponse:
    macro_topic = detect_macro_topic(title=title, summary=summary)
    cluster_key = build_cluster_key(
        title=title,
        published_at=published_at,
        macro_topic=macro_topic,
    )
    return HotNewsItemResponse(
        event_id=None,
        cluster_key=cluster_key,
        providers=[normalize_provider(provider, source)],
        source_coverage=providers_to_source_coverage([provider]),
        title=title,
        summary=summary,
        published_at=published_at,
        url=url,
        source=source,
        macro_topic=macro_topic,
    )


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
            _build_hot_news_item(
                title=title,
                summary=_as_text(row.get("摘要")),
                published_at=_parse_datetime(row.get("发布时间")),
                url=url,
                source="eastmoney_global",
                provider="akshare",
            )
        )

    mapped.sort(key=lambda item: item.published_at or datetime.min, reverse=True)
    return mapped


def map_tushare_major_news_rows(rows: list[dict[str, object]]) -> list[HotNewsItemResponse]:
    mapped: list[HotNewsItemResponse] = []
    for row in rows:
        title = _as_text(row.get("title")) or _as_text(row.get("content"))
        if not title:
            continue
        mapped.append(
            _build_hot_news_item(
                title=title,
                summary=_as_text(row.get("content")) or _as_text(row.get("summary")),
                published_at=_parse_datetime(row.get("pub_time") or row.get("pub_date")),
                url=_as_text(row.get("url")),
                source="tushare_major_news",
                provider="tushare",
                external_id=_as_text(row.get("id")),
            )
        )

    mapped.sort(key=lambda item: item.published_at or datetime.min, reverse=True)
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
    mapped.sort(key=lambda item: item.published_at or datetime.min, reverse=True)
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
    mapped.sort(key=lambda item: item.published_at or datetime.min, reverse=True)
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
                source=_as_text(row.get("source")) or "policy_gateway",
                macro_topic="regulation_policy",
                fetched_at=datetime.now(UTC),
            )
        )
    return mapped


async def attach_dynamic_a_share_candidates(
    *,
    session: AsyncSession,
    profiles: list[dict[str, object]],
    per_topic_limit: int = 6,
    evidence_item_limit: int = 3,
) -> list[dict[str, object]]:
    statement = select(StockInstrument).where(StockInstrument.list_status == "L")
    instruments = (await session.execute(statement)).scalars().all()
    try:
        candidate_evidence_by_ts_code = await get_candidate_evidence_snapshots(
            session=session,
            ts_codes=[item.ts_code for item in instruments if item.ts_code],
            evidence_item_limit=evidence_item_limit,
        )
    except Exception:
        # 关键降级：候选增强快照异常时仅丢弃增强信息，基础候选链路继续执行。
        candidate_evidence_by_ts_code = {}

    recent_since = datetime.now(UTC) - timedelta(days=7)
    recent_news_statement = select(NewsEvent).where(
        NewsEvent.scope == "stock",
        NewsEvent.published_at >= recent_since,
    )
    recent_news_rows = (await session.execute(recent_news_statement)).scalars().all()
    stock_event_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"news": 0, "announcement": 0})
    for row in recent_news_rows:
        if not row.ts_code:
            continue
        if row.source == "cninfo_announcement":
            stock_event_counts[row.ts_code]["announcement"] += 1
        else:
            stock_event_counts[row.ts_code]["news"] += 1

    hot_statement = select(NewsEvent).where(NewsEvent.scope == "hot").order_by(
        NewsEvent.source_priority.desc(),
        NewsEvent.published_at.desc(),
        NewsEvent.created_at.desc(),
    )
    hot_rows = (await session.execute(hot_statement)).scalars().all()

    for profile in profiles:
        topic = str(profile.get("topic") or "other")
        keywords = MACRO_TOPIC_INDUSTRY_KEYWORDS.get(topic, ())
        target_names = set(profile.get("a_share_targets") or [])
        profile["anchor_event"] = None
        for row in hot_rows:
            if row.macro_topic != topic:
                continue
            normalized_provider = normalize_provider(row.provider, row.source)
            profile["anchor_event"] = {
                "event_id": row.id,
                "title": row.title,
                "published_at": row.published_at,
                "providers": [normalized_provider],
                "source_coverage": providers_to_source_coverage([normalized_provider]),
            }
            break

        candidates: list[dict[str, object]] = []
        for instrument in instruments:
            score = 0
            reasons: list[str] = []
            evidence_snapshot = candidate_evidence_by_ts_code.get(
                instrument.ts_code,
                CandidateEvidenceSummaryResponse(ts_code=instrument.ts_code),
            )
            haystack = f"{instrument.industry or ''} {instrument.name or ''} {instrument.fullname or ''}"
            if instrument.name in target_names:
                score += 35
                reasons.append("命中主题目标股")
            matched_keywords = [keyword for keyword in keywords if keyword in haystack]
            if matched_keywords:
                score += 15
                reasons.append(f"命中行业关键词：{matched_keywords[0]}")
            news_count = stock_event_counts[instrument.ts_code]["news"]
            if news_count > 0:
                score += 10
                reasons.append(f"近7日相关新闻 {news_count} 条")
            announcement_count = stock_event_counts[instrument.ts_code]["announcement"]
            if announcement_count > 0:
                score += 10
                reasons.append(f"近7日公告 {announcement_count} 条")
            if evidence_snapshot.hot_search_count > 0:
                score += 5
                reasons.append(f"百度热搜命中 {evidence_snapshot.hot_search_count} 次")
            if evidence_snapshot.research_report_count > 0:
                score += 5
                reasons.append(f"近30日研报 {evidence_snapshot.research_report_count} 篇")
            if score <= 0:
                continue

            source_hit_count = (
                int(instrument.name in target_names)
                + int(bool(matched_keywords))
                + int(news_count > 0)
                + int(announcement_count > 0)
                + int(evidence_snapshot.hot_search_count > 0)
                + int(evidence_snapshot.research_report_count > 0)
            )
            normalized_score = min(score, 100)
            candidates.append(
                {
                    "ts_code": instrument.ts_code,
                    "symbol": instrument.symbol,
                    "name": instrument.name,
                    "industry": instrument.industry,
                    "relevance_score": normalized_score,
                    "match_reasons": reasons,
                    "evidence_summary": "；".join(reasons),
                    "source_hit_count": source_hit_count,
                    "source_breakdown": [
                        item.model_dump(mode="json")
                        for item in evidence_snapshot.source_breakdown
                    ],
                    "freshness_score": _build_candidate_freshness_score(
                        evidence_snapshot.latest_published_at
                    ),
                    "candidate_confidence": _build_candidate_confidence(
                        normalized_score,
                        source_hit_count,
                    ),
                    "evidence_items": _to_evidence_item_payload(
                        evidence_snapshot.evidence_items,
                        limit=evidence_item_limit,
                    ),
                }
            )

        candidates.sort(
            key=lambda item: (
                -int(item["relevance_score"]),
                -int(item["source_hit_count"]),
                str(item["ts_code"]),
            )
        )
        profile["a_share_candidates"] = candidates[:per_topic_limit]

    return profiles
