from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

def split_document(
    documents: list[Document],
    document_id: str,
    user_id: str,
    course_id: str | None,
    conversation_id: str | None,
    scope: str,
    source_name: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120
) -> list[Document]:
    """
    Splits documents into chunks and injects uniform metadata into each chunk.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""]
    )
    
    chunks = splitter.split_documents(documents)
    
    # Inject metadata
    for i, chunk in enumerate(chunks):
        # Langchain loaders often set 'page' for PDF, 'source' for the file path
        page = chunk.metadata.get('page', 0)
        
        # Build the new metadata
        new_meta = {
            "document_id": document_id,
            "user_id": user_id,
            "course_id": course_id or "",
            "conversation_id": conversation_id or "",
            "scope": scope,
            "source": source_name,
            "page": page,
            "chunk_index": i
        }
        
        chunk.metadata = new_meta
        
    return chunks
