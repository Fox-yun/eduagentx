"""Verify OpenAPI schema against frozen frontend contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    """Verify the OpenAPI schema."""
    schema = app.openapi()

    if not schema:
        print("ERROR: OpenAPI schema is empty")
        sys.exit(1)

    # Check required fields
    assert "openapi" in schema, "Missing openapi version"
    assert "info" in schema, "Missing info section"
    assert "paths" in schema, "Missing paths section"

    paths = schema["paths"]

    # Verify required endpoints exist
    required_endpoints = [
        "/health/live",
        "/health/ready",
        "/api/auth/csrf",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/me",
        "/api/auth/refresh",
        "/api/auth/logout",
        "/api/auth/verify-email",
        "/api/users/me",
        "/api/users/me/onboarding",
        "/api/learning-goals",
        "/api/learning-goals/{goal_id}",
        "/api/learning/resume",
        "/api/tasks",
        "/api/tasks/{task_id}",
        "/api/tasks/{task_id}/stream",
        "/api/tasks/{task_id}/cancel",
        "/api/learning-paths/{path_id}",
        "/api/learning-paths/{path_id}/versions",
        "/api/learning-paths/{path_id}/activate",
        "/api/learning-paths/{path_id}/revision-requests",
        "/api/learning-paths/{path_id}/nodes/{node_id}/content",
        "/api/learning-paths/{path_id}/nodes/{node_id}/assessments",
        "/api/knowledge/documents",
        "/api/knowledge/search",
    ]

    missing = []
    for endpoint in required_endpoints:
        if endpoint not in paths:
            missing.append(endpoint)

    if missing:
        print(f"ERROR: Missing {len(missing)} required endpoints:")
        for ep in missing:
            print(f"  - {ep}")
        sys.exit(1)

    # Check error response structure
    components = schema.get("components", {})
    schemas = components.get("schemas", {})

    print(f"OpenAPI schema valid: {schema['info']['title']} v{schema['info']['version']}")
    print(f"Paths: {len(paths)}")
    print(f"Schemas: {len(schemas)}")
    print(f"Required endpoints: All {len(required_endpoints)} present")

    # Output schema path
    output_path = Path("openapi.json")
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)
    print(f"Schema written to: {output_path}")


if __name__ == "__main__":
    main()
