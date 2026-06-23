import os
import uuid
import time
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from src.knowledge.models import (
    DocumentUploadResponse,
    DocumentListResponse,
    IndexTaskStatusResponse,
    KnowledgeDocumentResponse
)
from src.knowledge.repository import (
    create_knowledge_document,
    get_knowledge_document,
    list_knowledge_documents,
    create_index_task,
    get_index_task,
    update_knowledge_document,
    claim_document_for_deletion,
    claim_document_for_reindex
)
from src.knowledge.storage import save_upload_stream, delete_file
from src.knowledge.service import submit_index_task, delete_document_completely
from src.db.database import get_connection

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "uploads")

@router.post("/documents", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    course_id: str | None = Form(None),
    scope: str = Form('personal'),
    conversation_id: str | None = Form(None)
):
    if scope not in {"personal", "session"}:
        raise HTTPException(status_code=400, detail="不支持的资料范围")

    if scope == "session" and not conversation_id:
        raise HTTPException(status_code=400, detail="当前会话资料必须提供 conversation_id")

    if scope == "personal":
        conversation_id = None
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.pdf', '.txt', '.md']:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
        
    document_id = str(uuid.uuid4())
    stored_path = os.path.join(UPLOAD_DIR, document_id + ext)
    
    # Save file and calculate hash streamingly
    try:
        async def file_stream():
            while chunk := await file.read(8192):
                yield chunk
        
        sha256_hex, file_size = await save_upload_stream(file_stream(), stored_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
        
    # Check if this user already has this exact file
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT document_id FROM knowledge_documents WHERE user_id = ? AND sha256 = ? AND status != 'deleted'",
            (user_id, sha256_hex)
        )
        existing = cursor.fetchone()
        if existing:
            # Clean up the file we just saved since it's a duplicate
            delete_file(stored_path)
            raise HTTPException(status_code=409, detail="Document already exists for this user")
            
    now = time.time()
    doc_data = {
        "document_id": document_id,
        "user_id": user_id,
        "course_id": course_id,
        "conversation_id": conversation_id,
        "scope": scope,
        "original_filename": file.filename,
        "display_name": file.filename,
        "stored_path": stored_path,
        "mime_type": file.content_type,
        "file_extension": ext,
        "file_size": file_size,
        "sha256": sha256_hex,
        "status": "pending",
        "created_at": now,
        "updated_at": now
    }
    create_knowledge_document(doc_data)
    
    index_task_id = str(uuid.uuid4())
    task_data = {
        "index_task_id": index_task_id,
        "document_id": document_id,
        "status": "pending",
        "progress": 0,
        "current_stage": "等待开始",
        "target_index_version": 1,
        "created_at": now,
        "updated_at": now
    }
    create_index_task(task_data)
    
    # Submit task to background worker pool
    submit_index_task(index_task_id, document_id)
    
    return DocumentUploadResponse(
        document_id=document_id,
        index_task_id=index_task_id,
        status="pending",
        message="Document uploaded and queued for indexing"
    )

@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    user_id: str,
    course_id: str = None,
    scope: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20
):
    offset = (page - 1) * page_size
    docs, total = list_knowledge_documents(
        user_id=user_id,
        course_id=course_id,
        scope=scope,
        status=status,
        limit=page_size,
        offset=offset
    )
    
    # We do not return stored_path and sha256 to client. The Repository will return dict, and FastAPI response_model will filter it if using KnowledgeDocumentResponse, but we should make sure schema is satisfied.
    return DocumentListResponse(
        items=docs,
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/documents/{document_id}", response_model=KnowledgeDocumentResponse)
def get_document(document_id: str, user_id: str):
    doc = get_knowledge_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if doc["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Permission denied: not owner")
        
    return doc

@router.delete("/documents/{document_id}")
def delete_document(document_id: str, user_id: str, background_tasks: BackgroundTasks):
    doc = get_knowledge_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if doc["scope"] == "system":
        raise HTTPException(status_code=403, detail="系统资料不能由普通用户删除")

    if doc["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Permission denied: not owner")
        
    if not claim_document_for_deletion(document_id, user_id):
        raise HTTPException(status_code=409, detail="资料正在建立索引，暂时不能删除")
        
    background_tasks.add_task(delete_document_completely, document_id)
    return {"message": "Document deletion scheduled"}

@router.get("/tasks/{index_task_id}", response_model=IndexTaskStatusResponse)
def get_index_task_status(index_task_id: str, user_id: str):
    task = get_index_task(index_task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    doc = get_knowledge_document(task["document_id"])
    if doc and doc["user_id"] != user_id and doc["scope"] != "system":
        raise HTTPException(status_code=403, detail="Permission denied")
        
    return IndexTaskStatusResponse(
        status=task["status"],
        progress=task["progress"],
        current_stage=task["current_stage"],
        error=task["error"]
    )

@router.post("/documents/{document_id}/reindex")
def reindex_document(document_id: str, user_id: str):
    doc = get_knowledge_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if doc["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Permission denied: not owner")
        
    if not claim_document_for_reindex(document_id, user_id):
        raise HTTPException(status_code=409, detail="索引任务正在进行中，无法重新索引")
        
    now = time.time()
    
    # We DO NOT delete old vectors/chunks here.
    # The worker will bump active_index_version upon success, 
    # and asynchronously clean up the old versions.
    
    # Update document status to indicate it is pending reindex tasks
    # claim_document_for_reindex already set it to 'reindexing'
    # but we can refresh the updated_at time.
    update_knowledge_document(document_id, {
        "error": None,
        "updated_at": now
    })
    
    # Create new task
    index_task_id = str(uuid.uuid4())
    target_version = doc.get("active_index_version", 0) + 1
    task_data = {
        "index_task_id": index_task_id,
        "document_id": document_id,
        "status": "pending",
        "progress": 0,
        "current_stage": "等待重新开始",
        "target_index_version": target_version,
        "created_at": now,
        "updated_at": now
    }
    create_index_task(task_data)
    
    submit_index_task(index_task_id, document_id)
    
    return {
        "document_id": document_id,
        "index_task_id": index_task_id,
        "status": "pending",
        "message": "Document reindexing queued"
    }
