from app.services.stock_sync_service import STOCK_BASIC_FULL_STATUSES


STOCK_BASIC_STATUSES: tuple[str, ...] = STOCK_BASIC_FULL_STATUSES
_INVALID_STATUS_DETAIL = (
    "invalid list_status, expected ALL or comma-separated values in L,D,P,G"
)


def parse_stock_list_status_filter(
    value: str,
    *,
    all_statuses: tuple[str, ...] = STOCK_BASIC_STATUSES,
    default_statuses: tuple[str, ...] = ("L",),
) -> list[str]:
    normalized_value = value.strip().upper()
    if not normalized_value:
        return list(default_statuses)
    if normalized_value == "ALL":
        return list(all_statuses)

    parsed: list[str] = []
    seen: set[str] = set()
    for raw_status in normalized_value.split(","):
        status_value = raw_status.strip()[:1]
        if status_value not in all_statuses:
            raise ValueError(_INVALID_STATUS_DETAIL)
        if status_value in seen:
            continue
        seen.add(status_value)
        parsed.append(status_value)

    return parsed or list(default_statuses)
