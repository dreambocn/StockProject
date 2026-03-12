from datetime import date

import pytest

from app.services.stock_query_policy import (
    parse_is_open,
    parse_period,
    resolve_calendar_date_range,
    resolve_tushare_kline_date_range,
    to_adj_factor_cache_key,
    to_trade_cal_cache_key,
    to_tushare_daily_cache_key,
)


def test_parse_period_accepts_supported_values() -> None:
    assert (
        parse_period(" daily ", supported_periods=("daily", "weekly", "monthly"))
        == "daily"
    )
    assert (
        parse_period("WEEKLY", supported_periods=("daily", "weekly", "monthly"))
        == "weekly"
    )


def test_parse_period_rejects_invalid_value() -> None:
    with pytest.raises(ValueError) as exc_info:
        parse_period("yearly", supported_periods=("daily", "weekly", "monthly"))

    assert str(exc_info.value) == "invalid period, expected daily, weekly, or monthly"


def test_parse_is_open_normalizes_and_validates() -> None:
    assert parse_is_open(None) is None
    assert parse_is_open("") is None
    assert parse_is_open(" 1 ") == "1"

    with pytest.raises(ValueError) as exc_info:
        parse_is_open("2")

    assert str(exc_info.value) == "invalid is_open, expected 0 or 1"


def test_resolve_calendar_date_range_defaults_and_validation() -> None:
    start_date, end_date = resolve_calendar_date_range(
        start_date=None,
        end_date=None,
        today=date(2026, 3, 7),
    )

    assert start_date == "20250131"
    assert end_date == "20260307"

    with pytest.raises(ValueError) as exc_info:
        resolve_calendar_date_range(
            start_date="20260308",
            end_date="20260307",
            today=date(2026, 3, 7),
        )

    assert str(exc_info.value) == "start_date must be earlier than or equal to end_date"


def test_resolve_tushare_kline_date_range_supports_trade_date() -> None:
    start_date, end_date = resolve_tushare_kline_date_range(
        limit=60,
        trade_date="20260303",
        start_date=None,
        end_date=None,
        today=date(2026, 3, 7),
    )

    assert start_date == "20260303"
    assert end_date == "20260303"


def test_resolve_tushare_kline_date_range_defaults_with_limit_window() -> None:
    start_date, end_date = resolve_tushare_kline_date_range(
        limit=10,
        trade_date=None,
        start_date=None,
        end_date=None,
        today=date(2026, 3, 7),
    )

    assert start_date == "20260205"
    assert end_date == "20260307"


def test_cache_key_builders_generate_stable_keys() -> None:
    assert (
        to_trade_cal_cache_key(
            prefix="stocks:trade_cal:tushare",
            exchange="SSE",
            start_date="20260301",
            end_date="20260305",
            is_open="1",
        )
        == "stocks:trade_cal:tushare:SSE:20260301:20260305:1"
    )
    assert (
        to_adj_factor_cache_key(
            prefix="stocks:adj_factor:tushare",
            ts_code="000001.SZ",
            start_date="20260301",
            end_date="20260305",
            limit=240,
            trade_date=None,
        )
        == "stocks:adj_factor:tushare:000001.SZ:20260301:20260305:240:ALL"
    )
    assert (
        to_tushare_daily_cache_key(
            prefix="stocks:daily:tushare",
            ts_code="000001.SZ",
            period="daily",
            start_date="20260301",
            end_date="20260305",
            limit=60,
        )
        == "stocks:daily:tushare:000001.SZ:daily:20260301:20260305:60"
    )
