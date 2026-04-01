from collections import defaultdict
from datetime import UTC, datetime, timedelta
import hashlib
import re

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.models.news_event import NewsEvent
from app.models.policy_document import PolicyDocument
from app.models.stock_instrument import StockInstrument
from app.schemas.news import (
    CandidateEvidenceItemResponse,
    CandidateEvidenceSummaryResponse,
    HotNewsItemResponse,
    NewsEventResponse,
    StockRelatedNewsItemResponse,
)
from app.services.candidate_evidence_service import get_candidate_evidence_snapshots
from app.services.news_fetch_batch_service import load_latest_news_fetch_batch


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
    "policy_document": 40,
    "tushare": 30,
    "akshare": 20,
    "internal": 10,
}

SOURCE_COVERAGE_MAP: dict[str, str] = {
    "akshare": "AK",
    "tushare": "TS",
    "internal": "IN",
}

CANDIDATE_POOL_MULTIPLIER = 4
MAX_CANDIDATE_POOL_SIZE = 24


async def _load_relevant_candidate_instruments(
    *,
    session: AsyncSession,
    target_names: set[str],
    keywords: set[str],
    recent_event_ts_codes: set[str],
) -> list[StockInstrument]:
    normalized_target_names = sorted(
        {
            str(name).strip()
            for name in target_names
            if str(name).strip() and str(name).strip() != "待人工研判"
        }
    )
    normalized_keywords = sorted(
        {str(keyword).strip() for keyword in keywords if str(keyword).strip()}
    )
    normalized_recent_event_ts_codes = sorted(
        {str(ts_code).strip().upper() for ts_code in recent_event_ts_codes if str(ts_code).strip()}
    )

    filters = []
    if normalized_target_names:
        filters.append(StockInstrument.name.in_(normalized_target_names))
    for keyword in normalized_keywords:
        wildcard = f"%{keyword}%"
        filters.extend(
            [
                StockInstrument.industry.ilike(wildcard),
                StockInstrument.name.ilike(wildcard),
                StockInstrument.fullname.ilike(wildcard),
            ]
        )
    if normalized_recent_event_ts_codes:
        filters.append(StockInstrument.ts_code.in_(normalized_recent_event_ts_codes))

    if not filters:
        return []

    statement = (
        select(StockInstrument)
        .options(
            load_only(
                StockInstrument.ts_code,
                StockInstrument.symbol,
                StockInstrument.name,
                StockInstrument.fullname,
                StockInstrument.industry,
            )
        )
        .where(StockInstrument.list_status == "L")
        .where(or_(*filters))
    )
    # 候选增强只依赖少数字段和相关股票集合，先在 SQL 层预筛掉无关标的，
    # 再配合 load_only 缩小行宽，避免每次构建影响面板都全量搬运上市公司主表。
    return (await session.execute(statement)).scalars().all()


def detect_macro_topic(*, title: str, summary: str | None) -> str:
    # 宏观主题只做关键字匹配，命中则锁定，避免过度推断。
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
    if source_text in {
        "policy_gateway",
        "gov_cn",
        "npc",
        "pbc",
        "csrc",
        "ndrc",
        "miit",
    }:
        return "internal"
    if "tushare" in source_text:
        return "tushare"
    if source_text:
        return "akshare"
    return "internal"


def providers_to_source_coverage(providers: list[str]) -> str:
    # 用简短标签表示来源覆盖，便于前端展示合并来源。
    normalized = sorted({normalize_provider(provider) for provider in providers if provider})
    if not normalized:
        return "IN"
    labels = [SOURCE_COVERAGE_MAP.get(provider, provider.upper()) for provider in normalized]
    return "+".join(labels)


def _normalize_title(title: str) -> str:
    # 聚类标题要去除噪声符号与常见媒体后缀，保证摘要聚合稳定。
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
    # 聚类键基于标题+日期+主题，避免不同日重复事件混到一起。
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
    # 新鲜度分数用于排序候选池，越近越高。
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
    # 置信度由分数与来源数量共同决定，避免单一来源导致误判偏高。
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
    # 证据条目限制上限，避免返回过长列表影响前端性能。
    return [item.model_dump(mode="json") for item in items[: max(1, min(limit, 5))]]


def _build_base_candidate_signals(
    *,
    instrument: StockInstrument,
    target_names: set[str],
    keywords: tuple[str, ...],
    news_count: int,
    announcement_count: int,
) -> tuple[int, list[str], int]:
    score = 0
    reasons: list[str] = []
    signal_hits = 0
    haystack = f"{instrument.industry or ''} {instrument.name or ''} {instrument.fullname or ''}"

    # 目标股命中权重最高，优先提高分数与命中数。
    if instrument.name in target_names:
        score += 35
        reasons.append("命中主题目标股")
        signal_hits += 1

    matched_keywords = [keyword for keyword in keywords if keyword in haystack]
    if matched_keywords:
        score += 15
        reasons.append(f"命中行业关键词：{matched_keywords[0]}")
        signal_hits += 1

    if news_count > 0:
        score += 10
        reasons.append(f"近7日相关新闻 {news_count} 条")
        signal_hits += 1

    if announcement_count > 0:
        score += 10
        reasons.append(f"近7日公告 {announcement_count} 条")
        signal_hits += 1

    return score, reasons, signal_hits


async def _load_recent_stock_event_counts(
    *,
    session: AsyncSession,
    recent_since: datetime,
) -> dict[str, dict[str, int]]:
    statement = (
        select(
            NewsEvent.ts_code,
            func.sum(
                case(
                    (NewsEvent.source == "cninfo_announcement", 1),
                    else_=0,
                )
            ).label("announcement_count"),
            func.sum(
                case(
                    (NewsEvent.source == "cninfo_announcement", 0),
                    else_=1,
                )
            ).label("news_count"),
        )
        .where(
            NewsEvent.scope == "stock",
            NewsEvent.published_at >= recent_since,
            NewsEvent.ts_code.is_not(None),
        )
        .group_by(NewsEvent.ts_code)
    )
    rows = (await session.execute(statement)).all()
    return {
        str(ts_code): {
            "news": int(news_count or 0),
            "announcement": int(announcement_count or 0),
        }
        for ts_code, announcement_count, news_count in rows
        if ts_code
    }


async def _load_anchor_events_by_topic(
    *,
    session: AsyncSession,
    topics: set[str],
) -> dict[str, dict[str, object]]:
    if not topics:
        return {}

    statement = select(NewsEvent).where(
        NewsEvent.scope == "hot",
        NewsEvent.cache_variant == "global",
        NewsEvent.macro_topic.in_(topics),
    )
    latest_batch = await load_latest_news_fetch_batch(
        session,
        scope="hot",
        cache_variant="global",
    )
    if latest_batch is not None:
        # 锚点事件只应来自最新热点批次，避免旧批次里“发布时间更晚”的历史数据拖慢查询并覆盖当前语义。
        statement = statement.where(NewsEvent.batch_id == latest_batch.id)
    else:
        latest_fetched_at = (
            await session.execute(
                select(func.max(NewsEvent.fetched_at)).where(
                    NewsEvent.scope == "hot",
                    NewsEvent.cache_variant == "global",
                )
            )
        ).scalar_one_or_none()
        if latest_fetched_at is None:
            return {}
        # 兼容旧数据：未写批次时退回最新 fetched_at 窗口，而不是扫描全部历史热点。
        statement = statement.where(NewsEvent.fetched_at == latest_fetched_at)

    statement = statement.order_by(
        NewsEvent.macro_topic.asc(),
        NewsEvent.source_priority.desc(),
        NewsEvent.published_at.desc(),
        NewsEvent.created_at.desc(),
    )
    rows = (await session.execute(statement)).scalars().all()

    anchor_events: dict[str, dict[str, object]] = {}
    for row in rows:
        topic = row.macro_topic
        if not topic or topic in anchor_events:
            continue
        normalized_provider = normalize_provider(row.provider, row.source)
        anchor_events[topic] = {
            "event_id": row.id,
            "title": row.title,
            "published_at": row.published_at,
            "providers": [normalized_provider],
            "source_coverage": providers_to_source_coverage([normalized_provider]),
        }
    return anchor_events


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


def map_policy_document_to_news_event_response(
    document: PolicyDocument,
    *,
    fetched_at: datetime,
) -> NewsEventResponse:
    # 关键流程：兼容路由只消费投影所需最小字段，正文与附件仍由政策主表负责承载。
    return NewsEventResponse(
        scope="policy",
        cache_variant="policy_source",
        ts_code=None,
        symbol=None,
        title=document.title,
        summary=document.summary
        or (document.content_text[:180] if document.content_text else None),
        published_at=document.published_at,
        url=document.url,
        publisher=document.issuing_authority,
        source=document.source,
        macro_topic=document.macro_topic or "other",
        fetched_at=fetched_at,
    )


async def attach_dynamic_a_share_candidates(
    *,
    session: AsyncSession,
    profiles: list[dict[str, object]],
    per_topic_limit: int = 6,
    evidence_item_limit: int = 3,
) -> list[dict[str, object]]:
    recent_since = datetime.now(UTC) - timedelta(days=7)
    stock_event_counts = await _load_recent_stock_event_counts(
        session=session,
        recent_since=recent_since,
    )
    topics = {str(profile.get("topic") or "other") for profile in profiles}
    anchor_events_by_topic = await _load_anchor_events_by_topic(
        session=session,
        topics=topics,
    )
    instruments = await _load_relevant_candidate_instruments(
        session=session,
        target_names={
            str(name).strip()
            for profile in profiles
            for name in (profile.get("a_share_targets") or [])
            if str(name).strip()
        },
        keywords={
            keyword
            for profile in profiles
            for keyword in MACRO_TOPIC_INDUSTRY_KEYWORDS.get(
                str(profile.get("topic") or "other"),
                (),
            )
            if str(keyword).strip()
        },
        recent_event_ts_codes=set(stock_event_counts.keys()),
    )
    candidate_pool_limit = min(
        MAX_CANDIDATE_POOL_SIZE,
        max(per_topic_limit, per_topic_limit * CANDIDATE_POOL_MULTIPLIER),
    )
    base_candidates_by_topic: dict[str, list[dict[str, object]]] = {}
    candidate_pool_ts_codes: set[str] = set()

    for profile in profiles:
        topic = str(profile.get("topic") or "other")
        keywords = MACRO_TOPIC_INDUSTRY_KEYWORDS.get(topic, ())
        target_names = set(profile.get("a_share_targets") or [])
        profile["anchor_event"] = anchor_events_by_topic.get(topic)
        base_candidates: list[dict[str, object]] = []
        for instrument in instruments:
            event_counts = stock_event_counts.get(
                instrument.ts_code,
                {"news": 0, "announcement": 0},
            )
            news_count = int(event_counts["news"])
            announcement_count = int(event_counts["announcement"])
            score, reasons, signal_hits = _build_base_candidate_signals(
                instrument=instrument,
                target_names=target_names,
                keywords=keywords,
                news_count=news_count,
                announcement_count=announcement_count,
            )
            if score <= 0 or not instrument.ts_code:
                continue

            base_candidates.append(
                {
                    "ts_code": instrument.ts_code,
                    "symbol": instrument.symbol,
                    "name": instrument.name,
                    "industry": instrument.industry,
                    "base_score": score,
                    "base_reasons": reasons,
                    "base_signal_hits": signal_hits,
                }
            )

        base_candidates.sort(
            key=lambda item: (
                -int(item["base_score"]),
                -int(item["base_signal_hits"]),
                str(item["ts_code"]),
            )
        )
        pooled_candidates = base_candidates[:candidate_pool_limit]
        base_candidates_by_topic[topic] = pooled_candidates
        candidate_pool_ts_codes.update(
            str(item["ts_code"]) for item in pooled_candidates if item.get("ts_code")
        )

    try:
        candidate_evidence_by_ts_code = await get_candidate_evidence_snapshots(
            session=session,
            ts_codes=sorted(candidate_pool_ts_codes),
            evidence_item_limit=evidence_item_limit,
            allow_remote_fetch=False,
        )
    except Exception:
        # 关键降级：候选增强快照异常时仅丢弃增强信息，基础候选链路继续执行。
        candidate_evidence_by_ts_code = {}

    for profile in profiles:
        topic = str(profile.get("topic") or "other")
        candidates: list[dict[str, object]] = []
        for base_candidate in base_candidates_by_topic.get(topic, []):
            ts_code = str(base_candidate["ts_code"])
            evidence_snapshot = candidate_evidence_by_ts_code.get(
                ts_code,
                CandidateEvidenceSummaryResponse(ts_code=ts_code),
            )
            reasons = list(base_candidate["base_reasons"])
            score = int(base_candidate["base_score"])
            source_hit_count = int(base_candidate["base_signal_hits"])

            if evidence_snapshot.hot_search_count > 0:
                score += 5
                reasons.append(f"百度热搜命中 {evidence_snapshot.hot_search_count} 次")
                source_hit_count += 1
            if evidence_snapshot.research_report_count > 0:
                score += 5
                reasons.append(f"近30日研报 {evidence_snapshot.research_report_count} 篇")
                source_hit_count += 1

            normalized_score = min(score, 100)
            candidates.append(
                {
                    "ts_code": ts_code,
                    "symbol": base_candidate["symbol"],
                    "name": base_candidate["name"],
                    "industry": base_candidate["industry"],
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
