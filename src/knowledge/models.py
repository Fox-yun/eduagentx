from pydantic import BaseModel, Field
from typing import Optional, List

class KnowledgeDocumentInternal(BaseModel):
    document_id: str
    user_id: str
    course_id: Optional[str] = None
    conversation_id: Optional[str] = None
    scope: str = 'personal'
    original_filename: str
    display_name: Optional[str] = None
    stored_path: str
    mime_type: Optional[str] = None
    file_extension: Optional[str] = None
    file_size: int
    sha256: str
    status: str
    page_count: int = 0
    chunk_count: int = 0
    error: Optional[str] = None
    created_at: float
    updated_at: float
    indexed_at: Optional[float] = None
    deleted_at: Optional[float] = None

class KnowledgeDocumentResponse(BaseModel):
    document_id: str
    user_id: str
    course_id: Optional[str] = None
    conversation_id: Optional[str] = None
    scope: str = 'personal'
    original_filename: str
    display_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_extension: Optional[str] = None
    file_size: int
    status: str
    page_count: int = 0
    chunk_count: int = 0
    error: Optional[str] = None
    created_at: float
    updated_at: float
    indexed_at: Optional[float] = None
    # Joined index task fields
    index_task_id: Optional[str] = None
    index_status: Optional[str] = None
    index_progress: Optional[int] = None
    index_stage: Optional[str] = None
    index_error: Optional[str] = None

class KnowledgeIndexTaskSchema(BaseModel):
    index_task_id: str
    document_id: str
    status: str
    progress: int = 0
    current_stage: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    heartbeat_at: Optional[float] = None
    worker_id: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    cancel_requested_at: Optional[float] = None
    target_index_version: int = 1
    created_at: float
    updated_at: float

class KnowledgeChunkSchema(BaseModel):
    chunk_id: str
    document_id: str
    vector_id: str
    page_number: Optional[int] = None
    chunk_index: int
    content_hash: Optional[str] = None
    index_version: int = 1
    created_at: float

class DocumentUploadResponse(BaseModel):
    document_id: str
    index_task_id: str
    status: str
    message: str

class DocumentListResponse(BaseModel):
    items: List[KnowledgeDocumentResponse]
    total: int
    page: int
    page_size: int

class IndexTaskStatusResponse(BaseModel):
    status: str
    progress: int
    current_stage: Optional[str] = None
    error: Optional[str] = None
