ACTIVE_STATUSES = frozenset({
    "pending",
    "running",
    "cancel_requested",
})

TERMINAL_STATUSES = frozenset({
    "completed",
    "partial_completed",
    "failed",
    "cancelled",
    "interrupted",
    "expired",
})


def is_terminal_status(status: str | None) -> bool:
    return status in TERMINAL_STATUSES


def is_active_status(status: str | None) -> bool:
    return status in ACTIVE_STATUSES
