from datetime import date

from app.services.stock_tushare_mapper import map_tushare_daily_row_to_snapshot_response


def test_map_tushare_daily_row_returns_snapshot_for_valid_row() -> None:
    mapped = map_tushare_daily_row_to_snapshot_response(
        ts_code="000001.SZ",
        row={
            "trade_date": "20260303",
            "open": "11.0",
            "high": 11.2,
            "low": 10.8,
            "close": 11.1,
            "pre_close": 10.95,
            "change": 0.15,
            "pct_chg": 1.37,
            "vol": 123456,
            "amount": 789012,
        },
    )

    assert mapped is not None
    assert mapped.ts_code == "000001.SZ"
    assert mapped.trade_date == date(2026, 3, 3)
    assert mapped.close == 11.1
    assert mapped.pct_chg == 1.37


def test_map_tushare_daily_row_returns_none_without_trade_date() -> None:
    mapped = map_tushare_daily_row_to_snapshot_response(
        ts_code="000001.SZ",
        row={
            "trade_date": "",
            "close": 11.1,
        },
    )

    assert mapped is None


def test_map_tushare_daily_row_supports_dashed_date_format() -> None:
    mapped = map_tushare_daily_row_to_snapshot_response(
        ts_code="000001.SZ",
        row={
            "trade_date": "2026-03-03",
            "close": "11.1",
        },
    )

    assert mapped is not None
    assert mapped.trade_date == date(2026, 3, 3)
    assert mapped.close == 11.1


def test_map_tushare_daily_row_filters_invalid_numeric_values() -> None:
    mapped = map_tushare_daily_row_to_snapshot_response(
        ts_code="000001.SZ",
        row={
            "trade_date": "20260303",
            "close": "not-a-number",
            "pct_chg": float("nan"),
        },
    )

    assert mapped is not None
    assert mapped.close is None
    assert mapped.pct_chg is None
