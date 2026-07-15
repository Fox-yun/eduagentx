#!/usr/bin/env python3
"""Create a cross-platform ZIP package of the EduAgentX submission.

Excludes agent tool files, temporary scripts, and development artifacts.
Uses UTF-8 filenames and forward slashes for cross-platform compatibility.
"""

import os
import zipfile
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "EduAgentX-submission.zip")

# Directories to exclude entirely
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".tauri",
    "target",
    ".packaging",
    ".catpaw",
    ".codex",
    ".claude",
    ".vscode",
    ".idea",
    "certs",
    ".uv-cache-review",
    ".pytest_tmp_full_diagram",
    ".local-storage",
    "coverage",
    "playwright-report",
    "test-results",
    ".next",
    ".nuxt",
}

# File patterns to exclude
EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".exe",
    ".msi",
    ".log",
    ".tmp",
    ".swp",
    ".swo",
    ".egg-info",
    ".tsbuildinfo",
    ".part",
}

# Specific files to exclude
EXCLUDE_FILES = {
    ".env",
    ".env.docker",
    ".env.local",
    ".env.production",
    ".coverage",
    "_create_zip.py",
    "_verify_zip.py",
    "mypy_output.txt",
    "mypy_output2.txt",
    "mypy_output3.txt",
    "mypy_final.txt",
    "ruff_output.txt",
    "ruff_final.txt",
    "test_output.txt",
    "test_all.txt",
    "test_all2.txt",
    "test_all3.txt",
    "test_all4.txt",
    "test_final.txt",
    "openapi_gen.txt",
    "backend/.env",
    "backend/.env.docker",
    "backend/.coverage",
    "frontend/.env.local",
    "frontend/.coverage",
    "EduAgentX-submission.zip",
    "EduAgentX-submission(2).zip",
    "EduAgentX-submission(3).zip",
}

# Files that start with these prefixes are excluded
EXCLUDE_PREFIXES = {
    ".",
    "_",
}


def should_exclude(path: str, name: str) -> bool:
    """Check if a file or directory should be excluded."""
    # Check directory exclusions
    if name in EXCLUDE_DIRS:
        return True

    # Check file exclusions
    full_path = os.path.join(path, name)
    rel_path = os.path.relpath(full_path, PROJECT_ROOT).replace("\\", "/")

    if rel_path in EXCLUDE_FILES:
        return True

    # Check for .env files (but keep .env.example, .env.docker.example)
    if name == ".env" or (name.startswith(".env") and "example" not in name and "docker" not in name):
        return True
    if name == ".env.docker":
        return True

    # Exclude files with specific extensions
    _, ext = os.path.splitext(name)
    if ext.lower() in EXCLUDE_EXTENSIONS:
        return True

    # Exclude temporary Python files
    if name.startswith("_") and name.endswith(".py") and "init" not in name:
        return True

    # Exclude __pycache__ directories
    if name == "__pycache__":
        return True

    return False


def collect_files() -> list[str]:
    """Collect all files to include in the ZIP."""
    files = []
    for root, dirs, filenames in os.walk(PROJECT_ROOT):
        # Filter directories in-place to prevent descending into excluded dirs
        dirs[:] = [d for d in dirs if not should_exclude(root, d)]

        for filename in filenames:
            if should_exclude(root, filename):
                continue

            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, PROJECT_ROOT)
            files.append(rel_path)

    return sorted(files)


def create_zip() -> None:
    """Create the ZIP file with UTF-8 filenames and forward slashes."""
    files = collect_files()

    print(f"Collecting {len(files)} files...")

    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    with zipfile.ZipFile(OUTPUT_FILE, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel_path in files:
            full_path = os.path.join(PROJECT_ROOT, rel_path)
            # Use forward slashes for cross-platform compatibility
            arcname = rel_path.replace("\\", "/")

            # Create ZipInfo with UTF-8 flag
            info = zipfile.ZipInfo(arcname)
            info.flag_bits |= 0x800  # Set UTF-8 flag bit
            info.compress_type = zipfile.ZIP_DEFLATED

            with open(full_path, "rb") as f:
                zf.writestr(info, f.read())

    size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"Created: {OUTPUT_FILE}")
    print(f"Size: {size_mb:.1f} MB")
    print(f"Files: {len(files)}")


if __name__ == "__main__":
    create_zip()
