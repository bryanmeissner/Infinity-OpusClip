#!/usr/bin/env bash
# Atalho para parar o LocalClip
DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/parar.sh" "$@"
