#!/usr/bin/env bash
# ==============================================================================
# LocalClip - Iniciar Aplicação
# Compatível com Fedora Linux (GNOME Files / KDE Dolphin e Terminal)
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

# Detecta modo headless em flags ou variável de ambiente
IS_HEADLESS=0
if [[ "${LOCALCLIP_HEADLESS:-}" =~ ^(1|true|yes)$ ]]; then
    IS_HEADLESS=1
fi
for arg in "$@"; do
    if [ "$arg" = "--headless" ] || [ "$arg" = "--no-browser" ]; then
        IS_HEADLESS=1
    fi
done

CMD="start"
if [ "$1" = "status" ] || [ "$1" = "stop" ] || [ "$1" = "restart" ]; then
    CMD="$1"
    shift
fi

"$PYTHON_EXEC" "$PROJECT_DIR/scripts/supervisor.py" "$CMD" --repo-dir "$PROJECT_DIR" "$@"
EXIT_CODE=$?

# Exibe feedback gráfico apenas se invocado graficamente, display ativo E não estiver em modo headless
if [ ! -t 1 ] && [ "$IS_HEADLESS" -eq 0 ] && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
    if [ $EXIT_CODE -ne 0 ]; then
        LOG_DIR="${LOCALCLIP_LOG_DIR:-$HOME/.local/state/localclip/logs}"
        MSG="Não foi possível iniciar o LocalClip. Consulte os registros em:\n$LOG_DIR"
        if [ "${XDG_CURRENT_DESKTOP:-}" = "KDE" ] && command -v kdialog >/dev/null 2>&1; then
            kdialog --error "$MSG" --title "LocalClip" 2>/dev/null || true
        elif command -v zenity >/dev/null 2>&1; then
            zenity --error --title="LocalClip" --text="$MSG" --timeout=10 2>/dev/null || true
        elif command -v kdialog >/dev/null 2>&1; then
            kdialog --error "$MSG" --title "LocalClip" 2>/dev/null || true
        elif command -v notify-send >/dev/null 2>&1; then
            notify-send -u critical "LocalClip" "$MSG" 2>/dev/null || true
        fi
    elif [ "$CMD" = "start" ] || [ "$CMD" = "restart" ]; then
        if command -v notify-send >/dev/null 2>&1; then
            notify-send "LocalClip" "Servidor iniciado com sucesso." --icon=video-player 2>/dev/null || true
        fi
    fi
fi

exit $EXIT_CODE
