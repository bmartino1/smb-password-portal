#!/bin/sh
set -eu

CONFIG_DIR="${CONFIG_DIR:-/config}"
SECRET_FILE="${SECRET_FILE:-$CONFIG_DIR/secret_key}"

mkdir -p "$CONFIG_DIR"

if [ -z "${SECRET_KEY:-}" ]; then
    if [ ! -s "$SECRET_FILE" ]; then
        echo "Generating Flask SECRET_KEY at $SECRET_FILE"
        python3 - <<PY > "$SECRET_FILE"
import secrets
print(secrets.token_hex(32))
PY
        chmod 600 "$SECRET_FILE" || true
    fi

    export SECRET_KEY="$(cat "$SECRET_FILE")"
fi

echo "Starting smb-password-portal"
echo "SAMBA_SERVER=${SAMBA_SERVER:-127.0.0.1}"
echo "UNRAID_CONFIG_DIR=${UNRAID_CONFIG_DIR:-/unraid-config}"
echo "MIN_PASSWORD_LENGTH=${MIN_PASSWORD_LENGTH:-8}"
echo "SHOW_USER_DROPDOWN=${SHOW_USER_DROPDOWN:-0}"

exec "$@"
