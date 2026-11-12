import contextlib
import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import supervisor


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_lifecycle_flock_concurrency(tmp_path):
    """Verifica se acquire_lifecycle_lock serializa operações concorrentes via fcntl flock."""
    run_dir = tmp_path / "run"
    port = get_free_port()
    order = []

    def task(task_id: int):
        with supervisor.acquire_lifecycle_lock(run_dir, port):
            order.append(f"enter_{task_id}")
            time.sleep(0.1)
            order.append(f"exit_{task_id}")

    t1 = threading.Thread(target=task, args=(1,))
    t2 = threading.Thread(target=task, args=(2,))
    t1.start()
    time.sleep(0.02)
    t2.start()
    t1.join()
    t2.join()

    assert order in (
        ["enter_1", "exit_1", "enter_2", "exit_2"],
        ["enter_2", "exit_2", "enter_1", "exit_1"],
    )


def test_verify_owned_identity_strict(tmp_path):
    """Testa verify_owned_identity com processo filho real simulando localclip."""
    port = get_free_port()
    # Inicia processo filho real com comando identificável e nova sessão
    proc = subprocess.Popen(
        [sys.executable, "-c", "# localclip test process\nimport time; time.sleep(10)", "--port", str(port)],
        cwd=str(PROJECT_ROOT),
        start_new_session=True,
    )
    try:
        pid = proc.pid
        time.sleep(0.05)
        stat = supervisor.get_proc_stat(pid)
        assert stat is not None
        cmdline = supervisor.get_proc_cmdline(pid)

        valid_state = {
            "pid": pid,
            "starttime": stat["starttime"],
            "pgid": stat["pgrp"],
            "session": stat["session"],
            "repo_dir": str(PROJECT_ROOT.resolve()),
            "cmdline": cmdline,
            "port": port,
        }

        # 1. Identidade real deve ser aceita
        assert supervisor.verify_owned_identity(valid_state, PROJECT_ROOT) is True

        # 2. starttime divergente (reuso de PID pelo SO) => rejeitar
        stale_start = dict(valid_state, starttime=stat["starttime"] + 12345)
        assert supervisor.verify_owned_identity(stale_start, PROJECT_ROOT) is False

        # 3. pgid divergente => rejeitar
        bad_pgid = dict(valid_state, pgid=stat["pgrp"] + 999)
        assert supervisor.verify_owned_identity(bad_pgid, PROJECT_ROOT) is False

        # 4. repo_dir divergente do repo esperado => rejeitar
        bad_repo = dict(valid_state, repo_dir=str(tmp_path / "outro_repo"))
        assert supervisor.verify_owned_identity(bad_repo, PROJECT_ROOT) is False
        assert supervisor.verify_owned_identity(valid_state, tmp_path / "outro_repo") is False

        # 5. Linha de comando modificada => rejeitar
        bad_cmd = dict(valid_state, cmdline=["bash", "-i"])
        assert supervisor.verify_owned_identity(bad_cmd, PROJECT_ROOT) is False

        # 6. Campo obrigatório ausente => rejeitar
        for k in ("pid", "starttime", "pgid", "session", "repo_dir", "cmdline", "port"):
            missing_state = dict(valid_state)
            del missing_state[k]
            assert supervisor.verify_owned_identity(missing_state, PROJECT_ROOT) is False
    finally:
        proc.terminate()
        proc.wait()


def test_descendants_tracking_and_pid_reuse():
    """Valida captura de {pid: starttime} de descendentes e proteção contra reuso de PID em filhos."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        descendants = supervisor.find_descendants(os.getpid())
        assert proc.pid in descendants
        captured_start = descendants[proc.pid]

        assert supervisor.is_child_alive(proc.pid, captured_start) is True
        assert supervisor.is_child_alive(proc.pid, captured_start + 999999) is False
    finally:
        proc.terminate()
        proc.wait()


def test_refuse_killpg_when_pgid_mismatch(tmp_path, monkeypatch):
    """Garante que cmd_stop não invoca os.killpg se actual_pgid != pid."""
    port = get_free_port()
    run_dir = tmp_path / "run"
    monkeypatch.setenv("LOCALCLIP_RUNTIME_DIR", str(run_dir))

    # Cria processo filho que NÃO é líder de grupo (sem start_new_session)
    child = subprocess.Popen([sys.executable, "-c", "# localclip child\nimport time; time.sleep(5)", "--port", str(port)], cwd=str(PROJECT_ROOT))
    try:
        stat = supervisor.get_proc_stat(child.pid)
        assert stat is not None
        assert stat["pgrp"] != child.pid  # não é líder de grupo

        state = {
            "pid": child.pid,
            "starttime": stat["starttime"],
            "pgid": stat["pgrp"],
            "session": stat["session"],
            "repo_dir": str(PROJECT_ROOT.resolve()),
            "cmdline": supervisor.get_proc_cmdline(child.pid),
            "port": port,
        }
        supervisor.save_state(run_dir, port, state)

        killed_pgids = []
        monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed_pgids.append(pgid))

        supervisor.cmd_stop(repo_dir=PROJECT_ROOT, port=port, timeout=0.1)

        # Como o processo não é líder de grupo, killpg NUNCA pode ter sido chamado
        assert len(killed_pgids) == 0
    finally:
        child.terminate()
        child.wait()


def test_readiness_requires_both_root_and_bootstrap_200():
    """Valida que check_service_ready exige HTTP 200 no root e em /api/projects (503 é rejeitado)."""
    with patch("urllib.request.urlopen") as mock_url:
        resp_503 = MagicMock()
        resp_503.status = 503
        resp_503.__enter__.return_value = resp_503
        mock_url.return_value = resp_503
        assert supervisor.check_service_ready("127.0.0.1", 8765) is False

    with patch("urllib.request.urlopen") as mock_url:
        resp_200 = MagicMock()
        resp_200.status = 200
        resp_200.__enter__.return_value = resp_200
        mock_url.side_effect = [resp_200, urllib.error.URLError("Connection refused")]
        assert supervisor.check_service_ready("127.0.0.1", 8765) is False

    with patch("urllib.request.urlopen") as mock_url:
        resp_200_a = MagicMock()
        resp_200_a.status = 200
        resp_200_a.__enter__.return_value = resp_200_a

        resp_200_b = MagicMock()
        resp_200_b.status = 200
        resp_200_b.__enter__.return_value = resp_200_b

        mock_url.side_effect = [resp_200_a, resp_200_b]
        assert supervisor.check_service_ready("127.0.0.1", 8765) is True


def test_unrelated_process_on_port_rejected(tmp_path, monkeypatch):
    """Garante que socket estrangeiro na porta impede cmd_start e não é tocado por cmd_stop."""
    port = get_free_port()
    run_dir = tmp_path / "run"
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("LOCALCLIP_RUNTIME_DIR", str(run_dir))
    monkeypatch.setenv("LOCALCLIP_LOG_DIR", str(log_dir))

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(5)
    srv.settimeout(0.2)

    stop_flag = False

    def accept_loop():
        while not stop_flag:
            try:
                conn, _ = srv.accept()
                conn.close()
            except (socket.timeout, OSError):
                pass

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()

    try:
        ret = supervisor.cmd_start(
            repo_dir=PROJECT_ROOT,
            host="127.0.0.1",
            port=port,
            headless=True,
            timeout=1.0,
        )
        assert ret == 1
        assert supervisor.load_state(run_dir, port) is None

        stop_ret = supervisor.cmd_stop(repo_dir=PROJECT_ROOT, host="127.0.0.1", port=port)
        assert stop_ret == 0

        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.connect(("127.0.0.1", port))
        c.close()
    finally:
        stop_flag = True
        srv.close()
        t.join(timeout=1.0)


def test_headless_mode_suppression(monkeypatch):
    """Verifica que o modo headless suprime webbrowser.open."""
    opened_urls = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened_urls.append(url))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    # Sem display, open_browser não abre nada
    supervisor.open_browser("http://127.0.0.1:8765")
    assert len(opened_urls) == 0


def test_private_permissions_enforced(tmp_path, monkeypatch):
    """Garante permissões 0700 para diretórios e 0600 para arquivos de estado e trava."""
    run_dir = tmp_path / "private_run"
    log_dir = tmp_path / "private_log"
    monkeypatch.setenv("LOCALCLIP_RUNTIME_DIR", str(run_dir))
    monkeypatch.setenv("LOCALCLIP_LOG_DIR", str(log_dir))

    d_run = supervisor.get_runtime_dir()
    d_log = supervisor.get_log_dir()

    assert oct(d_run.stat().st_mode)[-3:] == "700"
    assert oct(d_log.stat().st_mode)[-3:] == "700"

    port = get_free_port()
    state = {
        "pid": 1234,
        "starttime": 1,
        "pgid": 1234,
        "session": 1234,
        "repo_dir": str(PROJECT_ROOT),
        "cmdline": ["python3", "-m", "localclip", "--port", str(port)],
        "port": port,
    }
    supervisor.save_state(d_run, port, state)
    state_file = supervisor.state_file_path(d_run, port)
    assert oct(state_file.stat().st_mode)[-3:] == "600"

    with supervisor.acquire_lifecycle_lock(d_run, port):
        lock_file = d_run / f"supervisor_{port}.lock"
        assert oct(lock_file.stat().st_mode)[-3:] == "600"




def test_is_frontend_built_checks_root_assets(tmp_path):
    """Valida que is_frontend_built invalida o build se index.html ou vite.config.ts forem mais recentes."""
    repo = tmp_path / "repo com espacos"
    dist = repo / "web" / "dist"
    src = repo / "web" / "src"
    dist.mkdir(parents=True)
    src.mkdir(parents=True)

    dist_index = dist / "index.html"
    app_file = src / "App.tsx"
    root_index = repo / "web" / "index.html"
    vite_cfg = repo / "web" / "vite.config.ts"

    # 1. Sem dist/index.html => não construído
    assert supervisor.is_frontend_built(repo) is False

    # 2. dist/index.html mais novo que os fontes => construído
    now = time.time()
    app_file.write_text("export default function App() {}", encoding="utf-8")
    root_index.write_text("<!doctype html><html></html>", encoding="utf-8")
    vite_cfg.write_text("export default {}", encoding="utf-8")
    os.utime(app_file, (now - 10, now - 10))
    os.utime(root_index, (now - 10, now - 10))
    os.utime(vite_cfg, (now - 10, now - 10))

    dist_index.write_text("<!doctype html><html>dist</html>", encoding="utf-8")
    os.utime(dist_index, (now, now))
    assert supervisor.is_frontend_built(repo) is True

    # 3. web/index.html editado após o build => requer recompilação
    os.utime(root_index, (now + 5, now + 5))
    assert supervisor.is_frontend_built(repo) is False

    # 4. Atualizar dist e editar vite.config.ts => requer recompilação
    os.utime(dist_index, (now + 10, now + 10))
    assert supervisor.is_frontend_built(repo) is True
    os.utime(vite_cfg, (now + 15, now + 15))
    assert supervisor.is_frontend_built(repo) is False




def test_verify_owned_identity_accepts_python_shebang_prefix(tmp_path):
    """Garante que verify_owned_identity aceita processo quando cmdline real tem prefixo do interpretador."""
    port = get_free_port()
    proc = subprocess.Popen(
        [sys.executable, "-c", "# localclip test runner\nimport time; time.sleep(10)", "--port", str(port)],
        cwd=str(PROJECT_ROOT),
        start_new_session=True,
    )
    try:
        pid = proc.pid
        time.sleep(0.05)
        stat = supervisor.get_proc_stat(pid)
        assert stat is not None
        actual_cmd = supervisor.get_proc_cmdline(pid)

        # Se o script salvou sem o executável python inicial (como ocorre ao lançar shebang script diretamente)
        recorded_without_python = actual_cmd[1:] if "python" in actual_cmd[0] else actual_cmd
        state = {
            "pid": pid,
            "starttime": stat["starttime"],
            "pgid": stat["pgrp"],
            "session": stat["session"],
            "repo_dir": str(PROJECT_ROOT.resolve()),
            "cmdline": recorded_without_python,
            "port": port,
        }
        assert supervisor.verify_owned_identity(state, PROJECT_ROOT) is True
    finally:
        proc.terminate()
        proc.wait()



def test_closed_http_connection_does_not_block_immediate_restart():
    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, 0))
        port = server.getsockname()[1]
        server.listen(4)
        with socket.create_connection((host, port), timeout=2) as client:
            connection, _ = server.accept()
            connection.close()
            assert client.recv(1) == b""
    assert supervisor.is_port_in_use(host, port) is False
