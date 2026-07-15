#!/usr/bin/env bash
# ── EduAgentX Docker Stack Starter (Linux/macOS) ──
# Usage:
#   ./start-stack.sh demo         # Demo mode (HTTP, no TLS required)
#   ./start-stack.sh production   # Production mode (HTTPS, requires TLS certs)
set -euo pipefail

cd "$(dirname "$0")"

MODE="${1:-demo}"

if [[ "$MODE" != "production" && "$MODE" != "demo" ]]; then
    echo "Usage: $0 [demo|production]"
    echo "  demo        - Local development with HTTP (default)"
    echo "  production  - Production with HTTPS + Nginx"
    exit 1
fi

ENV_FILE=".env.docker"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found. Run init-production.sh first to generate secrets."
    exit 1
fi

COMPOSE_ARGS=(--env-file "$ENV_FILE" -f docker-compose.yml)

if [[ "$MODE" == "production" ]]; then
    # Verify TLS certs exist
    if [[ ! -f nginx/certs/fullchain.pem || ! -f nginx/certs/privkey.pem ]]; then
        echo "ERROR: TLS certificates not found in nginx/certs/."
        echo "Run init-production.sh --generate-cert to generate self-signed certs, or place real certs manually."
        exit 1
    fi
    COMPOSE_ARGS+=(-f docker-compose.production.yml)
else
    COMPOSE_ARGS+=(-f docker-compose.demo.yml)
    COMPOSE_ARGS+=(--profile demo)
fi

echo "Starting in $MODE mode..."

# ── Start infrastructure ──
if [[ "$MODE" == "demo" ]]; then
    echo "Starting PostgreSQL, Redis, MinIO, and Mailpit..."
    docker compose "${COMPOSE_ARGS[@]}" up -d postgres redis minio mailpit
else
    echo "Starting PostgreSQL, Redis, and MinIO..."
    docker compose "${COMPOSE_ARGS[@]}" up -d postgres redis minio
fi

# ── Build images ──
echo "Building application images..."
docker compose "${COMPOSE_ARGS[@]}" build \
    migrate \
    backend \
    celery-worker \
    celery-beat \
    outbox-publisher \
    frontend

# ── Run migrations ──
echo "Running database migrations..."
docker compose "${COMPOSE_ARGS[@]}" up migrate

# ── Start runtime services ──
echo "Starting runtime services..."
docker compose "${COMPOSE_ARGS[@]}" up -d \
    backend \
    celery-worker \
    celery-beat \
    outbox-publisher \
    frontend

if [[ "$MODE" == "production" ]]; then
    echo "Starting Nginx (HTTPS)..."
    docker compose "${COMPOSE_ARGS[@]}" up -d nginx
fi

# ── Wait for backend readiness ──
echo "Waiting for backend readiness..."

ready=false
for attempt in $(seq 1 30); do
    if [[ "$MODE" == "production" ]]; then
        if response=$(curl -sk --max-time 3 https://127.0.0.1/health/ready 2>/dev/null); then
            status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
            if [[ "$status" == "ready" ]]; then
                ready=true
                break
            fi
        fi
    else
        if response=$(curl -s --max-time 3 http://127.0.0.1:8000/health/ready 2>/dev/null); then
            status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
            if [[ "$status" == "ready" ]]; then
                ready=true
                break
            fi
        fi
    fi
    sleep 2
done

if [[ "$ready" == false ]]; then
    docker compose "${COMPOSE_ARGS[@]}" logs --tail=200 backend
    echo "ERROR: Backend did not become ready."
    exit 1
fi

# ── Wait for frontend / nginx health ──
echo "Waiting for frontend health..."

frontend_ready=false
for attempt in $(seq 1 15); do
    if [[ "$MODE" == "production" ]]; then
        if curl -sk --max-time 3 https://127.0.0.1/health >/dev/null 2>&1; then
            frontend_ready=true
            break
        fi
    else
        if curl -s --max-time 3 http://127.0.0.1:8081/health >/dev/null 2>&1; then
            frontend_ready=true
            break
        fi
    fi
    sleep 2
done

if [[ "$frontend_ready" == false ]]; then
    docker compose "${COMPOSE_ARGS[@]}" logs --tail=200 frontend
    echo "ERROR: Frontend did not become healthy."
    exit 1
fi

echo ""
echo "Full stack started successfully in $MODE mode."

if [[ "$MODE" == "production" ]]; then
    echo "Frontend: https://127.0.0.1 (or your domain)"
    echo "Backend API: https://127.0.0.1/api/"
    echo "Health: https://127.0.0.1/health/ready"
else
    echo "Frontend:  http://127.0.0.1:8081"
    echo "Backend:  http://127.0.0.1:8000"
    echo "Mailpit:  http://127.0.0.1:8025"
    echo "MinIO:    http://127.0.0.1:9001 (console)"
fi
