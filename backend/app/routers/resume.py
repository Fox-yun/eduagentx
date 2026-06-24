"""Resume API endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.user import User
from app.services.resume import ResumeService

router = APIRouter()


@router.get("")
async def get_resume(
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the resume state for the current user.

    Returns one of five states:
    - empty: No learning activity
    - generating: A task is in progress
    - review: A path is ready for review
    - active: A path is active (learning in progress)
    - completed: A path has been completed
    """
    service = ResumeService(db)
    return await service.get_resume(user.id)
