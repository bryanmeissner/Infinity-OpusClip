import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


def data_root() -> Path:
    root = Path(os.environ.get('LOCALCLIP_DATA_DIR', Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'localclip')).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root


def cache_root() -> Path:
    root = Path(os.environ.get('LOCALCLIP_CACHE_DIR', Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'localclip')).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root


def uid():
    return uuid4().hex


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


@contextmanager
def connection():
    db = sqlite3.connect(data_root()/'localclip.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    with connection() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT, created_at REAL NOT NULL,
          metadata TEXT NOT NULL DEFAULT '{}', options TEXT NOT NULL DEFAULT '{}',
          status TEXT NOT NULL DEFAULT 'importing', error TEXT);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
          kind TEXT NOT NULL, candidate_id TEXT, state TEXT NOT NULL DEFAULT 'queued',
          stage TEXT NOT NULL DEFAULT 'Na fila', progress REAL NOT NULL DEFAULT 0,
          payload TEXT NOT NULL, error TEXT, cancel INTEGER NOT NULL DEFAULT 0,
          created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS candidates (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
          position INTEGER NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS providers (id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS usage (
          id INTEGER PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
          created_at REAL NOT NULL, data TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS job_queue ON jobs(state,created_at);
        CREATE INDEX IF NOT EXISTS project_candidates ON candidates(project_id,position);
        ''')
        # Existing installations retain project names and all jobs.
        project_columns = {r['name'] for r in db.execute('PRAGMA table_info(projects)')}
        for column in ('display_name', 'original_filename', 'source_title'):
            if column not in project_columns:
                db.execute(f'ALTER TABLE projects ADD COLUMN {column} TEXT')
        db.execute("UPDATE projects SET display_name=name WHERE display_name IS NULL")
        job_columns = {r['name'] for r in db.execute('PRAGMA table_info(jobs)')}
        for column, definition in (
            ('checkpoint', "TEXT NOT NULL DEFAULT '{}'"),
            ('attempts', 'INTEGER NOT NULL DEFAULT 0'),
            ('failed_provider', 'TEXT'),
        ):
            if column not in job_columns:
                db.execute(f'ALTER TABLE jobs ADD COLUMN {column} {definition}')
        db.execute("UPDATE jobs SET state='interrupted', stage='Interrompido', error='Processo interrompido; execute novamente.' WHERE state='running'")
        db.execute("UPDATE projects SET status='interrupted', error='Processamento interrompido.' WHERE status IN ('processing','rendering')")


def project_dir(pid):
    # IDs generated internally; never permit filesystem paths through API identifiers.
    if not isinstance(pid, str) or len(pid) != 32 or any(c not in '0123456789abcdef' for c in pid):
        raise KeyError('Projeto não encontrado.')
    path = data_root()/'projects'/pid
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def create_project(name, source=None, metadata=None):
    pid = uid()
    project_dir(pid)
    with connection() as db:
        db.execute('INSERT INTO projects(id,name,display_name,source,created_at,metadata,status) VALUES(?,?,?,?,?,?,?)',
                   (pid, name[:250], name[:250], str(source) if source else None, time.time(), dumps(metadata or {}), 'ready' if source else 'importing'))
    return pid


def list_projects():
    with connection() as db:
        rows = db.execute('SELECT id,name,display_name,original_filename,source_title,metadata,options,status,error,created_at FROM projects ORDER BY created_at DESC').fetchall()
    return [{**dict(r), 'metadata': json.loads(r['metadata']), 'options': json.loads(r['options'])} for r in rows]


def get_project(pid, internal=False):
    with connection() as db:
        row = db.execute('SELECT * FROM projects WHERE id=?', (pid,)).fetchone()
        if row is None:
            raise KeyError('Projeto não encontrado.')
        jobs = db.execute('SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC', (pid,)).fetchall()
        candidates = db.execute('SELECT data FROM candidates WHERE project_id=? ORDER BY position', (pid,)).fetchall()
    value = dict(row)
    for field in ['metadata', 'options']:
        value[field] = json.loads(value[field])
    value['jobs'] = [public_job(r) for r in jobs]
    value['candidates'] = [public_candidate(json.loads(r['data'])) for r in candidates]
    if not internal:
        value.pop('source', None)
    return value


def update_project(pid, **values):
    allowed = {'source', 'metadata', 'options', 'status', 'error', 'name', 'display_name', 'original_filename', 'source_title'}
    if not values or not values.keys() <= allowed:
        raise ValueError('Campos de projeto inválidos.')
    encoded = {k: dumps(v) if k in {'metadata','options'} else v for k,v in values.items()}
    with connection() as db:
        db.execute('UPDATE projects SET '+','.join(k+'=?' for k in encoded)+' WHERE id=?', (*encoded.values(),pid))


def public_job(row):
    value = dict(row)
    value.pop('payload', None)
    value['checkpoint'] = json.loads(value['checkpoint']) if value.get('checkpoint') else {}
    return value


def enqueue(pid, kind, payload, cid=None):
    jid = uid()
    now = time.time()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM jobs WHERE project_id=? AND state IN ('queued','running')",(pid,)).fetchone():
            raise ValueError('Já existe um job ativo neste projeto.')
        db.execute('INSERT INTO jobs(id,project_id,kind,candidate_id,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                   (jid,pid,kind,cid,dumps(payload),now,now))
    return get_job(jid)

def retry_job(jid):
    """Requeue the same failed processing job, retaining its checkpoint and payload."""
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT project_id,kind,state FROM jobs WHERE id=?', (jid,)).fetchone()
        if row is None:
            raise KeyError('Job não encontrado.')
        if row['kind'] != 'process' or row['state'] not in ('failed', 'interrupted'):
            raise ValueError('Somente processamento falho ou interrompido pode ser retomado.')
        if db.execute("SELECT 1 FROM jobs WHERE project_id=? AND state IN ('queued','running')", (row['project_id'],)).fetchone():
            raise ValueError('Já existe um job ativo neste projeto.')
        db.execute("UPDATE jobs SET state='queued',stage='Na fila para retomada',error=NULL,failed_provider=NULL,cancel=0,attempts=attempts+1,updated_at=? WHERE id=?", (time.time(),jid))
    return get_job(jid)


def get_job(jid):
    with connection() as db:
        row = db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
    if row is None:
        raise KeyError('Job não encontrado.')
    return public_job(row)


def claim_job():
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT * FROM jobs WHERE state='queued' AND cancel=0 ORDER BY created_at LIMIT 1").fetchone()
        if row is None:
            return None
        db.execute("UPDATE jobs SET state='running',updated_at=? WHERE id=?", (time.time(),row['id']))
        value = dict(row)
        value['payload'] = json.loads(value['payload'])
        return value


def update_job(jid, **values):
    allowed = {'state','stage','progress','error','cancel','checkpoint','attempts','failed_provider','payload'}
    if not values.keys() <= allowed:
        raise ValueError('Campos de job inválidos.')
    values['updated_at'] = time.time()
    for key in ('checkpoint', 'payload'):
        if key in values and not isinstance(values[key], str):
            values[key] = dumps(values[key])
    with connection() as db:
        db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?', (*values.values(),jid))


def cancel_job(jid):
    with connection() as db:
        row = db.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()
        if row is None:
            raise KeyError('Job não encontrado.')
        if row['state'] == 'queued':
            db.execute("UPDATE jobs SET cancel=1,state='cancelled',stage='Cancelado',updated_at=? WHERE id=?",(time.time(),jid))
        elif row['state'] == 'running':
            db.execute('UPDATE jobs SET cancel=1,updated_at=? WHERE id=?',(time.time(),jid))
    return get_job(jid)


def cancelled(jid):
    with connection() as db:
        row = db.execute('SELECT cancel FROM jobs WHERE id=?',(jid,)).fetchone()
    return not row or bool(row['cancel'])


def public_candidate(candidate):
    value = dict(candidate)
    value['rendered'] = bool(value.pop('render_path', None))
    return value


def get_candidate(pid, cid):
    with connection() as db:
        row = db.execute('SELECT data FROM candidates WHERE id=? AND project_id=?',(cid,pid)).fetchone()
    if row is None:
        raise KeyError('Candidato não encontrado.')
    return json.loads(row['data'])


def save_candidates(pid, candidates):
    with connection() as db:
        db.execute('DELETE FROM candidates WHERE project_id=?',(pid,))
        for n,c in enumerate(candidates,1):
            db.execute('INSERT INTO candidates VALUES(?,?,?,?)',(c['id'],pid,n,dumps(c)))


def update_candidate(pid,cid,value):
    with connection() as db:
        db.execute('UPDATE candidates SET data=? WHERE project_id=? AND id=?',(dumps(value),pid,cid))


def active_project(pid):
    with connection() as db:
        return bool(db.execute("SELECT 1 FROM jobs WHERE project_id=? AND state IN ('running','queued')",(pid,)).fetchone())


def provider_state():
    with connection() as db:
        providers = [json.loads(r['data']) for r in db.execute('SELECT data FROM providers ORDER BY id')]
        row = db.execute("SELECT data FROM settings WHERE key='provider_order'").fetchone()
    order = json.loads(row['data']) if row else {'primary':None,'fallback':None}
    return {'providers':providers, **order}


def selected_providers():
    state = provider_state()
    byid = {p['id']:p for p in state['providers'] if p.get('enabled', True)}
    return {k:byid.get(state[k]) for k in ['primary','fallback']}


def record_usage(pid, value):
    with connection() as db:
        db.execute('INSERT INTO usage(project_id,created_at,data) VALUES(?,?,?)',(pid,time.time(),dumps(value)))


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(dumps(data), encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)
