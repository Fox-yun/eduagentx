"""Database setup script - creates databases and runs migrations."""

from __future__ import annotations

import subprocess
import sys


def run_command(cmd: str) -> int:
    """Run a shell command and return the exit code."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


def main() -> None:
    """Set up the database."""
    print("=== EduAgentX Backend Database Setup ===\n")

    # Check if PostgreSQL is available
    print("1. Checking PostgreSQL connection...")
    ret = run_command("pg_isready -h localhost -p 5432")
    if ret != 0:
        print("ERROR: PostgreSQL is not running.")
        print("Please start PostgreSQL first:")
        print("  - Using Docker: cd backend/docker && docker-compose up -d postgres")
        print("  - Or install PostgreSQL locally")
        sys.exit(1)

    # Create databases
    print("\n2. Creating databases...")
    run_command('psql -h localhost -U postgres -c "CREATE DATABASE eduagentx;" 2>/dev/null || true')
    run_command('psql -h localhost -U postgres -c "CREATE DATABASE eduagentx_test;" 2>/dev/null || true')
    run_command(
        "psql -h localhost -U postgres -c \"CREATE USER eduagentx WITH PASSWORD 'eduagentx';\" 2>/dev/null || true"
    )
    run_command(
        'psql -h localhost -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE eduagentx TO eduagentx;" 2>/dev/null || true'
    )
    run_command(
        'psql -h localhost -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE eduagentx_test TO eduagentx;" 2>/dev/null || true'
    )

    # Run migrations
    print("\n3. Running Alembic migrations...")
    ret = run_command("alembic upgrade head")
    if ret != 0:
        print("ERROR: Migration failed.")
        sys.exit(1)

    print("\n=== Database setup complete! ===")


if __name__ == "__main__":
    main()
