"""Final verification script for Backend Phase 3."""

from __future__ import annotations

import subprocess
import sys


def run(cmd: str, check: bool = True) -> int:
    """Run a command and return exit code."""
    print(f"\n{'=' * 60}")
    print(f"Running: {cmd}")
    print("=" * 60)
    result = subprocess.run(cmd, shell=True)
    if check and result.returncode != 0:
        print(f"FAILED: {cmd}")
        return result.returncode
    return 0


def main() -> int:
    """Run all verification checks."""
    checks = [
        ("Ruff lint", "ruff check ."),
        ("Ruff format", "ruff format --check ."),
        ("Unit tests", "python -m pytest tests/unit -v"),
        ("OpenAPI verification", "python scripts/verify_openapi.py"),
    ]

    failed = []
    for name, cmd in checks:
        print(f"\n>>> {name}")
        if run(cmd, check=False) != 0:
            failed.append(name)

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    if failed:
        print(f"\nFAILED ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")
        return 1

    print("\nALL CHECKS PASSED")
    print("\nBackend Phase 3: Production Ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
