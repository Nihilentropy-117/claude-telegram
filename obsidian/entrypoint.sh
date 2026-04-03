#!/bin/sh
set -e

# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
# OBSIDIAN_AUTH_TOKEN is read automatically by `ob login` if set in env.
# Otherwise fall back to email + password.
echo "[obsidian-sync] Logging in..."
if [ -n "$OBSIDIAN_AUTH_TOKEN" ]; then
    ob login
elif [ -n "$OBSIDIAN_EMAIL" ] && [ -n "$OBSIDIAN_PASSWORD" ]; then
    ob login --email "$OBSIDIAN_EMAIL" --password "$OBSIDIAN_PASSWORD"
else
    echo "[obsidian-sync] ERROR: Set OBSIDIAN_AUTH_TOKEN or both OBSIDIAN_EMAIL and OBSIDIAN_PASSWORD" >&2
    exit 1
fi
echo "[obsidian-sync] Login OK."

# ---------------------------------------------------------------------------
# Sync each vault
# ---------------------------------------------------------------------------
if [ -z "$OBSIDIAN_VAULT_NAMES" ]; then
    echo "[obsidian-sync] ERROR: OBSIDIAN_VAULT_NAMES is not set" >&2
    exit 1
fi

PIDS=""

for vault in $(echo "$OBSIDIAN_VAULT_NAMES" | tr ',' '\n'); do
    # Strip leading/trailing whitespace
    vault=$(echo "$vault" | tr -d ' ')
    [ -z "$vault" ] && continue

    VAULT_DIR="/vaults/$vault"
    mkdir -p "$VAULT_DIR"

    echo "[obsidian-sync] Setting up vault: $vault → $VAULT_DIR"
    (
        cd "$VAULT_DIR"
        if [ -n "$OBSIDIAN_VAULT_PASSWORD" ]; then
            ob sync-setup --vault "$vault" --password "$OBSIDIAN_VAULT_PASSWORD"
        else
            ob sync-setup --vault "$vault"
        fi
        echo "[obsidian-sync] Starting continuous sync: $vault"
        exec ob sync --continuous
    ) &

    PIDS="$PIDS $!"
done

# Fail the container if any sync process exits unexpectedly
wait_status=0
for pid in $PIDS; do
    wait "$pid" || wait_status=$?
done

exit $wait_status
