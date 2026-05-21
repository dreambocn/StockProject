def resolve_generation_event_limit(settings: object, fallback_limit: int) -> int:
    raw_limit = getattr(settings, "analysis_generation_event_limit", fallback_limit)
    try:
        resolved_limit = int(raw_limit)
    except (TypeError, ValueError):
        resolved_limit = fallback_limit
    return max(1, resolved_limit)
