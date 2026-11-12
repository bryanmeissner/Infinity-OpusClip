#!/usr/bin/env python3
"""LocalClip Process Supervisor: singleton determinístico e parada segura."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def ensure_user_path() -> None:
    path_env = os.environ.get("PATH", "")
    parts = path_env.split(os.pathsep) if path_env else []
    for extra in (Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin"):
        s = str(extra)
        if extra.is_dir() and s not in parts:
            parts.insert(0, s)
    os.environ["PATH"] = os.pathsep.join(parts)


ensure_user_path()


def get_runtime_dir() -> Path:
    env = os.environ.get("LOCALCLIP_RUNTIME_DIR")
    if env:
        p = Path(env).expanduser().resolve()
    else:
        xdg = os.environ.get("XDG_RUNTIME_DIR")
        base = Path(xdg) if xdg else Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        p = (base / "localclip" / ("run" if not xdg else "")).resolve()
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        p.chmod(0o700)
    except OSError:
        pass
    return p


def get_log_dir() -> Path:
    env = os.environ.get("LOCALCLIP_LOG_DIR")
    base = Path(env) if env else Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "localclip" / "logs"
    p = base.expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        p.chmod(0o700)
    except OSError:
        pass
    return p


@contextlib.contextmanager
def acquire_lifecycle_lock(runtime_dir: Path, port: int):
    runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_file = runtime_dir / f"supervisor_{port}.lock"
    fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def state_file_path(runtime_dir: Path, port: int) -> Path:
    return runtime_dir / f"instance_{port}.json"


def load_state(runtime_dir: Path, port: int) -> dict | None:
    path = state_file_path(runtime_dir, port)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        required = ("pid", "starttime", "pgid", "session", "repo_dir", "cmdline", "port")
        if isinstance(data, dict) and all(data.get(k) is not None for k in required):
            return data
    except Exception:
        pass
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def save_state(runtime_dir: Path, port: int, data: dict) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state_file_path(runtime_dir, port)
    temp = runtime_dir / f".tmp_{port}_{os.getpid()}_{time.time_ns()}.json"
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    temp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def remove_state(runtime_dir: Path, port: int) -> None:
    try:
        state_file_path(runtime_dir, port).unlink(missing_ok=True)
    except OSError:
        pass


def get_proc_stat(pid: int) -> dict | None:
    try:
        content = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    comm_end, comm_start = content.rfind(")"), content.find("(")
    if comm_end == -1 or comm_start == -1 or comm_end < comm_start:
        return None
    rest = content[comm_end + 2 :].split()
    if len(rest) < 20:
        return None
    try:
        return {
            "pid": pid,
            "comm": content[comm_start + 1 : comm_end],
            "state": rest[0],
            "ppid": int(rest[1]),
            "pgrp": int(rest[2]),
            "session": int(rest[3]),
            "starttime": int(rest[19]),
        }
    except (ValueError, IndexError):
        return None


def get_proc_cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return [p.decode("utf-8", errors="replace") for p in raw.split(b"\x00") if p]
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return []


def verify_owned_identity(state: dict, expected_repo: Path) -> bool:
    """Verifica identidade estrita do processo. Rejeita se qualquer campo faltar ou divergir."""
    required = ("pid", "starttime", "pgid", "session", "repo_dir", "cmdline", "port")
    if not isinstance(state, dict) or not all(state.get(k) is not None for k in required):
        return False

    pid = state["pid"]
    if pid <= 0:
        return False

    stat = get_proc_stat(pid)
    if stat is None or stat.get("state") in ("Z", "X"):
        return False

    # 1. starttime, pgid e session devem conferir exatamente
    if stat["starttime"] != state["starttime"]:
        return False
    if stat["pgrp"] != state["pgid"] or stat["session"] != state["session"]:
        return False

    # 2. repo_dir registrado e /proc/<pid>/cwd DEVEM conferir com o repo esperado
    try:
        expected_resolved = expected_repo.resolve()
        state_repo_resolved = Path(state["repo_dir"]).resolve()
        proc_cwd = Path(f"/proc/{pid}/cwd").resolve()
        if state_repo_resolved != expected_resolved or proc_cwd != expected_resolved:
            return False
    except (OSError, PermissionError):
        return False

    # 3. Linha de comando real deve coincidir com a linha capturada e conter porta/executável
    actual_cmdline = get_proc_cmdline(pid)
    recorded_cmdline = state["cmdline"]
    if actual_cmdline != recorded_cmdline:
        match_with_python_prefix = (
            (len(actual_cmdline) == len(recorded_cmdline) + 1 and actual_cmdline[1:] == recorded_cmdline and "python" in actual_cmdline[0])
            or (len(recorded_cmdline) == len(actual_cmdline) + 1 and recorded_cmdline[1:] == actual_cmdline and "python" in recorded_cmdline[0])
        )
        if not match_with_python_prefix:
            return False

    cmd_str = " ".join(actual_cmdline)
    if str(state["port"]) not in cmd_str:
        return False
    if not any(token in cmd_str for token in ("localclip", "uvicorn")):
        return False

    return True


def find_descendants(parent_pid: int) -> dict[int, int]:
    """Descobre descendentes {pid: starttime} para workers, ffmpeg e jobs."""
    descendants: dict[int, int] = {}
    current_parents = {parent_pid}
    while current_parents:
        next_parents: set[int] = set()
        try:
            entries = os.listdir("/proc")
        except OSError:
            break
        for entry in entries:
            if not entry.isdigit():
                continue
            c_pid = int(entry)
            if c_pid in descendants or c_pid == parent_pid:
                continue
            stat = get_proc_stat(c_pid)
            if stat and stat["ppid"] in current_parents and stat.get("state") not in ("Z", "X"):
                descendants[c_pid] = stat["starttime"]
                next_parents.add(c_pid)
        current_parents = next_parents
    return descendants


def is_child_alive(pid: int, expected_starttime: int) -> bool:
    stat = get_proc_stat(pid)
    return bool(stat and stat.get("state") not in ("Z", "X") and stat["starttime"] == expected_starttime)


def is_port_listening(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def is_port_in_use(host: str, port: int) -> bool:
    if is_port_listening(host, port):
        return True
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # Match Uvicorn's bind policy: closed HTTP connections in TIME_WAIT
            # must not prevent an immediate restart. Live listeners are still refused.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return False
    except OSError:
        return True


def check_service_ready(host: str, port: int) -> bool:
    """Exige HTTP 200 no root (frontend montado) E HTTP 200 em /api/projects."""
    try:
        with urllib.request.urlopen(urllib.request.Request(f"http://{host}:{port}/"), timeout=1.5) as r1:
            if r1.status != 200:
                return False
        with urllib.request.urlopen(urllib.request.Request(f"http://{host}:{port}/api/projects"), timeout=1.5) as r2:
            return r2.status == 200
    except Exception:
        return False


def is_frontend_built(repo_dir: Path) -> bool:
    dist_index = repo_dir / "web" / "dist" / "index.html"
    if not dist_index.is_file():
        return False
    dist_mtime = dist_index.stat().st_mtime
    web_dir = repo_dir / "web"
    for root, _, files in os.walk(web_dir / "src"):
        for f in files:
            if (Path(root) / f).stat().st_mtime > dist_mtime:
                return False
    for fname in ("index.html", "vite.config.ts", "package.json"):
        fpath = web_dir / fname
        if fpath.is_file() and fpath.stat().st_mtime > dist_mtime:
            return False
    return True


def is_venv_ready(repo_dir: Path) -> bool:
    marker = repo_dir / ".venv" / ".localclip_synced"
    py = repo_dir / ".venv" / "bin" / "python"
    if not py.is_file() or not marker.is_file():
        return False
    h = hashlib.sha256()
    for f in (repo_dir / "uv.lock", repo_dir / "pyproject.toml"):
        if f.is_file():
            h.update(f.read_bytes())
    try:
        return marker.read_text(encoding="utf-8").strip() == h.hexdigest()
    except OSError:
        return False


def check_prerequisites(need_build: bool, repo_dir: Path | None = None) -> tuple[bool, list[str]]:
    ensure_user_path()
    errs = []
    if platform.system() != "Linux":
        errs.append("LocalClip requer Linux.")
    if sys.version_info < (3, 12):
        errs.append(f"Python >= 3.12 obrigatório (atual: {sys.version.split()[0]}). No Fedora: sudo dnf install python3.12")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            errs.append(f"Pré-requisito do sistema ausente: '{tool}'. No Fedora Linux: sudo dnf install ffmpeg (com RPM Fusion para suporte total a codecs).")

    venv_ok = repo_dir is not None and is_venv_ready(repo_dir) and (repo_dir / ".venv" / "bin" / "python").is_file()
    if not venv_ok:
        if not shutil.which("uv"):
            errs.append("Pré-requisito ausente: 'uv' (necessário para criar e sincronizar o ambiente virtual). Para instalar no seu usuário sem sudo: curl -LsSf https://astral.sh/uv/install.sh | sh")

    if need_build:
        if not shutil.which("node"):
            errs.append("Pré-requisito ausente: 'node' (necessário para compilar o frontend). No Fedora: sudo dnf install nodejs")
        if not shutil.which("npm"):
            errs.append("Pré-requisito ausente: 'npm' (necessário para compilar o frontend). No Fedora: sudo dnf install npm")
    return len(errs) == 0, errs


def ensure_dependencies(repo_dir: Path) -> tuple[bool, str]:
    ensure_user_path()
    if not is_venv_ready(repo_dir):
        if not shutil.which("uv"):
            return False, "'uv' não encontrado para sincronizar ambiente. Instale sem sudo com: curl -LsSf https://astral.sh/uv/install.sh | sh"
        if subprocess.run(["uv", "sync", "--extra", "dev"], cwd=str(repo_dir)).returncode != 0:
            return False, "Falha ao executar uv sync."
        h = hashlib.sha256()
        for f in (repo_dir / "uv.lock", repo_dir / "pyproject.toml"):
            if f.is_file():
                h.update(f.read_bytes())
        try:
            (repo_dir / ".venv" / ".localclip_synced").write_text(h.hexdigest(), encoding="utf-8")
        except OSError:
            pass

    if not is_frontend_built(repo_dir):
        if not shutil.which("npm"):
            return False, "'npm' não encontrado para compilar frontend. Instale com: sudo dnf install npm"
        web_dir = repo_dir / "web"
        if not (web_dir / "node_modules").is_dir():
            if subprocess.run(["npm", "install"], cwd=str(web_dir)).returncode != 0:
                return False, "Falha ao executar npm install."
        if subprocess.run(["npm", "run", "build"], cwd=str(web_dir)).returncode != 0:
            return False, "Falha ao executar npm run build."
        if not (web_dir / "dist" / "index.html").is_file():
            return False, "web/dist/index.html não foi gerado."
    return True, ""


def open_browser(url: str) -> None:
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        try:
            webbrowser.open(url)
        except Exception:
            pass


def cmd_start(repo_dir: Path, host: str = "127.0.0.1", port: int = 8765, headless: bool = False, timeout: float = 25.0) -> int:
    ensure_user_path()
    runtime_dir = get_runtime_dir()
    log_dir = get_log_dir()

    with acquire_lifecycle_lock(runtime_dir, port):
        state = load_state(runtime_dir, port)
        if state:
            if verify_owned_identity(state, repo_dir):
                if is_port_listening(host, port):
                    url = f"http://{host}:{port}"
                    print(f"LocalClip já está em execução em {url} (PID: {state['pid']}).")
                    if not headless:
                        open_browser(url)
                    return 0
            else:
                remove_state(runtime_dir, port)

        if is_port_in_use(host, port):
            print(f"Erro: A porta {port} já está em uso por outro processo.", file=sys.stderr)
            return 1

        need_build = not (repo_dir / "web" / "dist" / "index.html").is_file()
        ok_p, errs = check_prerequisites(need_build, repo_dir=repo_dir)
        if not ok_p:
            for e in errs:
                print(f"Erro: {e}", file=sys.stderr)
            return 1

        ok_d, d_err = ensure_dependencies(repo_dir)
        if not ok_d:
            print(f"Erro ao preparar dependências: {d_err}", file=sys.stderr)
            return 1

        py_bin = repo_dir / ".venv" / "bin" / "python"
        if not py_bin.is_file():
            py_bin = Path(sys.executable)

        venv_bin = repo_dir / ".venv" / "bin" / "localclip"
        if venv_bin.is_file():
            cmd = [str(py_bin), str(venv_bin), "--port", str(port)]
        else:
            cmd = [str(py_bin), "-m", "localclip.app", "--port", str(port)]

        log_path = log_dir / f"localclip_{port}.log"
        fd = os.open(str(log_path), os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        try:
            os.chmod(log_path, 0o600)
            os.write(fd, f"\n=== LocalClip iniciado {time.strftime('%Y-%m-%d %H:%M:%S')} (porta {port}) ===\n".encode("utf-8"))
            proc = subprocess.Popen(cmd, cwd=str(repo_dir), stdout=fd, stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            os.close(fd)

        pid = proc.pid
        stat = None
        for _ in range(20):
            if proc.poll() is not None:
                break
            stat = get_proc_stat(pid)
            if stat and stat.get("starttime"):
                break
            time.sleep(0.05)

        captured_cmdline = get_proc_cmdline(pid) or cmd

        state_data = {
            "pid": pid,
            "starttime": stat["starttime"] if stat else 0,
            "pgid": stat["pgrp"] if stat else pid,
            "session": stat["session"] if stat else pid,
            "repo_dir": str(repo_dir.resolve()),
            "cmdline": captured_cmdline,
            "port": port,
            "host": host,
            "log_file": str(log_path),
            "created_at": time.time(),
        }
        save_state(runtime_dir, port, state_data)

        print(f"Iniciando LocalClip na porta {port} (PID: {pid})...")
        deadline = time.time() + timeout
        ready = False
        while time.time() < deadline:
            if proc.poll() is not None:
                log_tail = ""
                try:
                    if log_path.is_file():
                        lines = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
                        log_tail = "\n".join(lines[-10:])
                except Exception:
                    pass
                remove_state(runtime_dir, port)
                msg = f"Erro: O processo encerrou com código {proc.returncode}."
                if log_tail:
                    msg += f"\nÚltimas linhas do log ({log_path}):\n{log_tail}"
                print(msg, file=sys.stderr)
                return 1
            if is_port_listening(host, port) and check_service_ready(host, port):
                ready = True
                break
            time.sleep(0.2)

        if not ready:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            remove_state(runtime_dir, port)
            print(f"Erro: Tempo limite de {timeout:.1f}s excedido aguardando serviço.", file=sys.stderr)
            return 1

        url = f"http://{host}:{port}"
        print(f"LocalClip iniciado com sucesso!\nURL: {url}\nPID: {pid}\nLogs: {log_path}")
        if not headless:
            open_browser(url)
        return 0


def cmd_stop(repo_dir: Path, host: str = "127.0.0.1", port: int = 8765, timeout: float = 12.0) -> int:
    runtime_dir = get_runtime_dir()

    with acquire_lifecycle_lock(runtime_dir, port):
        state = load_state(runtime_dir, port)
        if not state:
            if is_port_in_use(host, port):
                print(f"Aviso: A porta {port} está ocupada por outro processo não pertencente ao LocalClip.", file=sys.stderr)
            else:
                print(f"LocalClip não está em execução na porta {port}.")
            return 0

        if not verify_owned_identity(state, repo_dir):
            remove_state(runtime_dir, port)
            if is_port_in_use(host, port):
                print(f"Aviso: A porta {port} está ocupada por outro processo não pertencente ao LocalClip.", file=sys.stderr)
            else:
                print("Registro antigo inválido/reciclado limpo. LocalClip não está em execução.")
            return 0

        pid = state["pid"]
        start_time = state["starttime"]
        descendants = find_descendants(pid)

        stat = get_proc_stat(pid)
        actual_pgid = stat.get("pgrp") if stat else None

        if actual_pgid == pid:
            try:
                os.killpg(pid, signal.SIGTERM)
            except OSError:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            for d_pid, d_start in descendants.items():
                if is_child_alive(d_pid, d_start):
                    try:
                        os.kill(d_pid, signal.SIGTERM)
                    except OSError:
                        pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            cur = get_proc_stat(pid)
            if cur is None or cur.get("state") in ("Z", "X") or cur["starttime"] != start_time:
                break
            time.sleep(0.15)

        cur = get_proc_stat(pid)
        if cur and cur.get("state") not in ("Z", "X") and cur["starttime"] == start_time:
            if actual_pgid == pid:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except OSError:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass

        time.sleep(0.15)
        new_descendants = find_descendants(pid)
        descendants.update(new_descendants)
        for d_pid, d_start in descendants.items():
            if is_child_alive(d_pid, d_start):
                try:
                    os.kill(d_pid, signal.SIGKILL)
                except OSError:
                    pass
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass

        remove_state(runtime_dir, port)
        print(f"LocalClip (PID {pid}) encerrado com sucesso.")
        return 0


def cmd_restart(repo_dir: Path, host: str = "127.0.0.1", port: int = 8765, headless: bool = False, timeout: float = 25.0) -> int:
    stop_ret = cmd_stop(repo_dir=repo_dir, host=host, port=port, timeout=min(timeout / 2, 12.0))
    if stop_ret != 0:
        return stop_ret
    time.sleep(0.5)
    return cmd_start(repo_dir=repo_dir, host=host, port=port, headless=headless, timeout=timeout)

def cmd_status(repo_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> int:
    runtime_dir = get_runtime_dir()
    with acquire_lifecycle_lock(runtime_dir, port):
        state = load_state(runtime_dir, port)
        if state:
            if verify_owned_identity(state, repo_dir):
                listening = is_port_listening(host, port)
                ready = check_service_ready(host, port) if listening else False
                print(f"Status: EM EXECUÇÃO\nPID: {state['pid']}\nPorta: {port}\nURL: http://{host}:{port}\nPronto: {'Sim' if ready else 'Não'}\nLogs: {state.get('log_file', 'N/A')}")
                return 0
            else:
                remove_state(runtime_dir, port)

        if is_port_in_use(host, port):
            print(f"Status: PARADO\nAviso: Porta {port} ocupada por outro processo não pertencente ao LocalClip.")
            return 1

        print(f"Status: PARADO\nPorta {port} está livre.")
        return 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervisor do LocalClip")
    sub = parser.add_subparsers(dest="command", required=True)

    start_p = sub.add_parser("start")
    start_p.add_argument("--headless", "--no-browser", action="store_true", default=os.environ.get("LOCALCLIP_HEADLESS", "").lower() in ("1", "true", "yes"))
    start_p.add_argument("--port", type=int, default=int(os.environ.get("LOCALCLIP_PORT", "8765")))
    start_p.add_argument("--host", type=str, default=os.environ.get("LOCALCLIP_HOST", "127.0.0.1"))
    start_p.add_argument("--timeout", type=float, default=25.0)
    start_p.add_argument("--repo-dir", type=str, default=os.environ.get("LOCALCLIP_REPO_DIR", str(Path(__file__).resolve().parents[1])))

    stop_p = sub.add_parser("stop")
    stop_p.add_argument("--port", type=int, default=int(os.environ.get("LOCALCLIP_PORT", "8765")))
    stop_p.add_argument("--host", type=str, default=os.environ.get("LOCALCLIP_HOST", "127.0.0.1"))
    stop_p.add_argument("--timeout", type=float, default=12.0)
    stop_p.add_argument("--repo-dir", type=str, default=os.environ.get("LOCALCLIP_REPO_DIR", str(Path(__file__).resolve().parents[1])))

    stop_p.add_argument("--headless", "--no-browser", action="store_true", default=os.environ.get("LOCALCLIP_HEADLESS", "").lower() in ("1", "true", "yes"))

    restart_p = sub.add_parser("restart")
    restart_p.add_argument("--headless", "--no-browser", action="store_true", default=os.environ.get("LOCALCLIP_HEADLESS", "").lower() in ("1", "true", "yes"))
    restart_p.add_argument("--port", type=int, default=int(os.environ.get("LOCALCLIP_PORT", "8765")))
    restart_p.add_argument("--host", type=str, default=os.environ.get("LOCALCLIP_HOST", "127.0.0.1"))
    restart_p.add_argument("--timeout", type=float, default=25.0)
    restart_p.add_argument("--repo-dir", type=str, default=os.environ.get("LOCALCLIP_REPO_DIR", str(Path(__file__).resolve().parents[1])))
    status_p = sub.add_parser("status")
    status_p.add_argument("--port", type=int, default=int(os.environ.get("LOCALCLIP_PORT", "8765")))
    status_p.add_argument("--host", type=str, default=os.environ.get("LOCALCLIP_HOST", "127.0.0.1"))
    status_p.add_argument("--repo-dir", type=str, default=os.environ.get("LOCALCLIP_REPO_DIR", str(Path(__file__).resolve().parents[1])))

    args = parser.parse_args()
    repo_dir = Path(args.repo_dir).resolve()

    if args.command == "start":
        return cmd_start(repo_dir=repo_dir, host=args.host, port=args.port, headless=args.headless, timeout=args.timeout)
    elif args.command == "stop":
        return cmd_stop(repo_dir=repo_dir, host=args.host, port=args.port, timeout=args.timeout)
    elif args.command == "restart":
        return cmd_restart(repo_dir=repo_dir, host=args.host, port=args.port, headless=args.headless, timeout=args.timeout)
    elif args.command == "status":
        return cmd_status(repo_dir=repo_dir, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
