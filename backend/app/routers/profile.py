"""Profile conversation API endpoints.

Phase 3.6: Conversational 8-Dimensional Learner Profile

Endpoints:
  POST   /api/profile/conversations                        — create conversation
  GET    /api/profile/conversations/{session_id}            — get conversation state
  POST   /api/profile/conversations/{session_id}/messages   — send message
  POST   /api/profile/conversations/{session_id}/finalize   — finalize profile
  GET    /api/profile/me                                    — get current profile
  GET    /api/profile/me/evidence                           — get evidence records
  PATCH  /api/profile/me/dimensions                         — manual correction
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import ProfileEvidenceType
from app.core.auth_deps import require_learning_user
from app.core.database import get_db
from app.core.errors import ApiError
from app.models.user import User
from app.services.profile_conversation import ProfileConversationService

router = APIRouter()

# Type alias for the 8 profile dimensions (E0-A6)
ProfileDimension = Literal[
    "knowledge_depth",
    "prerequisite_mastery",
    "concept_grasp",
    "problem_solving",
    "practice_ability",
    "learning_pace",
    "resource_preference",
    "error_pattern",
]


# ──────────────────────────────────────────────
# Request / Response schemas
# ──────────────────────────────────────────────


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learning_goal: str = Field(..., min_length=1, max_length=2000)
    target_context: str | None = Field(None, max_length=500)
    learning_goal_id: str | None = None


class CreateConversationResponse(BaseModel):
    session_id: str
    status: str
    assistant_message: str


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=5000)


class SendMessageResponse(BaseModel):
    assistant_message: str
    extracted_dimensions: dict[str, Any]
    missing_dimensions: list[str]
    ready_to_finalize: bool


class FinalizeResponse(BaseModel):
    profile_id: str
    profile_version: int
    dimensions: dict[str, Any]
    summary: str
    confidence: float


class ProfileSummaryResponse(BaseModel):
    profile_id: str
    user_id: str
    status: str
    profile_version: int
    dimensions: dict[str, Any]
    summary: str | None
    confidence: float


class EvidenceResponse(BaseModel):
    evidence_id: str
    dimension: str
    evidence_type: str
    value: float
    confidence: float
    evidence_metadata: dict[str, Any] | None
    created_at: str


class ManualCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: ProfileDimension
    value: float | str | list[str] | dict[str, float]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str | None = Field(None, max_length=500)


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.post("/conversations", response_model=CreateConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> CreateConversationResponse:
    """Create a new profile conversation session."""
    service = ProfileConversationService(db)
    session = await service.create_session(
        user_id=user.id,
        learning_goal=request.learning_goal,
        learning_goal_id=request.learning_goal_id,
        target_context=request.target_context,
    )
    messages = await service.get_messages(session.id)
    first_message = messages[0] if messages else None

    return CreateConversationResponse(
        session_id=session.id,
        status=session.status,
        assistant_message=first_message.content if first_message else "",
    )


@router.get("/conversations/{session_id}")
async def get_conversation(
    session_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get conversation session state and messages."""
    service = ProfileConversationService(db)
    session = await service.get_session(session_id, user.id)
    if not session:
        raise ApiError(code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404)

    messages = await service.get_messages(session_id)

    return {
        "session_id": session.id,
        "status": session.status,
        "turn_count": session.turn_count,
        "extracted_dimensions": session.extracted_dimensions,
        "completion_score": session.completion_score,
        "ready_to_finalize": session.turn_count >= 3 and len(session.extracted_dimensions) >= 6,
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ],
    }


@router.post("/conversations/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> SendMessageResponse:
    """Send a message in a profile conversation and get the assistant response."""
    service = ProfileConversationService(db)
    session = await service.get_session(session_id, user.id)
    if not session:
        raise ApiError(code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404)

    if session.status != "active":
        raise ApiError(code="CONVERSATION_CLOSED", message="Conversation is not active", status_code=400)

    if session.turn_count >= 7:
        raise ApiError(code="MAX_TURNS_REACHED", message="Maximum turns reached", status_code=400)

    result = await service.process_message(session, request.message)

    return SendMessageResponse(**result)


@router.post("/conversations/{session_id}/finalize", response_model=FinalizeResponse)
async def finalize_conversation(
    session_id: str,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> FinalizeResponse:
    """Finalize a profile conversation and create/update the student profile."""
    service = ProfileConversationService(db)
    session = await service.get_session(session_id, user.id)
    if not session:
        raise ApiError(code="CONVERSATION_NOT_FOUND", message="Conversation not found", status_code=404)

    if session.status == "completed" and session.profile_id:
        # Idempotent: return existing profile
        profile = await service.get_profile(user.id)
        if profile:
            return FinalizeResponse(
                profile_id=profile.id,
                profile_version=profile.profile_version,
                dimensions=profile.dimensions,
                summary=profile.summary or "",
                confidence=profile.confidence,
            )

    if session.turn_count < 1:
        raise ApiError(code="INSUFFICIENT_TURNS", message="Need at least 1 turn to finalize", status_code=400)

    # E0-A5: Enforce finalize rules server-side
    if not ProfileConversationService.can_finalize(session):
        raise ApiError(
            code="PROFILE_NOT_READY",
            message="Need more conversation before finalizing profile",
            status_code=409,
        )

    profile = await service.finalize(session)

    return FinalizeResponse(
        profile_id=profile.id,
        profile_version=profile.profile_version,
        dimensions=profile.dimensions,
        summary=profile.summary or "",
        confidence=profile.confidence,
    )


@router.get("/me", response_model=ProfileSummaryResponse)
async def get_my_profile(
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileSummaryResponse:
    """Get the current user's profile."""
    service = ProfileConversationService(db)
    profile = await service.get_profile(user.id)
    if not profile:
        raise ApiError(code="PROFILE_NOT_FOUND", message="Profile not found", status_code=404)

    return ProfileSummaryResponse(
        profile_id=profile.id,
        user_id=profile.user_id,
        status=profile.status,
        profile_version=profile.profile_version,
        dimensions=profile.dimensions,
        summary=profile.summary,
        confidence=profile.confidence,
    )


@router.get("/me/evidence")
async def get_my_evidence(
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> list[EvidenceResponse]:
    """Get all evidence records for the current user's profile."""
    service = ProfileConversationService(db)
    evidence = await service.get_evidence(user.id)
    return [
        EvidenceResponse(
            evidence_id=e.id,
            dimension=e.dimension,
            evidence_type=e.evidence_type,
            value=e.value,
            confidence=e.confidence,
            evidence_metadata=e.evidence_metadata,
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in evidence
    ]


@router.patch("/me/dimensions", response_model=ProfileSummaryResponse)
async def manual_correction(
    request: ManualCorrectionRequest,
    user: User = Depends(require_learning_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileSummaryResponse:
    """Manually correct a profile dimension.

    Writes a manual_correction evidence record and updates the profile.
    """
    from sqlalchemy import select

    from app.models.profile import StudentProfile
    from app.models.user import StudentProfileEvidence

    # Get or create profile
    result = await db.execute(select(StudentProfile).where(StudentProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = StudentProfile(
            id=str(uuid.uuid4()),
            user_id=user.id,
            status="active",
            profile_version=0,
            dimensions={},
            confidence=0.0,
        )
        db.add(profile)
        await db.flush()

    # Update dimension with manual correction (high confidence)
    # E0-A2: copy-then-assign for JSON persistence
    numeric_value = float(request.value) if isinstance(request.value, (int, float)) else 0.0
    dims = dict(profile.dimensions or {})
    dims[request.dimension] = {
        "value": request.value,
        "confidence": request.confidence,
        "source": "manual_correction",
    }
    profile.dimensions = dims
    profile.profile_version += 1

    # Write evidence record
    evidence = StudentProfileEvidence(
        id=str(uuid.uuid4()),
        user_id=user.id,
        dimension=request.dimension,
        evidence_type=ProfileEvidenceType.MANUAL_CORRECTION.value,
        evidence_id=str(uuid.uuid4()),
        value=numeric_value,
        confidence=request.confidence,
        evidence_metadata={
            "reason": request.reason,
            "raw_value": request.value,
        },
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(profile)

    return ProfileSummaryResponse(
        profile_id=profile.id,
        user_id=profile.user_id,
        status=profile.status,
        profile_version=profile.profile_version,
        dimensions=profile.dimensions,
        summary=profile.summary,
        confidence=profile.confidence,
    )
