from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_theme import MarketTheme
from app.models.market_theme_membership import MarketThemeMembership


async def list_stock_themes(
    session: AsyncSession,
    *,
    ts_code: str,
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            select(MarketThemeMembership, MarketTheme)
            .join(MarketTheme, MarketTheme.id == MarketThemeMembership.theme_id)
            .where(MarketThemeMembership.ts_code == ts_code.strip().upper())
            .order_by(
                MarketThemeMembership.match_score.desc(),
                MarketTheme.theme_name.asc(),
            )
        )
    ).all()

    items: list[dict[str, object]] = []
    for membership, theme in rows:
        raw_evidence = membership.evidence_json or []
        theme_evidence = [
            str(item.get("text"))
            for item in raw_evidence
            if isinstance(item, dict) and item.get("text")
        ]
        if not theme_evidence:
            theme_evidence = [str(item) for item in raw_evidence if isinstance(item, str)]

        items.append(
            {
                "theme_code": theme.theme_code,
                "theme_name": theme.theme_name,
                "theme_type": theme.theme_type,
                "match_score": membership.match_score,
                "evidence_summary": membership.evidence_summary,
                "theme_evidence": theme_evidence[:3],
            }
        )
    return items


async def attach_theme_matches_to_profiles(
    session: AsyncSession,
    *,
    profiles: list[dict[str, object]],
) -> list[dict[str, object]]:
    ts_codes = sorted(
        {
            str(candidate.get("ts_code") or "").strip().upper()
            for profile in profiles
            for candidate in (profile.get("a_share_candidates") or [])
            if str(candidate.get("ts_code") or "").strip()
        }
    )
    if not ts_codes:
        return profiles

    rows = (
        await session.execute(
            select(MarketThemeMembership, MarketTheme)
            .join(MarketTheme, MarketTheme.id == MarketThemeMembership.theme_id)
            .where(MarketThemeMembership.ts_code.in_(ts_codes))
            .order_by(
                MarketThemeMembership.ts_code.asc(),
                MarketThemeMembership.match_score.desc(),
                MarketTheme.theme_name.asc(),
            )
        )
    ).all()

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for membership, theme in rows:
        raw_evidence = membership.evidence_json or []
        theme_evidence = [
            str(item.get("text"))
            for item in raw_evidence
            if isinstance(item, dict) and item.get("text")
        ]
        if not theme_evidence and membership.evidence_summary:
            theme_evidence = [membership.evidence_summary]

        grouped[membership.ts_code].append(
            {
                "theme_name": theme.theme_name,
                "theme_evidence": theme_evidence[:2],
            }
        )

    for profile in profiles:
        for candidate in profile.get("a_share_candidates") or []:
            ts_code = str(candidate.get("ts_code") or "").strip().upper()
            theme_items = grouped.get(ts_code, [])
            candidate["theme_matches"] = [
                str(item["theme_name"])
                for item in theme_items[:3]
            ]
            evidence_lines: list[str] = []
            for item in theme_items[:2]:
                evidence_lines.extend(
                    str(text) for text in item.get("theme_evidence") or [] if text
                )
            candidate["theme_evidence"] = evidence_lines[:3]
    return profiles
