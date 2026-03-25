from datetime import UTC, datetime, timedelta

from app.models.news_event import NewsEvent
from app.services.analysis_event_selection_service import (
    build_analysis_event_logical_key,
    select_generation_analysis_events,
    select_summary_analysis_events,
)


def _build_news_event(
    *,
    event_id: str,
    scope: str,
    published_at: datetime,
    title: str | None = None,
    cluster_key: str | None = None,
    ts_code: str | None = None,
    macro_topic: str | None = None,
    fetched_offset_minutes: int = 0,
) -> NewsEvent:
    return NewsEvent(
        id=event_id,
        scope=scope,
        cache_variant="default",
        ts_code=ts_code,
        symbol=(ts_code or "").split(".")[0] or None,
        title=title or event_id,
        summary=f"{event_id}-summary",
        published_at=published_at,
        url=f"https://example.com/{event_id}",
        publisher="测试源",
        source=f"{scope}-source",
        macro_topic=macro_topic,
        cluster_key=cluster_key,
        fetched_at=published_at + timedelta(minutes=fetched_offset_minutes),
        created_at=published_at + timedelta(minutes=fetched_offset_minutes),
    )


def test_select_generation_analysis_events_balances_quotas_and_keeps_anchor_first() -> None:
    base_time = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
    events: list[NewsEvent] = []

    events.append(
        _build_news_event(
            event_id="stock-anchor",
            scope="stock",
            ts_code="600519.SH",
            macro_topic="commodity_supply",
            title="锚点事件",
            published_at=base_time,
        )
    )
    events.append(
        _build_news_event(
            event_id="stock-anchor-archived",
            scope="stock",
            ts_code="600519.SH",
            macro_topic="commodity_supply",
            title="锚点事件",
            cluster_key="anchor-cluster",
            published_at=base_time - timedelta(hours=1),
        )
    )

    for index in range(1, 12):
        events.append(
            _build_news_event(
                event_id=f"stock-{index}",
                scope="stock",
                ts_code="600519.SH",
                macro_topic="commodity_supply",
                published_at=base_time - timedelta(minutes=index),
            )
        )

    for index in range(8):
        events.append(
            _build_news_event(
                event_id=f"policy-{index}",
                scope="policy",
                macro_topic="commodity_supply",
                published_at=base_time - timedelta(hours=1, minutes=index),
            )
        )

    for index in range(10):
        events.append(
            _build_news_event(
                event_id=f"hot-{index}",
                scope="hot",
                macro_topic="commodity_supply",
                published_at=base_time - timedelta(hours=2, minutes=index),
            )
        )

    selected = select_generation_analysis_events(
        events,
        anchor_event_id="stock-anchor",
        total_limit=30,
        stock_quota=12,
        policy_quota=8,
        hot_quota=10,
    )

    assert len(selected) == 30
    assert selected[0].id == "stock-anchor"
    assert len([item for item in selected if item.scope == "stock"]) == 12
    assert len([item for item in selected if item.scope == "policy"]) == 8
    assert len([item for item in selected if item.scope == "hot"]) == 10
    assert len({build_analysis_event_logical_key(item) for item in selected}) == 30


def test_select_generation_analysis_events_backfills_missing_quota_with_remaining_candidates() -> None:
    base_time = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
    events = [
        _build_news_event(
            event_id="stock-anchor",
            scope="stock",
            ts_code="600519.SH",
            macro_topic="energy",
            published_at=base_time,
        ),
        _build_news_event(
            event_id="stock-1",
            scope="stock",
            ts_code="600519.SH",
            macro_topic="energy",
            published_at=base_time - timedelta(minutes=1),
        ),
        _build_news_event(
            event_id="stock-2",
            scope="stock",
            ts_code="600519.SH",
            macro_topic="energy",
            published_at=base_time - timedelta(minutes=2),
        ),
        _build_news_event(
            event_id="stock-3",
            scope="stock",
            ts_code="600519.SH",
            macro_topic="energy",
            published_at=base_time - timedelta(minutes=3),
        ),
        _build_news_event(
            event_id="policy-1",
            scope="policy",
            macro_topic="energy",
            published_at=base_time - timedelta(hours=1),
        ),
        _build_news_event(
            event_id="hot-1",
            scope="hot",
            macro_topic="energy",
            published_at=base_time - timedelta(hours=2),
        ),
        _build_news_event(
            event_id="hot-2",
            scope="hot",
            macro_topic="energy",
            published_at=base_time - timedelta(hours=2, minutes=1),
        ),
    ]

    selected = select_generation_analysis_events(
        events,
        anchor_event_id="stock-anchor",
        total_limit=6,
        stock_quota=2,
        policy_quota=2,
        hot_quota=2,
    )

    assert len(selected) == 6
    assert selected[0].id == "stock-anchor"
    assert [item.scope for item in selected].count("policy") == 1
    assert [item.scope for item in selected].count("hot") == 2
    assert [item.scope for item in selected].count("stock") == 3


def test_select_summary_analysis_events_dedupes_historical_links_and_keeps_anchor_first() -> None:
    base_time = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
    events = [
        {
            "event_id": "duplicate-new",
            "scope": "stock",
            "title": "同一条个股事件",
            "published_at": base_time,
            "source": "stock-source",
            "macro_topic": "commodity_supply",
            "event_type": None,
            "event_tags": [],
            "sentiment_label": None,
            "sentiment_score": None,
            "anchor_trade_date": None,
            "window_return_pct": None,
            "window_volatility": None,
            "abnormal_volume_ratio": None,
            "correlation_score": 0.9,
            "confidence": "high",
            "link_status": "linked",
            "cluster_key": "duplicate-cluster",
            "ts_code": "600519.SH",
            "url": "https://example.com/duplicate",
            "link_created_at": base_time,
        },
        {
            "event_id": "anchor-old",
            "scope": "stock",
            "title": "锚点旧批次",
            "published_at": base_time - timedelta(minutes=1),
            "source": "stock-source",
            "macro_topic": "commodity_supply",
            "event_type": None,
            "event_tags": [],
            "sentiment_label": None,
            "sentiment_score": None,
            "anchor_trade_date": None,
            "window_return_pct": None,
            "window_volatility": None,
            "abnormal_volume_ratio": None,
            "correlation_score": 0.8,
            "confidence": "high",
            "link_status": "linked",
            "cluster_key": "anchor-cluster",
            "ts_code": "600519.SH",
            "url": "https://example.com/anchor",
            "link_created_at": base_time - timedelta(minutes=1),
        },
        {
            "event_id": "anchor-new",
            "scope": "stock",
            "title": "锚点旧批次",
            "published_at": base_time - timedelta(minutes=1),
            "source": "stock-source",
            "macro_topic": "commodity_supply",
            "event_type": None,
            "event_tags": [],
            "sentiment_label": None,
            "sentiment_score": None,
            "anchor_trade_date": None,
            "window_return_pct": None,
            "window_volatility": None,
            "abnormal_volume_ratio": None,
            "correlation_score": 0.85,
            "confidence": "high",
            "link_status": "linked",
            "cluster_key": "anchor-cluster",
            "ts_code": "600519.SH",
            "url": "https://example.com/anchor",
            "link_created_at": base_time - timedelta(seconds=30),
        },
        {
            "event_id": "policy-1",
            "scope": "policy",
            "title": "政策事件",
            "published_at": base_time - timedelta(hours=1),
            "source": "policy-source",
            "macro_topic": "commodity_supply",
            "event_type": None,
            "event_tags": [],
            "sentiment_label": None,
            "sentiment_score": None,
            "anchor_trade_date": None,
            "window_return_pct": None,
            "window_volatility": None,
            "abnormal_volume_ratio": None,
            "correlation_score": 0.5,
            "confidence": "medium",
            "link_status": "linked",
            "cluster_key": None,
            "ts_code": None,
            "url": "https://example.com/policy",
            "link_created_at": base_time - timedelta(hours=1),
        },
    ]

    selected = select_summary_analysis_events(
        events,
        anchor_event_id="anchor-old",
        total_limit=3,
    )

    assert [item["event_id"] for item in selected] == [
        "anchor-old",
        "duplicate-new",
        "policy-1",
    ]
