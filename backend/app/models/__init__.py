"""Database models."""

from app.models.clarification import ClarificationAnswer, ClarificationQuestion, ClarificationSet
from app.models.diagnostic import DiagnosticAnswer, DiagnosticAttempt, DiagnosticQuestion, DiagnosticResult
from app.models.goal import LearningGoal
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.path import (
    LearningEdge,
    LearningNode,
    LearningPath,
    LearningPathRevisionRequest,
    LearningPathVersion,
    LearningStage,
)
from app.models.profile import ProfileConversationMessage, ProfileConversationSession, StudentProfile
from app.models.progress import LearningProgress, MasterySnapshot, Recommendation, RecommendationFeedback
from app.models.task import BackgroundTask, TaskEvent
from app.models.unit import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentQuestion,
    LearningUnitContent,
)
from app.models.user import (
    AuthAuditLog,
    AuthSession,
    RefreshToken,
    StudentProfileEvidence,
    User,
    UserProfile,
    VerificationToken,
)

__all__ = [
    # User & Auth
    "User",
    "UserProfile",
    "AuthSession",
    "RefreshToken",
    "VerificationToken",
    "AuthAuditLog",
    # Goals
    "LearningGoal",
    "Recommendation",
    # Diagnostic
    "DiagnosticQuestion",
    "DiagnosticAttempt",
    "DiagnosticAnswer",
    "DiagnosticResult",
    # Tasks
    "BackgroundTask",
    "TaskEvent",
    # Paths
    "LearningPath",
    "LearningPathVersion",
    "LearningStage",
    "LearningNode",
    "LearningEdge",
    "LearningPathRevisionRequest",
    # Progress
    "LearningProgress",
    "MasterySnapshot",
    "RecommendationFeedback",
    # Unit
    "Assessment",
    "AssessmentQuestion",
    "AssessmentAttempt",
    "AssessmentAnswer",
    "LearningUnitContent",
    # Knowledge
    "KnowledgeDocument",
    "KnowledgeChunk",
    # Clarification
    "ClarificationSet",
    "ClarificationQuestion",
    "ClarificationAnswer",
    "StudentProfileEvidence",
    # Profile (Phase 3.6)
    "StudentProfile",
    "ProfileConversationSession",
    "ProfileConversationMessage",
]
