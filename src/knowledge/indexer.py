import time
import hashlib
from langchain_core.documents import Document
from src.rag.vector_store import get_vectorstore

class IndexingError(Exception):
    pass

from src.knowledge.repository import record_index_vectors, update_index_vectors_state

def add_documents_to_vector_store(
    vectorstore,
    index_task_id: str,
    document_id: str,
    index_version: int,
    chunks: list[Document],
    batch_size: int = 32
) -> list[str]:
    """
    Adds chunks to Chroma vector store incrementally.
    Records planned vector IDs in DB before calling Chroma.
    Generates a unique vector_id for each chunk using index_version.
    """
    inserted_ids = []
    
    # Generate vector ids deterministically
    vector_ids = [f"{document_id}:v{index_version}:{chunk.metadata.get('chunk_index', i)}" for i, chunk in enumerate(chunks)]
    
    for i, chunk in enumerate(chunks):
        content_hash = hashlib.sha256(chunk.page_content.encode('utf-8')).hexdigest()
        chunk.metadata["content_hash"] = content_hash
        chunk.metadata["vector_id"] = vector_ids[i]
        chunk.metadata["index_version"] = index_version
        
    try:
        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_ids = vector_ids[i:i + batch_size]
            
            # 1. Record planned state
            record_index_vectors(index_task_id, document_id, index_version, batch_ids, "planned")
            
            # 2. Insert into Chroma
            vectorstore.add_documents(documents=batch_chunks, ids=batch_ids)
            
            # 3. Mark as inserted
            update_index_vectors_state(index_task_id, batch_ids, "inserted")
            
            inserted_ids.extend(batch_ids)
            
        return inserted_ids
    except Exception as e:
        raise IndexingError(f"Failed to add documents to vector store: {e}")

def delete_documents_from_vector_store(vectorstore, vector_ids: list[str]) -> bool:
    """
    Deletes specific vector IDs from Chroma vector store.
    """
    if not vector_ids:
        return True
        
    try:
        vectorstore.delete(ids=vector_ids)
        return True
    except Exception as e:
        # Check if the error is just "id not found" which is safe to ignore
        err_msg = str(e).lower()
        if "does not exist" in err_msg or "not found" in err_msg:
            return True
        raise IndexingError(f"Failed to delete documents from vector store: {e}")
