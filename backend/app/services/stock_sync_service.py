from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.job_service import (
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCESS,
    create_job_run,
    finish_job_run,
)
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.models.stock_sync_cursor import StockSyncCursor


STOCK_BASIC_FULL_STATUSES: tuple[str, ...] = ("L", "D", "P", "G")


class StockDataGateway(Protocol):
    async def fetch_stock_basic_by_status(
        self, list_status: str
    ) -> list[dict[str, str]]: ...

    async def fetch_recent_open_trade_dates(self, limit: int) -> list[str]: ...

    async def fetch_daily_for_trade_date(
        self, trade_date: str
    ) -> list[dict[str, str | float]]: ...

    async def fetch_daily_basic_for_trade_date(
        self, trade_date: str
    ) -> list[dict[str, str | float]]: ...


def _parse_yyyymmdd(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y%m%d").date()  # noqa: DTZ007


def _as_decimal(value: str | float | int | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


async def _upsert_stock_instrument(
    session: AsyncSession, payload: dict[str, str]
) -> str:
    ts_code = str(payload["ts_code"]).strip().upper()
    # 主键按 ts_code 归一化，避免大小写/空格导致重复记录。
    instrument = await session.get(StockInstrument, ts_code)
    is_created = instrument is None
    if instrument is None:
        instrument = StockInstrument(ts_code=ts_code, symbol="-", name="-")
        session.add(instrument)

    instrument.symbol = str(payload.get("symbol") or "").strip()
    instrument.name = str(payload.get("name") or "").strip()
    instrument.area = str(payload.get("area") or "").strip() or None
    instrument.industry = str(payload.get("industry") or "").strip() or None
    instrument.fullname = str(payload.get("fullname") or "").strip() or None
    instrument.enname = str(payload.get("enname") or "").strip() or None
    instrument.cnspell = str(payload.get("cnspell") or "").strip() or None
    instrument.market = str(payload.get("market") or "").strip() or None
    instrument.exchange = str(payload.get("exchange") or "").strip() or None
    instrument.curr_type = str(payload.get("curr_type") or "").strip() or None
    instrument.list_status = (
        str(payload.get("list_status") or "L").strip().upper()[:1] or "L"
    )
    instrument.list_date = _parse_yyyymmdd(payload.get("list_date"))
    instrument.delist_date = _parse_yyyymmdd(payload.get("delist_date"))
    instrument.is_hs = str(payload.get("is_hs") or "").strip() or None
    instrument.act_name = str(payload.get("act_name") or "").strip() or None
    instrument.act_ent_type = str(payload.get("act_ent_type") or "").strip() or None
    return "created" if is_created else "updated"


async def _upsert_daily_snapshot(
    session: AsyncSession,
    daily_payload: dict[str, str | float],
    daily_basic_payload: dict[str, str | float] | None,
) -> None:
    ts_code = str(daily_payload["ts_code"]).strip().upper()
    trade_date = _parse_yyyymmdd(str(daily_payload["trade_date"]))
    if trade_date is None:
        return

    snapshot = await session.get(StockDailySnapshot, (ts_code, trade_date))
    if snapshot is None:
        snapshot = StockDailySnapshot(ts_code=ts_code, trade_date=trade_date)
        session.add(snapshot)

    snapshot.open = _as_decimal(daily_payload.get("open"))
    snapshot.high = _as_decimal(daily_payload.get("high"))
    snapshot.low = _as_decimal(daily_payload.get("low"))
    snapshot.close = _as_decimal(daily_payload.get("close"))
    snapshot.pre_close = _as_decimal(daily_payload.get("pre_close"))
    snapshot.change = _as_decimal(daily_payload.get("change"))
    snapshot.pct_chg = _as_decimal(daily_payload.get("pct_chg"))
    snapshot.vol = _as_decimal(daily_payload.get("vol"))
    snapshot.amount = _as_decimal(daily_payload.get("amount"))
    if daily_basic_payload:
        # 关键业务分支：仅当 daily_basic 可用时才补充估值字段，避免因缺失覆盖已有有效数据。
        snapshot.turnover_rate = _as_decimal(daily_basic_payload.get("turnover_rate"))
        snapshot.volume_ratio = _as_decimal(daily_basic_payload.get("volume_ratio"))
        snapshot.pe = _as_decimal(daily_basic_payload.get("pe"))
        snapshot.pb = _as_decimal(daily_basic_payload.get("pb"))
        snapshot.total_mv = _as_decimal(daily_basic_payload.get("total_mv"))
        snapshot.circ_mv = _as_decimal(daily_basic_payload.get("circ_mv"))


async def _upsert_cursor(session: AsyncSession, key: str, value: str) -> None:
    cursor = await session.get(StockSyncCursor, key)
    if cursor is None:
        cursor = StockSyncCursor(cursor_key=key, cursor_value=value)
        session.add(cursor)
        return

    cursor.cursor_value = value


def _normalize_status_list(
    list_statuses: tuple[str, ...] | list[str] | None,
) -> list[str]:
    if list_statuses is None:
        return list(STOCK_BASIC_FULL_STATUSES)

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_status in list_statuses:
        status = raw_status.strip().upper()[:1]
        if not status or status in seen:
            continue
        if status not in STOCK_BASIC_FULL_STATUSES:
            continue
        seen.add(status)
        normalized.append(status)

    if normalized:
        return normalized

    # 全部无效时回退到全量状态，避免“空同步”造成误判。
    return list(STOCK_BASIC_FULL_STATUSES)


async def _sync_stock_basic_rows(
    session: AsyncSession,
    gateway: StockDataGateway,
    list_statuses: tuple[str, ...] | list[str] | None = None,
) -> dict[str, int | list[str]]:
    statuses = _normalize_status_list(list_statuses)
    merged_by_code: dict[str, dict[str, str]] = {}

    for status in statuses:
        stock_rows = await gateway.fetch_stock_basic_by_status(status)
        for row in stock_rows:
            ts_code = str(row.get("ts_code") or "").strip().upper()
            if not ts_code:
                continue
            # 按 ts_code 覆盖合并多状态行，确保同一标的只写入一次。
            merged_by_code[ts_code] = row

    created_count = 0
    updated_count = 0
    for row in merged_by_code.values():
        result = await _upsert_stock_instrument(session, row)
        if result == "created":
            created_count += 1
        else:
            updated_count += 1

    return {
        "total": len(merged_by_code),
        "created": created_count,
        "updated": updated_count,
        "list_statuses": statuses,
    }


async def sync_stock_basic_full(
    session: AsyncSession,
    gateway: StockDataGateway,
    list_statuses: tuple[str, ...] | list[str] | None = None,
) -> dict[str, int | list[str]]:
    normalized_statuses = _normalize_status_list(list_statuses)
    job = await create_job_run(
        session,
        job_type="stock_sync_full",
        status=JOB_STATUS_RUNNING,
        trigger_source="admin.stocks.full",
        resource_type="stock_basic",
        resource_key=",".join(normalized_statuses),
        summary="股票主数据全量同步执行中",
        payload_json={"list_statuses": normalized_statuses},
    )
    # 全量同步结束后记录游标，作为后续排障与增量的时间基准。
    try:
        summary = await _sync_stock_basic_rows(
            session,
            gateway,
            list_statuses=normalized_statuses,
        )
        await _upsert_cursor(
            session,
            "stock_basic_last_sync",
            datetime.now(UTC).replace(microsecond=0).isoformat(),
        )
        await finish_job_run(
            session,
            job=job,
            status=JOB_STATUS_SUCCESS,
            summary="股票主数据全量同步完成",
            metrics_json={
                "total": int(summary["total"]),
                "created": int(summary["created"]),
                "updated": int(summary["updated"]),
                "list_statuses": list(summary["list_statuses"]),
            },
        )
        await session.commit()
        return summary
    except Exception as exc:
        await finish_job_run(
            session,
            job=job,
            status=JOB_STATUS_FAILED,
            summary="股票主数据全量同步失败",
            error_type=type(exc).__name__,
            error_message=str(exc),
            metrics_json={"list_statuses": normalized_statuses},
        )
        await session.commit()
        raise


async def sync_recent_trade_days(
    session: AsyncSession,
    gateway: StockDataGateway,
    trade_days: int = 120,
) -> None:
    # 关键流程：先全量同步股票主数据（L/D/P/G），再同步日线快照，保证外键引用的股票代码先存在。
    await _sync_stock_basic_rows(
        session, gateway, list_statuses=STOCK_BASIC_FULL_STATUSES
    )

    # 增量策略：仅拉取最近 N 个交易日，控制首次接入成本与同步时延。
    trade_dates = await gateway.fetch_recent_open_trade_dates(limit=trade_days)
    for trade_date in trade_dates:
        daily_rows = await gateway.fetch_daily_for_trade_date(trade_date)
        daily_basic_rows = await gateway.fetch_daily_basic_for_trade_date(trade_date)
        daily_basic_map = {
            str(item["ts_code"]).strip().upper(): item for item in daily_basic_rows
        }
        for daily_row in daily_rows:
            ts_code = str(daily_row["ts_code"]).strip().upper()
            await _upsert_daily_snapshot(
                session, daily_row, daily_basic_map.get(ts_code)
            )

    # 同步游标是后续增量/排障的状态边界，必须在同一事务内与数据一起提交。
    if trade_dates:
        await _upsert_cursor(session, "daily_latest_trade_date", trade_dates[0])
    await _upsert_cursor(
        session,
        "stock_basic_last_sync",
        datetime.now(UTC).replace(microsecond=0).isoformat(),
    )
    await session.commit()
