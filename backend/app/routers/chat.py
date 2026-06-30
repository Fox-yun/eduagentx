"""Chat / Q&A tutor API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.models.user import User
from app.services.tutor import TutorService

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    node_id: str
    path_id: str


@router.post("")
async def chat(
    body: ChatRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ask a question about a learning node (tutor agent)."""
    service = TutorService(db)
    return await service.ask(
        path_id=body.path_id,
        node_id=body.node_id,
        user_id=user.id,
        question=body.question,
    )
