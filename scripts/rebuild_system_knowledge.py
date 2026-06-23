import os
import sys
import argparse
import uuid
import time
import hashlib
import sqlite3
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from src.knowledge.parser import parse_document
from src.knowledge.splitter import split_document
from src.db.database import get_connection
from src.rag.vector_store import get_vectorstore, get_chroma_db_path

def rebuild_system_knowledge(dry_run: bool, reset: bool, purge_old: bool, keep_last: int, confirm: bool):
    print("=== System Knowledge Base Management Tool ===")

    base_dir = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base")
    if not os.path.exists(base_dir):
        print(f"Error: Directory {base_dir} does not exist.")
        return

    files = [f for f in os.listdir(base_dir) if os.path.isfile(os.path.join(base_dir, f))]
    print(f"Found {len(files)} files in knowledge_base directory.")

    if dry_run:
        print("\n[DRY RUN MODE] Scanning files...")
        total_files = 0
        total_chunks = 0
        success_files = []
        failed_files = []
        
        for filename in files:
            file_path = os.path.join(base_dir, filename)
            _, ext = os.path.splitext(filename)
            if ext.lower() not in ['.pdf', '.txt', '.md']:
                print(f"Skipping unsupported file: {filename}")
                continue
                
            total_files += 1
            print(f"Simulating processing for: {filename}")
            try:
                documents = parse_document(file_path, ext.lower())
                if not documents:
                    print(f" - Warning: No text parsed from {filename}")
                    failed_files.append(filename)
                    continue
                    
                chunks = split_document(
                    documents=documents,
                    document_id="sys_dry_run",
                    user_id="system",
                    course_id="",
                    conversation_id="",
                    scope="system",
                    source_name=filename
                )
                print(f" - Success: {len(documents)} pages, {len(chunks)} chunks")
                total_chunks += len(chunks)
                success_files.append(filename)
            except Exception as e:
                print(f" - Failed to parse: {e}")
                failed_files.append(filename)
                
        print("\n=== Dry Run Summary ===")
        print(f"Total files scanned: {total_files}")
        print(f"Supported format parsed successfully: {len(success_files)}")
        print(f"Estimated total chunks: {total_chunks}")
        if failed_files:
            print(f"Errors encountered in: {failed_files}")
        print("Dry run completed. No changes were made to Chroma DB or SQLite.")
        return

    if reset:
        print("\n[RESET MODE] Rebuilding system collection...")
        try:
            # 1. Allocate version inside SQLite transaction
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE")
                cursor.execute("SELECT COALESCE(MAX(index_version), 0) + 1 FROM knowledge_system_builds")
                index_version = cursor.fetchone()[0]
                
                timestamp = int(time.time())
                new_collection_name = f"system_knowledge_v{index_version}_{timestamp}"
                now = time.time()
                
                # Insert building record
                cursor.execute(
                    """
                    INSERT INTO knowledge_system_builds (collection_name, index_version, status, created_at)
                    VALUES (?, ?, 'building', ?)
                    """,
                    (new_collection_name, index_version, now)
                )
                conn.commit()
            print(f"Allocated index_version: {index_version}")
            print(f"Target Collection: {new_collection_name}")
        except Exception as e:
            print(f"Failed to allocate version: {e}")
            return

        new_docs = []
        new_chunks = []
        expected_vector_ids = []
        
        # 2. Build Chroma Collection and add documents
        vs = get_vectorstore(get_chroma_db_path(), new_collection_name)
        new_collection_created = True
        switched = False
        
        try:
            for idx, filename in enumerate(files):
                _, ext = os.path.splitext(filename)
                if ext.lower() not in ['.pdf', '.txt', '.md']:
                    continue
                    
                print(f"[{idx+1}/{len(files)}] Processing {filename}...")
                file_path = os.path.join(base_dir, filename)
                stable_id = "sys_" + hashlib.md5(filename.encode()).hexdigest()
                file_size = os.path.getsize(file_path)
                
                documents = parse_document(file_path, ext.lower())
                if not documents:
                    raise ValueError(f"No text extracted from {filename}")
                    
                chunks = split_document(
                    documents=documents,
                    document_id=stable_id,
                    user_id="system",
                    course_id="",
                    conversation_id="",
                    scope="system",
                    source_name=filename
                )
                
                vector_ids = [f"{stable_id}:v{index_version}:{chunk.metadata.get('chunk_index', i)}" for i, chunk in enumerate(chunks)]
                for i, chunk in enumerate(chunks):
                    chunk.metadata["vector_id"] = vector_ids[i]
                    chunk.metadata["index_version"] = index_version
                    
                vs.add_documents(documents=chunks, ids=vector_ids)
                expected_vector_ids.extend(vector_ids)
                
                for i, chunk in enumerate(chunks):
                    new_chunks.append({
                        "chunk_id": str(uuid.uuid4()),
                        "document_id": stable_id,
                        "vector_id": vector_ids[i],
                        "page_number": chunk.metadata.get("page", 0),
                        "chunk_index": chunk.metadata.get("chunk_index", i),
                        "content_hash": hashlib.sha256(chunk.page_content.encode("utf-8")).hexdigest(),
                        "index_version": index_version,
                        "created_at": time.time()
                    })
                    
                new_docs.append({
                    "document_id": stable_id,
                    "user_id": "system",
                    "course_id": None,
                    "conversation_id": None,
                    "scope": "system",
                    "original_filename": filename,
                    "stored_path": file_path,
                    "file_size": file_size,
                    "sha256": stable_id,
                    "status": "ready",
                    "active_index_version": index_version,
                    "page_count": len(documents),
                    "chunk_count": len(chunks),
                    "created_at": time.time(),
                    "updated_at": time.time(),
                    "indexed_at": time.time()
                })
                print(f"Success: {filename} ({len(chunks)} chunks)")

            # 3. Validation
            print("Validating collection count in Chroma...")
            collection_count = vs._collection.count()
            if collection_count != len(new_chunks):
                raise RuntimeError(f"Chroma collection count ({collection_count}) mismatch with expected chunk count ({len(new_chunks)})")
                
            print("Verifying specific vector IDs in Chroma...")
            stored = vs._collection.get(ids=expected_vector_ids)
            if len(stored["ids"]) != len(expected_vector_ids):
                raise RuntimeError("Not all vector IDs exist in Chroma")
                
            print("Running sampling query verification...")
            # Query content from 2-3 different chunks if possible
            sample_docs = list(set([doc["original_filename"] for doc in new_docs]))[:3]
            for s_doc in sample_docs:
                matching_chunks = [c for c in new_chunks if c["document_id"] == "sys_" + hashlib.md5(s_doc.encode()).hexdigest()]
                if matching_chunks:
                    # Let's perform a search
                    results = vs.similarity_search("EduAgent", k=3)
                    if not results:
                        raise RuntimeError(f"Sampling search returned empty results")
            print("Validation successful!")

            # 4. SQLite transaction atomic switch
            print("Performing atomic SQLite switch transaction...")
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE")
                
                # Delete old chunks
                cursor.execute("DELETE FROM knowledge_chunks WHERE document_id IN (SELECT document_id FROM knowledge_documents WHERE scope = 'system')")
                # Delete old docs
                cursor.execute("DELETE FROM knowledge_documents WHERE scope = 'system'")
                
                # Insert new docs
                for doc in new_docs:
                    cols = ", ".join(doc.keys())
                    placeholders = ", ".join(["?"] * len(doc))
                    cursor.execute(f"INSERT INTO knowledge_documents ({cols}) VALUES ({placeholders})", list(doc.values()))
                    
                # Insert new chunks
                for chunk in new_chunks:
                    cols = ", ".join(chunk.keys())
                    placeholders = ", ".join(["?"] * len(chunk))
                    cursor.execute(f"INSERT INTO knowledge_chunks ({cols}) VALUES ({placeholders})", list(chunk.values()))
                    
                # Update setting active_system_collection
                cursor.execute(
                    """
                    INSERT INTO knowledge_settings (setting_key, setting_value, updated_at)
                    VALUES ('active_system_collection', ?, ?)
                    ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value, updated_at = excluded.updated_at
                    """,
                    (new_collection_name, time.time())
                )
                
                # Retire old active builds
                cursor.execute(
                    """
                    UPDATE knowledge_system_builds
                    SET status = 'retired'
                    WHERE status = 'active'
                    """
                )
                
                # Activate new build
                cursor.execute(
                    """
                    UPDATE knowledge_system_builds
                    SET status = 'active', activated_at = ?
                    WHERE collection_name = ?
                    """,
                    (time.time(), new_collection_name)
                )
                conn.commit()
                
            switched = True
            print(f"Successfully switched system collection to: {new_collection_name}")
            
        except Exception as build_err:
            print(f"Rebuild failed: {build_err}")
            # Mark build as failed in database
            try:
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE knowledge_system_builds SET status = 'failed', error = ? WHERE collection_name = ?",
                        (str(build_err), new_collection_name)
                    )
            except Exception as db_err:
                print(f"Failed to record build failure: {db_err}")
                
            # Clean up the newly created collection
            if new_collection_created and not switched:
                print("Cleaning up failed Chroma collection...")
                try:
                    # Delete the collection from Chroma
                    vs._client.delete_collection(new_collection_name)
                    print("Deleted collection successfully.")
                except Exception as chroma_err:
                    print(f"Failed to delete collection from Chroma: {chroma_err}")
            return

    if purge_old:
        print(f"\n[PURGE MODE] Scanning for retired or failed system collections (keeping last {keep_last} retired versions)...")
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get active collection
        cursor.execute("SELECT setting_value FROM knowledge_settings WHERE setting_key = 'active_system_collection'")
        active_row = cursor.fetchone()
        active_collection = active_row[0] if active_row else None
        
        # Get builds
        cursor.execute("SELECT * FROM knowledge_system_builds ORDER BY index_version DESC")
        builds = [dict(r) for r in cursor.fetchall()]
        conn.close()
        
        retired_builds = [b for b in builds if b["status"] == "retired"]
        failed_builds = [b for b in builds if b["status"] == "failed"]
        
        # Keep top N retired builds
        to_keep = retired_builds[:keep_last]
        to_purge_retired = retired_builds[keep_last:]
        to_purge = failed_builds + to_purge_retired
        
        # Exclude active collection just in case
        to_purge = [b for b in to_purge if b["collection_name"] != active_collection]
        
        if not to_purge:
            print("No older retired or failed system collections found to purge.")
            return
            
        print(f"Found {len(to_purge)} collections to purge:")
        for b in to_purge:
            print(f" - Collection: {b['collection_name']} (Version: {b['index_version']}, Status: {b['status']})")
            
        if not confirm:
            print("\nDRY RUN. Use --confirm to execute the purge.")
            return
            
        print("\nExecuting purge...")
        for b in to_purge:
            col_name = b["collection_name"]
            ver = b["index_version"]
            print(f"Purging {col_name}...")
            
            # Delete from Chroma first
            chroma_success = False
            try:
                # Retrieve client and delete collection
                vs = get_vectorstore(get_chroma_db_path(), col_name)
                vs._client.delete_collection(col_name)
                chroma_success = True
                print(f" - Deleted Chroma collection {col_name}")
            except Exception as chroma_e:
                err_msg = str(chroma_e).lower()
                if "does not exist" in err_msg or "not found" in err_msg:
                    chroma_success = True
                    print(f" - Chroma collection {col_name} already deleted.")
                else:
                    print(f" - Error deleting collection from Chroma: {chroma_e}")
                    
            if chroma_success:
                # Delete SQLite chunks & tracking records for this version
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("BEGIN IMMEDIATE")
                    
                    # Delete chunks for this version
                    cursor.execute("DELETE FROM knowledge_chunks WHERE index_version = ? AND document_id IN (SELECT document_id FROM knowledge_documents WHERE scope = 'system')", (ver,))
                    # Delete index vectors for this version
                    cursor.execute("DELETE FROM knowledge_index_vectors WHERE index_version = ? AND document_id IN (SELECT document_id FROM knowledge_documents WHERE scope = 'system')", (ver,))
                    # Mark build as purged
                    cursor.execute("UPDATE knowledge_system_builds SET status = 'purged' WHERE collection_name = ?", (col_name,))
                    
                    conn.commit()
                    conn.close()
                    print(f" - Cleaned SQLite records and set build status to purged.")
                except Exception as db_e:
                    print(f" - Error cleaning SQLite records: {db_e}")
            else:
                print(f" - Skipped SQLite cleanup for version {ver} since Chroma delete failed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild and manage system knowledge collection")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Simulate parsing and check statistics without saving to DB or Chroma.")
    group.add_argument("--reset", action="store_true", help="Build a new system collection version and atomically switch active_system_collection.")
    group.add_argument("--purge-old", action="store_true", help="Purge older retired or failed system collections.")
    
    parser.add_argument("--keep-last", type=int, default=2, help="Number of retired system collections to keep when purging (default is 2).")
    parser.add_argument("--confirm", action="store_true", help="Confirm execution for purging older versions.")
    
    args = parser.parse_args()
    rebuild_system_knowledge(args.dry_run, args.reset, args.purge_old, args.keep_last, args.confirm)
