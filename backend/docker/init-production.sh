#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

ENV_FILE=".env.docker"
EXAMPLE_FILE=".env.docker.example"
GENERATE_CERT=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --generate-cert) GENERATE_CERT=true; shift ;;
        --force) FORCE=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Check if already initialized ──
if [[ -f "$ENV_FILE" && "$FORCE" == false ]]; then
    if ! grep -q "CHANGE_ME_" "$ENV_FILE"; then
        echo "WARNING: $ENV_FILE already contains non-placeholder values."
        echo "Use --force to overwrite."
        exit 0
    fi
fi

if [[ ! -f "$EXAMPLE_FILE" ]]; then
    echo "ERROR: $EXAMPLE_FILE not found."
    exit 1
fi

# ── Generate secrets using Python ──
echo "Generating random secrets..."

# Detect available Python interpreter
PYTHON_BIN=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_BIN="$cmd"
        break
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    echo "ERROR: Python is required but not found. Please install Python 3."
    exit 1
fi

SECRETS=$($PYTHON_BIN -c "
import secrets, string
from urllib.parse import quote

def gen_url_safe(n=64):
    return secrets.token_urlsafe(n)

def gen_alnum(n=32, charset=None):
    if charset is None:
        charset = string.ascii_letters + string.digits
    return ''.join(secrets.choice(charset) for _ in range(n))

app_secret = gen_url_safe(64)
pg_password = gen_alnum(32)
redis_password = gen_alnum(32)
minio_access = gen_alnum(20, string.ascii_lowercase + string.digits)
minio_secret = gen_alnum(40)
outbox_key = gen_url_safe(32)

print(app_secret)
print(pg_password)
print(quote(pg_password, safe=''))
print(redis_password)
print(quote(redis_password, safe=''))
print(minio_access)
print(minio_secret)
print(outbox_key)
")

APP_SECRET=$(echo "$SECRETS" | sed -n '1p')
PG_PASSWORD=$(echo "$SECRETS" | sed -n '2p')
PG_PASSWORD_ENC=$(echo "$SECRETS" | sed -n '3p')
REDIS_PASSWORD=$(echo "$SECRETS" | sed -n '4p')
REDIS_PASSWORD_ENC=$(echo "$SECRETS" | sed -n '5p')
MINIO_ACCESS=$(echo "$SECRETS" | sed -n '6p')
MINIO_SECRET=$(echo "$SECRETS" | sed -n '7p')
OUTBOX_KEY=$(echo "$SECRETS" | sed -n '8p')

# ── Generate .env.docker from template ──
echo "Writing $ENV_FILE..."

sed \
    -e "s/CHANGE_ME_TO_64_PLUS_RANDOM_CHARACTERS/${APP_SECRET}/g" \
    -e "s/CHANGE_ME_TO_STRONG_PASSWORD/${PG_PASSWORD}/g" \
    -e "s/CHANGE_ME_TO_REDIS_PASSWORD/${REDIS_PASSWORD}/g" \
    -e "s/CHANGE_ME_TO_STRONG_ACCESS_KEY/${MINIO_ACCESS}/g" \
    -e "s/CHANGE_ME_TO_STRONG_SECRET_KEY/${MINIO_SECRET}/g" \
    -e "s/CHANGE_ME_TO_32_PLUS_RANDOM_CHARACTERS/${OUTBOX_KEY}/g" \
    "$EXAMPLE_FILE" > "$ENV_FILE"

# Update connection URLs with URL-encoded passwords
# Detect OS for sed compatibility (GNU sed uses -i, BSD sed needs -i '')
if [[ "$OSTYPE" == "darwin"* ]]; then
    SED_INPLACE=(-i '')
else
    SED_INPLACE=(-i)
fi

sed "${SED_INPLACE[@]}" \
    -e "s|postgresql+asyncpg://eduagentx:${PG_PASSWORD}@|postgresql+asyncpg://eduagentx:${PG_PASSWORD_ENC}@|g" \
    -e "s|redis://:${REDIS_PASSWORD}@|redis://:${REDIS_PASSWORD_ENC}@|g" \
    "$ENV_FILE"

# Set production environment
sed "${SED_INPLACE[@]}" \
    -e "s/APP_ENV=development/APP_ENV=production/g" \
    -e "s/COOKIE_SECURE=false/COOKIE_SECURE=true/g" \
    "$ENV_FILE"

chmod 600 "$ENV_FILE"
echo "Secrets written to $ENV_FILE"

# ── Generate self-signed certificate ──
if [[ "$GENERATE_CERT" == true ]]; then
    CERTS_DIR="nginx/certs"
    mkdir -p "$CERTS_DIR"

    echo "Generating self-signed TLS certificate..."
    openssl req -x509 -nodes -days 365 \
        -newkey rsa:2048 \
        -keyout "$CERTS_DIR/privkey.pem" \
        -out "$CERTS_DIR/fullchain.pem" \
        -subj "/C=CN/ST=Beijing/L=Beijing/O=EduAgentX/CN=eduagentx.local" \
        -addext "subjectAltName=DNS:eduagentx.local,DNS:localhost,IP:127.0.0.1" 2>/dev/null

    echo ""
    echo "WARNING: Self-signed certificates are for testing only."
    echo "For production, use a trusted CA-signed certificate."
fi

echo ""
echo "Initialization complete."
echo "Next steps:"
echo "  docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.production.yml up -d   (with HTTPS)"
echo "  ./start-stack.sh demo                (local HTTP, no certs needed)"
