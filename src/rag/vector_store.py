import os
import glob
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import MarkdownTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings.sparkllm import SparkLLMTextEmbeddings
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

spark_embeddings = SparkLLMTextEmbeddings(
    spark_app_id=os.environ.get("SPARK_APPID"),
    spark_api_key=os.environ.get("SPARK_API_KEY"),
    spark_api_secret=os.environ.get("SPARK_API_SECRET")
)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "chroma_db")
KB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "knowledge_base")

def get_chroma_db_path() -> str:
    return os.environ.get("CHROMA_DB_PATH", DB_DIR)

from langchain_community.document_loaders import PyPDFLoader

def build_vector_store():
    # Deprecated build mechanism, retain but warn
    print("[RAG] 正在构建本地向量知识库 (已弃用, 请使用 rebuild_system_knowledge.py)...")
    pass

from functools import lru_cache

@lru_cache(maxsize=16)
def get_vectorstore(db_path: str, collection_name: str):
    return Chroma(
        collection_name=collection_name,
        persist_directory=db_path,
        embedding_function=spark_embeddings,
        collection_metadata={"hnsw:space": "cosine"}
    )

def get_active_system_collection_name() -> str:
    from src.db.database import get_connection
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT setting_value FROM knowledge_settings WHERE setting_key = 'active_system_collection'")
            row = cursor.fetchone()
            if row:
                return row["setting_value"]
    except Exception as e:
        print(f"Error fetching active_system_collection: {e}")
    return "system_knowledge"

def get_system_vectorstore():
    return get_vectorstore(get_chroma_db_path(), get_active_system_collection_name())

def get_user_vectorstore():
    return get_vectorstore(get_chroma_db_path(), "user_knowledge")

def get_retriever(k: int = 15, user_id: str = None, course_id: str = None, scope: str = None):
    """(Deprecated) 仅为向后兼容保留，新代码请使用 retrieve_authorized_documents"""
    if not os.path.exists(DB_DIR):
        raise RuntimeError("向量库不存在，请先运行 python src/rag/vector_store.py 构建知识库。")
    vectorstore = get_user_vectorstore()
    search_kwargs = {"k": k}
    filter_dict = {}
    if user_id:
        filter_dict["user_id"] = user_id
    if course_id:
        filter_dict["course_id"] = course_id
    if scope:
        filter_dict["scope"] = scope
        
    if filter_dict:
        if len(filter_dict) == 1:
            search_kwargs["filter"] = filter_dict
        else:
            search_kwargs["filter"] = {"$and": [{k: v} for k, v in filter_dict.items()]}
            
    return vectorstore.as_retriever(search_kwargs=search_kwargs)

def append_course_filter(base_conditions: list[dict], course_id: str | None) -> list[dict]:
    if not course_id or course_id == "__all__":
        return base_conditions
        
    # course_id = "__none__" -> filtering handled appropriately. Chroma doesn't natively support IS NULL,
    # so we rely on empty string "" which we use to store empty courses.
    if course_id == "__none__":
        return [*base_conditions, {"course_id": ""}]
        
    return [*base_conditions, {"course_id": course_id}]

def merge_retrieval_candidates(
    candidates: list[dict],
    final_k: int,
    max_per_document: int,
    max_context_chars: int,
    user_id: str,
    conversation_id: str | None
) -> list:
    candidates.sort(key=lambda item: item["score"], reverse=True)

    seen_vector_ids = set()
    seen_content_hashes = set()
    per_document_count = {}
    selected = []
    total_chars = 0
    
    # Pre-fetch authorization for the document IDs in the candidates
    doc_ids_in_results = list(set(item["document"].metadata.get("document_id") for item in candidates if item["document"].metadata.get("document_id")))
    
    from src.knowledge.repository import get_authorized_active_versions
    active_versions = get_authorized_active_versions(doc_ids_in_results, user_id, conversation_id)

    for item in candidates:
        doc = item["document"]
        metadata = doc.metadata

        document_id = metadata.get("document_id")
        vector_id = metadata.get("vector_id")
        chunk_index_version = int(metadata.get("index_version", 1))
        
        # We might not have a vector_id directly in metadata, Chroma returns it as id in the result set,
        # but Langchain's similarity_search doesn't expose it by default unless we use .get()
        import hashlib
        content_hash = hashlib.sha256(doc.page_content.encode("utf-8")).hexdigest()

        if document_id and document_id not in active_versions:
            continue
            
        # Filter out stale versions
        if document_id and chunk_index_version != active_versions[document_id]:
            continue

        if vector_id and vector_id in seen_vector_ids:
            continue

        if content_hash in seen_content_hashes:
            continue

        if per_document_count.get(document_id, 0) >= max_per_document:
            continue

        if total_chars + len(doc.page_content) > max_context_chars:
            continue

        selected.append(doc)
        total_chars += len(doc.page_content)
        per_document_count[document_id] = per_document_count.get(document_id, 0) + 1

        if vector_id:
            seen_vector_ids.add(vector_id)

        seen_content_hashes.add(content_hash)

        if len(selected) >= final_k:
            break

    return selected

def retrieve_authorized_documents(
    query: str,
    *,
    user_id: str,
    course_id: str | None = None,
    conversation_id: str | None = None,
    final_k: int = 5,
    fetch_k: int = 8,
    max_per_document: int = 2,
    max_context_chars: int = 16000,
    fusion_strategy: str = "score" # "score" or "rrf"
):
    if not os.path.exists(DB_DIR):
        pass # Handle gracefully by returning empty if not found, let chroma create on access if needed

    system_vectorstore = get_system_vectorstore()
    user_vectorstore = get_user_vectorstore()
    
    all_candidates = []
    
    # Helper to execute search and append to candidates
    def _search_and_append(vs, filter_dict, scope_name):
        try:
            docs_and_scores = vs.similarity_search_with_relevance_scores(query, k=fetch_k, filter=filter_dict)
            for doc, score in docs_and_scores:
                all_candidates.append({
                    "document": doc,
                    "score": score,
                    "source_scope": scope_name
                })
        except Exception as e:
            print(f"[RAG Error] {scope_name} scope search failed: {e}")

    # 1. System Scope (Course specific or general)
    sys_conditions = [{"scope": "system"}]
    sys_conditions = append_course_filter(sys_conditions, course_id)
    sys_filter = {"$and": sys_conditions} if len(sys_conditions) > 1 else sys_conditions[0]
    _search_and_append(system_vectorstore, sys_filter, "system")

    # 2. Personal Scope
    personal_conditions = [{"scope": "personal"}, {"user_id": user_id}]
    personal_conditions = append_course_filter(personal_conditions, course_id)
    _search_and_append(user_vectorstore, {"$and": personal_conditions}, "personal")

    # 3. Session Scope
    if conversation_id:
        session_conditions = [
            {"scope": "session"},
            {"user_id": user_id},
            {"conversation_id": conversation_id}
        ]
        session_conditions = append_course_filter(session_conditions, course_id)
        _search_and_append(user_vectorstore, {"$and": session_conditions}, "session")

    # If a specific course_id is provided, also fetch global documents for personal and system scopes
    if course_id and course_id not in ("__all__", "__none__", "__global__"):
        global_sys_filter = {"$and": [{"scope": "system"}, {"course_id": ""}]}
        _search_and_append(system_vectorstore, global_sys_filter, "system_global")
        
        global_personal_filter = {"$and": [{"scope": "personal"}, {"user_id": user_id}, {"course_id": ""}]}
        _search_and_append(user_vectorstore, global_personal_filter, "personal_global")

    # Apply fusion strategy
    if fusion_strategy == "rrf":
        # Group by scope/source or just rank globally
        # Since we just want to fuse across collections, we can rank by score within their respective source_scope types
        # and then apply RRF
        sys_candidates = sorted([c for c in all_candidates if c["source_scope"].startswith("system")], key=lambda x: x["score"], reverse=True)
        user_candidates = sorted([c for c in all_candidates if not c["source_scope"].startswith("system")], key=lambda x: x["score"], reverse=True)
        
        fused_scores = {} # id -> fused score
        for i, c in enumerate(sys_candidates):
            doc_id = c["document"].metadata.get("vector_id", c["document"].metadata.get("document_id", str(i)))
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + 1.0 / (60 + i + 1)
        for i, c in enumerate(user_candidates):
            doc_id = c["document"].metadata.get("vector_id", c["document"].metadata.get("document_id", str(i)))
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + 1.0 / (60 + i + 1)
            
        for c in all_candidates:
            doc_id = c["document"].metadata.get("vector_id", c["document"].metadata.get("document_id", "0"))
            c["score"] = fused_scores.get(doc_id, 0)

    # Merge and deduplicate
    unique_docs = merge_retrieval_candidates(
        all_candidates,
        final_k=final_k,
        max_per_document=max_per_document,
        max_context_chars=max_context_chars,
        user_id=user_id,
        conversation_id=conversation_id
    )
    
    return unique_docs

if __name__ == "__main__":
    build_vector_store()
