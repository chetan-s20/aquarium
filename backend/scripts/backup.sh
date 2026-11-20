#!/usr/bin/env bash
# Backup the Aquarium database to a dated file.
#   sqlite:     copies aquarium.db (back it up with the server stopped, or stop it first)
#   postgres:   pg_dump of DATABASE_URL
set -euo pipefail
out="${1:-aquarium-backup-$(date -u +%Y%m%d-%H%M%S).sql}"
url="${DATABASE_URL:-sqlite:///./aquarium.db}"
case "$url" in
  sqlite*) path="${url#sqlite:///}"; cp "$path" "$out" ;;
  postgres*) pg_dump "$url" > "$out" ;;
  *) echo "unsupported DATABASE_URL for backup: $url" >&2; exit 1 ;;
esac
echo "backed up to $out"
