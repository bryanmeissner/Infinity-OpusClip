#!/usr/bin/env bash
# Atalho para iniciar o LocalClip
DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/iniciar.sh" "$@"
