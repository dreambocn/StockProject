from datetime import date, datetime
from math import isnan

from app.schemas.stocks import StockDailySnapshotResponse


def _to_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and isnan(value):
        # Tushare 有时会返回 NaN，占位值需要显式转成空。
        return None

    normalized_value = str(value).strip()
    if not normalized_value:
        return None
    try:
        return float(normalized_value)
    except ValueError:
        return None


def _to_optional_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, float) and isnan(value):
        # NaN 代表缺失日期，避免影响后续排序与回写。
        return None

    normalized_value = str(value).strip()
    if not normalized_value:
        return None

    for format_value in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(normalized_value, format_value).date()  # noqa: DTZ007
        except ValueError:
            continue

    return None


def map_tushare_daily_row_to_snapshot_response(
    *,
    ts_code: str,
    row: dict[str, object],
) -> StockDailySnapshotResponse | None:
    trade_date = _to_optional_date(row.get("trade_date"))
    # 关键边界：trade_date 是行情时序主键，缺失时不能生成快照，
    # 否则会污染“最新交易日”判定和后续 upsert 行为。
    if trade_date is None:
        return None

    return StockDailySnapshotResponse(
        ts_code=ts_code,
        trade_date=trade_date,
        open=_to_optional_float(row.get("open")),
        high=_to_optional_float(row.get("high")),
        low=_to_optional_float(row.get("low")),
        close=_to_optional_float(row.get("close")),
        pre_close=_to_optional_float(row.get("pre_close")),
        change=_to_optional_float(row.get("change")),
        pct_chg=_to_optional_float(row.get("pct_chg")),
        vol=_to_optional_float(row.get("vol")),
        amount=_to_optional_float(row.get("amount")),
        turnover_rate=None,
        volume_ratio=None,
        pe=None,
        pb=None,
        total_mv=None,
        circ_mv=None,
    )
