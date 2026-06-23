import os
import tempfile
import pytest

# 设置环境变量，使用隔离的测试数据库
test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.environ["SQLITE_DB_PATH"] = test_db_path

# 可以根据需要隔离向量库
test_db_dir = tempfile.mkdtemp()
os.environ["CHROMA_DB_PATH"] = test_db_dir

@pytest.fixture(scope="session", autouse=True)
def isolated_database():
    """
    会话级别的 fixture，确保所有测试使用同一个隔离的临时数据库。
    并在会话结束时清理。
    """
    from src.db.database import init_db
    init_db()
    
    yield test_db_path
    
    # 清理
    os.close(test_db_fd)
    try:
        os.remove(test_db_path)
    except OSError:
        pass
        
    import shutil
    try:
        shutil.rmtree(test_db_dir)
    except OSError:
        pass

@pytest.fixture(autouse=True)
def clear_db_data():
    """
    每个测试执行前清空数据库中的数据（保留表结构），
    确保测试之间互不干扰。
    """
    from src.db.database import get_connection
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("DELETE FROM knowledge_chunks")
        cursor.execute("DELETE FROM knowledge_index_tasks")
        cursor.execute("DELETE FROM knowledge_documents")
        cursor.execute("DELETE FROM task_resources")
        cursor.execute("DELETE FROM tasks")
        conn.commit()
    yield
