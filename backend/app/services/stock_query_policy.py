from datetime import date, datetime, timedelta


def _parse_yyyymmdd(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()  # noqa: DTZ007
    except ValueError as exc:
        raise ValueError("invalid date format, expected YYYYMMDD") from exc


def parse_period(value: str, *, supported_periods: tuple[str, ...]) -> str:
    normalized_value = value.strip().lower()
    if normalized_value in supported_periods:
        return normalized_value
    raise ValueError("invalid period, expected daily, weekly, or monthly")


def parse_is_open(value: str | None) -> str | None:
    if value is None:
        return None
    normalized_value = value.strip()
    if not normalized_value:
        return None
    if normalized_value in {"0", "1"}:
        return normalized_value
    raise ValueError("invalid is_open, expected 0 or 1")


def resolve_calendar_date_range(
    *,
    start_date: str | None,
    end_date: str | None,
    today: date | None = None,
) -> tuple[str, str]:
    resolved_today = today or date.today()
    resolved_end = _parse_yyyymmdd(end_date) if end_date else resolved_today
    resolved_start = (
        _parse_yyyymmdd(start_date)
        if start_date
        else resolved_end - timedelta(days=400)
    )
    if resolved_start > resolved_end:
        raise ValueError("start_date must be earlier than or equal to end_date")

    return resolved_start.strftime("%Y%m%d"), resolved_end.strftime("%Y%m%d")


def resolve_tushare_kline_date_range(
    *,
    limit: int,
    trade_date: str | None,
    start_date: str | None,
    end_date: str | None,
    today: date | None = None,
) -> tuple[str, str]:
    if trade_date:
        trade_day = _parse_yyyymmdd(trade_date)
        resolved = trade_day.strftime("%Y%m%d")
        return resolved, resolved

    resolved_today = today or date.today()
    resolved_end = _parse_yyyymmdd(end_date) if end_date else resolved_today
    resolved_start = (
        _parse_yyyymmdd(start_date)
        if start_date
        else resolved_end - timedelta(days=limit * 3)
    )

    # 关键边界：开始日大于结束日属于无效查询窗口，必须在参数层直接失败，
    # 避免带着错误时间范围进入 DB/三方调用链。
    if resolved_start > resolved_end:
        raise ValueError("start_date must be earlier than or equal to end_date")

    return resolved_start.strftime("%Y%m%d"), resolved_end.strftime("%Y%m%d")


def to_trade_cal_cache_key(
    *,
    prefix: str,
    exchange: str,
    start_date: str,
    end_date: str,
    is_open: str | None,
) -> str:
    cache_is_open = is_open or "ALL"
    return f"{prefix}:{exchange}:{start_date}:{end_date}:{cache_is_open}"


def to_adj_factor_cache_key(
    *,
    prefix: str,
    ts_code: str,
    start_date: str,
    end_date: str,
    limit: int,
    trade_date: str | None,
) -> str:
    cache_trade_date = trade_date or "ALL"
    return f"{prefix}:{ts_code}:{start_date}:{end_date}:{limit}:{cache_trade_date}"


def to_tushare_daily_cache_key(
    *,
    prefix: str,
    ts_code: str,
    period: str,
    start_date: str,
    end_date: str,
    limit: int,
) -> str:
    return f"{prefix}:{ts_code}:{period}:{start_date}:{end_date}:{limit}"
