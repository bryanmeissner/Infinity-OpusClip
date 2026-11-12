#!/usr/bin/env bash
# ==============================================================================
# LocalClip - Parar Aplicação
# Encerra com segurança o servidor LocalClip e processos filhos/workers.
# ==============================================================================

set -o pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"

PYTHON_EXEC="python3"
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON_EXEC="$PROJECT_DIR/.venv/bin/python"
fi

IS_HEADLESS=0
if [[ "${LOCALCLIP_HEADLESS:-}" =~ ^(1|true|yes)$ ]]; then
    IS_HEADLESS=1
fi
# --headless/--no-browser só controlam notificações aqui; o subcomando stop não os aceita.
STOP_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--headless" ] || [ "$arg" = "--no-browser" ]; then
        IS_HEADLESS=1
    else
        STOP_ARGS+=("$arg")
    fi
done

"$PYTHON_EXEC" "$PROJECT_DIR/scripts/supervisor.py" stop --repo-dir "$PROJECT_DIR" "${STOP_ARGS[@]}"
EXIT_CODE=$?

if [ ! -t 1 ] && [ "$IS_HEADLESS" -eq 0 ] && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
    if [ $EXIT_CODE -eq 0 ]; then
        if command -v notify-send >/dev/null 2>&1; then
            notify-send "LocalClip" "Servidor LocalClip encerrado com segurança." --icon=process-stop 2>/dev/null || true
        fi
    else
        MSG="Erro ao encerrar o LocalClip."
        if [ "${XDG_CURRENT_DESKTOP:-}" = "KDE" ] && command -v kdialog >/dev/null 2>&1; then
            kdialog --error "$MSG" --title "LocalClip" 2>/dev/null || true
        elif command -v zenity >/dev/null 2>&1; then
            zenity --error --title="LocalClip" --text="$MSG" --timeout=10 2>/dev/null || true
        elif command -v kdialog >/dev/null 2>&1; then
            kdialog --error "$MSG" --title "LocalClip" 2>/dev/null || true
        elif command -v notify-send >/dev/null 2>&1; then
            notify-send -u critical "LocalClip" "$MSG" 2>/dev/null || true
        fi
    fi
fi

exit $EXIT_CODE
