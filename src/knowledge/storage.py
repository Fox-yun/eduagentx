import os
import aiofiles
import hashlib
from typing import AsyncGenerator

async def save_upload_stream(
    stream: AsyncGenerator[bytes, None],
    target_path: str,
    max_size: int = 30 * 1024 * 1024
) -> tuple[str, int]:
    """
    Saves an async stream of bytes to a file.
    Calculates SHA-256 and checks size limit on the fly.
    Uses a temporary file and renames it upon completion.
    
    Returns:
        tuple: (sha256_hex, file_size)
    """
    tmp_path = target_path + ".uploading"
    hasher = hashlib.sha256()
    total_size = 0
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    try:
        async with aiofiles.open(tmp_path, 'wb') as out_file:
            async for chunk in stream:
                hasher.update(chunk)
                await out_file.write(chunk)
                total_size += len(chunk)
                
                if total_size > max_size:
                    raise ValueError(f"File size exceeds limit of {max_size} bytes")
                    
        # Rename tmp to final path atomically (as much as possible on OS)
        os.replace(tmp_path, target_path)
        
        return hasher.hexdigest(), total_size
        
    except Exception:
        # Cleanup tmp file if failed
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

def delete_file(target_path: str):
    """
    Deletes the file at the given path if it exists.
    """
    if os.path.exists(target_path):
        os.remove(target_path)
