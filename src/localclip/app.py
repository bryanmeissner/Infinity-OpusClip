import fcntl
import json
import os
import re
import platform
import subprocess
import shutil
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import storage as store
from .jobs import Worker
from .schemas import CLIP_MODELS, DURATIONS, GENRES, PLATFORMS, Edit, OmpLogin, Options, ProjectRename, Provider, ProviderOrder, URLInput

MUTATION_LOCK = threading.RLock()


@asynccontextmanager
async def lifespan(app):
    os.umask(0o077)
    lock = (store.data_root()/'instance.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Já existe uma instância usando este diretório de dados.')
    try:
        store.initialize()
        worker = Worker()
        worker.start()
        app.state.worker = worker
        try:
            yield
        finally:
            from .providers import stop_omp_login
            stop_omp_login()
            worker.close()
    finally:
        lock.close()


app = FastAPI(title='LocalClip', lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware('http')
async def local_boundary(request: Request, call_next):
    host = request.url.hostname
    if host not in {'127.0.0.1', 'localhost', '::1', 'testserver'}:
        return JSONResponse({'detail':'Host não permitido.'},status_code=403)
    origin = request.headers.get('origin')
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {'http','https'} or parsed.netloc != request.headers.get('host'):
            return JSONResponse({'detail':'Origem não permitida.'},status_code=403)
    if request.method not in {'GET','HEAD','OPTIONS'} and request.headers.get('x-localclip') != '1':
        return JSONResponse({'detail':'Cabeçalho local obrigatório.'},status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@app.exception_handler(KeyError)
async def missing(request, exc):
    return JSONResponse({'detail':str(exc.args[0])},status_code=404)


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'detail':str(exc)},status_code=400)


def idle(pid):
    store.get_project(pid)
    if store.active_project(pid):
        raise HTTPException(409,'Aguarde ou cancele o job ativo antes de editar.')


def provider_public(config):
    from .providers import has_key
    result = dict(config)
    try:
        result['has_key'] = has_key(config['id'])
        result['credential_error'] = None
    except Exception:
        result['has_key'] = False
        result['credential_error'] = 'Secret Service indisponível ou bloqueado.'
    return result


@lru_cache(maxsize=1)
def hardware_info():
    """Report detected hardware without claiming an encoder is usable."""
    gpu = []
    if shutil.which('lspci'):
        try:
            result = subprocess.run(['lspci'], capture_output=True, text=True, timeout=5, check=True)
            gpu = [line.partition(': ')[2] for line in result.stdout.splitlines()
                   if any(kind in line for kind in ('VGA compatible controller', '3D controller', 'Display controller'))]
        except (OSError, subprocess.SubprocessError):
            pass
    return {
        'cpu': platform.processor() or platform.machine(),
        'cpu_threads': os.cpu_count(),
        'memory_bytes': os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES'),
        'gpu': '; '.join(gpu) or 'Não identificada',
    }


@app.get('/api/bootstrap')
def bootstrap():
    state = store.provider_state()
    return {'options':{'genres':GENRES,'durations':DURATIONS,'clip_models':CLIP_MODELS,'platforms':PLATFORMS},
            'projects':store.list_projects(),'providers':[provider_public(p) for p in state['providers']],
            'provider_order':{k:state[k] for k in ['primary','fallback']},
            'capabilities':{'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe')),
                'cpu_fallback':True, **hardware_info(),
                'free_disk_bytes':shutil.disk_usage(store.data_root()).free,'local_first':True}}


@app.get('/api/projects')
def projects():
    return store.list_projects()


@app.post('/api/projects')
async def import_file(file: UploadFile = File(...)):
    from .media import probe
    original_filename = Path(file.filename or 'video').name
    name = Path(original_filename).stem or original_filename
    pid = store.create_project(name)
    # Never use uploaded names as filesystem paths or trust extension as media type.
    source = store.project_dir(pid)/'source.media'
    try:
        size = 0
        with source.open('wb') as out:
            while chunk := await file.read(1024*1024):
                if shutil.disk_usage(source.parent).free < len(chunk)+512*1024*1024:
                    raise HTTPException(507,'Espaço insuficiente; mantenha pelo menos 512 MiB livres.')
                await run_in_threadpool(out.write,chunk)
                size += len(chunk)
        if size == 0:
            raise ValueError('Arquivo vazio.')
        metadata = await run_in_threadpool(probe,source)
        store.update_project(pid,source=str(source),metadata=metadata,original_filename=original_filename,
                             source_title=metadata.get('title'),status='ready')
        store.enqueue(pid,'preview',{})
    except Exception as exc:
        source.unlink(missing_ok=True)
        store.update_project(pid,status='failed',error='Falha ao importar vídeo.')
        if isinstance(exc,HTTPException):
            raise
        raise HTTPException(400,f'Não foi possível importar: {str(exc)[:400]}') from exc
    finally:
        await file.close()
    return store.get_project(pid)


@app.post('/api/projects/url')
def import_url(body: URLInput):
    if urlsplit(body.url).scheme not in {'http','https'}:
        raise ValueError('Use uma URL HTTP/HTTPS pública.')
    pid = store.create_project('Importação por URL')
    store.enqueue(pid,'ingest',body.model_dump())
    return store.get_project(pid)


@app.get('/api/projects/{pid}')
def project(pid: str):
    return store.get_project(pid)

@app.patch('/api/projects/{pid}')
def rename_project(pid: str, body: ProjectRename):
    with MUTATION_LOCK:
        store.get_project(pid)
        store.update_project(pid, display_name=body.display_name)
        return store.get_project(pid)


@app.delete('/api/projects/{pid}')
def delete_project(pid: str):
    with MUTATION_LOCK:
        idle(pid)
        directory = store.project_dir(pid)
        # Only app-owned copies are removed; never follow the source path.
        with store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM usage WHERE project_id=?', (pid,))
            db.execute('DELETE FROM candidates WHERE project_id=?', (pid,))
            db.execute('DELETE FROM jobs WHERE project_id=?', (pid,))
            db.execute('DELETE FROM projects WHERE id=?', (pid,))
        shutil.rmtree(directory)
        return {'deleted': True}


@app.post('/api/projects/{pid}/process')
def process(pid: str, options: Options):
    with MUTATION_LOCK:
        current = store.get_project(pid,internal=True)
        if not current.get('source'):
            raise ValueError('Importe um vídeo antes de processar.')
        duration = current['metadata']['duration']
        data = options.model_dump()
        if data['end'] is None:
            data['end'] = duration
        if data['start'] >= duration or data['end'] > duration:
            raise ValueError('Intervalo fora do vídeo.')
        return store.enqueue(pid,'process',data)

@app.post('/api/jobs/{jid}/retry')
def retry(jid: str):
    with MUTATION_LOCK:
        return store.retry_job(jid)


@app.post('/api/jobs/{jid}/cancel')
def cancel(jid: str):
    return store.cancel_job(jid)


@app.get('/api/jobs/{jid}')
def job(jid: str):
    return store.get_job(jid)


def source_path(pid):
    project = store.get_project(pid,internal=True)
    path = Path(project['source']) if project.get('source') else None
    if path is None or not path.is_file():
        raise HTTPException(404,'Vídeo não disponível.')
    return path


@app.get('/api/projects/{pid}/source')
def source(pid: str):
    source_path(pid)
    preview = store.project_dir(pid)/'preview.mp4'
    if not preview.is_file():
        raise HTTPException(409,'Prévia sendo preparada; aguarde a importação.')
    return FileResponse(preview,media_type='video/mp4')

@app.get('/api/projects/{pid}/thumbnail')
def thumbnail(pid: str):
    project = store.get_project(pid, internal=True)
    thumb = store.project_dir(pid)/'thumbnail.jpg'
    if not thumb.is_file():
        source = project.get('source')
        if source and not Path(source).is_file():
            raise HTTPException(410, 'Arquivo de origem removido.')
        from .media import ensure_project_thumbnail
        if source:
            try:
                ensure_project_thumbnail(Path(source), thumb)
            except Exception:
                pass
    if not thumb.is_file():
        raise HTTPException(404, 'Thumbnail indisponível.')
    return FileResponse(thumb, media_type='image/jpeg')


@app.get('/api/projects/{pid}/timeline')
def timeline(pid: str):
    store.get_project(pid)
    path = store.project_dir(pid)/'timeline.json'
    if not path.exists():
        raise HTTPException(404,'Timeline ainda não disponível.')
    return json.loads(path.read_text())


@app.patch('/api/projects/{pid}/candidates/{cid}')
def edit_candidate(pid: str,cid: str, edit: Edit):
    with MUTATION_LOCK:
        idle(pid)
        current = store.get_project(pid)
        if edit.end > current['metadata']['duration']+.01:
            raise ValueError('Fim fora do vídeo.')
        # Analysis evidence is valid only inside the interval the user requested.
        if edit.start < current['options'].get('start',0) or edit.end > current['options'].get('end',current['metadata']['duration'])+.01:
            raise ValueError('Edição deve permanecer no intervalo analisado.')
        value = store.get_candidate(pid,cid)
        value['edit'] = edit.model_dump()
        value['title'] = edit.title
        value['revision'] = value.get('revision',1)+1
        value.pop('render_path',None)
        store.update_candidate(pid,cid,value)
        return store.public_candidate(value)


@app.post('/api/projects/{pid}/candidates/{cid}/render')
def render_candidate(pid: str,cid: str):
    with MUTATION_LOCK:
        store.get_candidate(pid,cid)
        return store.enqueue(pid,'render',{},cid)


def rendered(pid,cid):
    candidate = store.get_candidate(pid,cid)
    file = candidate.get('render_path')
    if not file or not Path(file).is_file():
        raise HTTPException(409,'Renderize esta revisão antes de assistir/exportar.')
    path = Path(file).resolve()
    if not path.is_relative_to(store.project_dir(pid).resolve()):
        raise HTTPException(403,'Arquivo fora do projeto.')
    return path,candidate


@app.get('/api/projects/{pid}/candidates/{cid}/video')
def candidate_video(pid: str,cid: str):
    path,_ = rendered(pid,cid)
    return FileResponse(path,media_type='video/mp4')


@app.get('/api/projects/{pid}/candidates/{cid}/export')
def export_candidate(pid: str,cid: str):
    path,candidate = rendered(pid,cid)
    title = re.sub(r'[^\w .-]','',candidate.get('title','corte'))[:90].strip() or 'corte'
    return FileResponse(path,media_type='video/mp4',filename=f'{title}-{cid[:8]}.mp4')


@app.delete('/api/projects/{pid}/candidates/{cid}')
def delete_candidate(pid: str,cid: str):
    with MUTATION_LOCK:
        idle(pid)
        store.get_candidate(pid,cid)
        with store.connection() as db:
            db.execute('DELETE FROM candidates WHERE project_id=? AND id=?',(pid,cid))
        directory = store.project_dir(pid)/'renders'
        # cid was found in the DB; delete only application-generated revisions.
        for path in directory.glob(f'{cid}-*.mp4'):
            path.unlink(missing_ok=True)
        return {'deleted':True}


@app.get('/api/projects/{pid}/usage')
def usage(pid: str):
    store.get_project(pid)
    with store.connection() as db:
        return [{**json.loads(r['data']),'created_at':r['created_at']} for r in db.execute('SELECT data,created_at FROM usage WHERE project_id=? ORDER BY id',(pid,))]


@app.get('/api/providers')
def providers():
    state = store.provider_state()
    state['providers'] = [provider_public(p) for p in state['providers']]
    return state


def provider_id(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',value):
        raise ValueError('Identificador de provider inválido.')


def validate_endpoint(base_url):
    # Custom endpoints may receive credentials. Require explicit HTTPS except loopback local APIs.
    if base_url:
        parsed = urlsplit(base_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Endpoint não deve conter credenciais, query ou fragmento.')
        if parsed.scheme != 'https' and not (parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1','::1'}):
            raise ValueError('Endpoint deve usar HTTPS; HTTP permitido somente para modelos locais.')


@app.put('/api/providers/{provider}')
def save_provider(provider: str, body: Provider):
    from .providers import save_key
    provider_id(provider)
    value = body.model_dump(exclude={'api_key'})
    value['id'] = provider
    validate_endpoint(value['base_url'])
    with MUTATION_LOCK:
        if body.api_key:
            save_key(provider,body.api_key)
        with store.connection() as db:
            db.execute('INSERT INTO providers(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(provider,store.dumps(value)))
    return provider_public(value)


@app.delete('/api/providers/{provider}')
def delete_provider(provider: str):
    from .providers import delete_key
    provider_id(provider)
    with MUTATION_LOCK:
        delete_key(provider)
        with store.connection() as db:
            db.execute('DELETE FROM providers WHERE id=?',(provider,))
            row = db.execute("SELECT data FROM settings WHERE key='provider_order'").fetchone()
            if row:
                order = json.loads(row['data'])
                order = {k:None if v==provider else v for k,v in order.items()}
                db.execute("UPDATE settings SET data=? WHERE key='provider_order'",(store.dumps(order),))
    return {'deleted':True}


@app.post('/api/providers/{provider}/test')
def test_provider(provider: str, body: Provider | None = None):
    """Tests the form's unsaved config when sent, else the saved one; a blank key falls back to the keyring."""
    from .providers import health_check
    provider_id(provider)
    if body is not None:
        value = body.model_dump()
        value['id'] = provider
        validate_endpoint(value['base_url'])
    else:
        state = store.provider_state()
        value = next((p for p in state['providers'] if p['id']==provider),None)
        if value is None:
            raise KeyError('Provider não encontrado.')
    try:
        return health_check(value)
    except Exception as exc:
        raise HTTPException(400,str(exc)[:500]) from exc


DEFAULT_PRESET_CONFIGS = {
    'openai': {'id': 'openai', 'kind': 'openai', 'model': 'gpt-6-luna', 'base_url': 'https://api.openai.com/v1', 'enabled': True},
    'gemini': {'id': 'gemini', 'kind': 'gemini', 'model': 'gemini-3.8-flash', 'base_url': '', 'enabled': True},
    'anthropic': {'id': 'anthropic', 'kind': 'anthropic', 'model': 'claude-sonnet-5-5', 'base_url': 'https://api.anthropic.com/v1', 'enabled': True},
    'glm': {'id': 'glm', 'kind': 'glm', 'model': 'glm-4.7', 'base_url': 'https://api.z.ai/api/paas/v4', 'enabled': True},
    'compatible': {'id': 'compatible', 'kind': 'compatible', 'model': 'llama3.2', 'base_url': 'http://localhost:11434/v1', 'enabled': True},
    'omp': {'id': 'omp', 'kind': 'omp', 'model': 'google-antigravity/gemini-3.8-flash', 'base_url': '', 'enabled': True},
    'openrouter': {'id': 'openrouter', 'kind': 'openrouter', 'model': 'openai/gpt-4o-mini', 'base_url': '', 'enabled': True},
}


@app.get('/api/providers/catalog')
def provider_catalog():
    from .providers import get_curated_catalog
    return get_curated_catalog()


@app.get('/api/providers/{provider}/models')
def provider_models(provider: str):
    from .providers import list_provider_models
    provider_id(provider)
    state = store.provider_state()
    config = next((p for p in state['providers'] if p['id'] == provider), None)
    if config is None:
        if provider in DEFAULT_PRESET_CONFIGS:
            config = dict(DEFAULT_PRESET_CONFIGS[provider])
        else:
            raise HTTPException(404, 'Provider não encontrado.')
    return list_provider_models(config)


@app.post('/api/providers/{provider}/models')
def provider_models_custom(provider: str, body: Provider):
    from .providers import list_provider_models
    provider_id(provider)
    config = body.model_dump()
    config['id'] = provider
    validate_endpoint(config['base_url'])
    return list_provider_models(config)


@app.get('/api/omp/status')
def omp_status():
    from .providers import omp_login_status
    return omp_login_status()


@app.post('/api/omp/login')
def omp_login(body: OmpLogin):
    # Loopback-only API (see local_boundary); the provider id is checked against a fixed allow-list.
    from .providers import ProviderError, start_omp_login
    try:
        return start_omp_login(body.provider, body.google_cloud_project)
    except ProviderError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.put('/api/provider-order')
def provider_order(body: ProviderOrder):
    state = store.provider_state()
    ids = {p['id'] for p in state['providers'] if p.get('enabled',True)}
    value = body.model_dump()
    if any(v is not None and v not in ids for v in value.values()):
        raise ValueError('Selecione providers existentes e habilitados.')
    if body.fallback and (not body.primary or body.primary==body.fallback):
        raise ValueError('Fallback precisa ser distinto do principal.')
    with store.connection() as db:
        db.execute("INSERT INTO settings(key,data) VALUES('provider_order',?) ON CONFLICT(key) DO UPDATE SET data=excluded.data",(store.dumps(value),))
    return value


# Routes above always take precedence over the frontend mount.
DIST = Path(__file__).resolve().parents[2]/'web'/'dist'
if DIST.is_dir():
    app.mount('/',StaticFiles(directory=DIST,html=True),name='frontend')
else:
    @app.get('/')
    def unbuilt():
        return JSONResponse({'detail':'Frontend não compilado. Execute npm --prefix web install && npm --prefix web run build.'},status_code=503)


def main():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description='Editor de vídeo local-first')
    parser.add_argument('--port',type=int,default=8765)
    args = parser.parse_args()
    uvicorn.run('localclip.app:app',host='127.0.0.1',port=args.port)


if __name__ == '__main__':
    main()
