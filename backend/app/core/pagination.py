"""Cursor-based pagination utilities."""

from __future__ import annotations

import base64
import json
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError


def encode_cursor(data: dict[str, Any]) -> str:
    """Encode cursor data into a base64 string.

    The cursor encodes stable sort fields (e.g. created_at, id) to avoid
    exposing raw database IDs.
    """
    json_str = json.dumps(data, sort_keys=True, default=str)
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a base64 cursor string back to data."""
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(json_str)  # type: ignore[no-any-return]
    except (ValueError, json.JSONDecodeError) as e:
        raise ApiError(
            code="INVALID_CURSOR",
            message="The provided cursor is invalid",
            status_code=400,
        ) from e


async def paginate_query(
    db: AsyncSession,
    query: Select[Any],
    cursor: str | None,
    limit: int,
    order_column: Any,
    id_column: Any,
    model_class: Any,
) -> dict[str, Any]:
    """Execute a paginated query with cursor support.

    Args:
        db: Database session
        query: Base SQLAlchemy select query
        cursor: Optional cursor string for pagination
        limit: Maximum number of items to return
        order_column: Column to sort by (e.g. created_at)
        id_column: ID column for tie-breaking
        model_class: ORM model class

    Returns:
        Dict with items, next_cursor, and total
    """
    if limit < 1 or limit > 100:
        limit = 20

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply cursor filter
    if cursor:
        cursor_data = decode_cursor(cursor)
        cursor_order = cursor_data.get("order")
        cursor_id = cursor_data.get("id")
        if cursor_order is not None and cursor_id is not None:
            query = query.where(
                (order_column < cursor_order) | ((order_column == cursor_order) & (id_column < cursor_id))
            )

    # Apply ordering and limit
    query = query.order_by(order_column.desc(), id_column.desc())
    query = query.limit(limit + 1)  # Fetch one extra to determine if there's a next page

    result = await db.execute(query)
    rows = list(result.scalars().all())

    # Determine next cursor
    has_next = len(rows) > limit
    if has_next:
        rows = rows[:limit]
        last_row = rows[-1]
        next_cursor = encode_cursor(
            {
                "order": str(getattr(last_row, order_column.name)),
                "id": str(getattr(last_row, id_column.name)),
            }
        )
    else:
        next_cursor = None

    return {
        "items": rows,
        "next_cursor": next_cursor,
        "total": total,
    }
