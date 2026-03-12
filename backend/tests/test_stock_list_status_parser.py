import pytest

from app.services.stock_list_status import (
    STOCK_BASIC_STATUSES,
    parse_stock_list_status_filter,
)


def test_parser_defaults_to_listed_for_public_stocks() -> None:
    parsed = parse_stock_list_status_filter(
        "",
        all_statuses=STOCK_BASIC_STATUSES,
        default_statuses=("L",),
    )

    assert parsed == ["L"]


def test_parser_defaults_to_all_for_admin_stocks() -> None:
    parsed = parse_stock_list_status_filter(
        "",
        all_statuses=STOCK_BASIC_STATUSES,
        default_statuses=STOCK_BASIC_STATUSES,
    )

    assert parsed == ["L", "D", "P", "G"]


def test_parser_supports_all_keyword() -> None:
    parsed = parse_stock_list_status_filter(
        "ALL",
        all_statuses=STOCK_BASIC_STATUSES,
        default_statuses=("L",),
    )

    assert parsed == ["L", "D", "P", "G"]


def test_parser_deduplicates_and_preserves_order() -> None:
    parsed = parse_stock_list_status_filter(
        "d,l,d,p",
        all_statuses=STOCK_BASIC_STATUSES,
        default_statuses=("L",),
    )

    assert parsed == ["D", "L", "P"]


def test_parser_rejects_invalid_status() -> None:
    with pytest.raises(ValueError) as exc_info:
        parse_stock_list_status_filter(
            "L,X",
            all_statuses=STOCK_BASIC_STATUSES,
            default_statuses=("L",),
        )

    assert str(exc_info.value) == (
        "invalid list_status, expected ALL or comma-separated values in L,D,P,G"
    )
