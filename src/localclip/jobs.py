import hashlib
import json
import multiprocessing
import os
import signal
import time
from pathlib import Path
from . import storage as store

PIPELINE_VERSION = 3


def worker_loop(stop):
    # Own process group lets shutdown terminate FFmpeg descendants as well.
    os.setsid()
    while not stop.is_set():
        job = store.claim_job()
        if job is None:
            stop.wait(.5)
            continue
        pid, jid = job['project_id'], job['id']
        cancelled = lambda: stop.is_set() or store.cancelled(jid)
        def progress(stage, fraction):
            if cancelled():
                raise InterruptedError('Job cancelado.')
            store.update_job(jid, stage=str(stage), progress=max(0., min(1., float(fraction))))
        try:
            execute(job, progress, cancelled)
            if cancelled():
                raise InterruptedError('Job cancelado.')
            store.update_job(jid, state='completed', stage='Concluído', progress=1.)
            store.update_project(pid, status='ready', error=None)
        except BaseException as exc:
            # Provider errors are sanitized in adapters; paths are local, not remotely exposed.
            is_cancel = cancelled() or isinstance(exc, InterruptedError)
            message = 'Job cancelado.' if is_cancel else f'{type(exc).__name__}: {exc}'[:1500]
            update_kw = {
                'state': 'cancelled' if is_cancel else 'failed',
                'stage': 'Cancelado' if is_cancel else 'Falhou',
                'error': message,
            }
            if not is_cancel:
                saved = store.get_job(jid)
                failed_id = (saved or {}).get('checkpoint', {}).get('failed_provider')
                if failed_id:
                    update_kw['failed_provider'] = failed_id
            store.update_job(jid, **update_kw)
            store.update_project(pid, status='ready' if is_cancel else 'failed', error=message)


def execute(job, progress, cancelled):
    from . import media
    pid = job['project_id']
    project = store.get_project(pid, internal=True)
    directory = store.project_dir(pid)
    payload = job['payload']
    jid = job.get('id')
    if job['kind'] == 'ingest':
        source = media.ingest_url(payload['url'], directory/'source', progress, cancelled)
        metadata = media.probe(Path(source))
        source_title = media.extract_source_title(Path(source)) or metadata.get('title') or Path(source).stem
        current = store.get_project(pid, internal=True)
        updates = {'source': str(source), 'metadata': metadata, 'source_title': source_title}
        user_renamed = current.get('display_name') not in (None, '', 'Importação por URL') or current.get('name') not in (None, '', 'Importação por URL')
        if not user_renamed:
            updates['display_name'] = source_title
            updates['name'] = source_title
        store.update_project(pid, **updates)
        media.ensure_preview(Path(source), directory/'preview.mp4', progress, cancelled)
        return
    source = Path(project['source'])
    if not source.is_file():
        raise FileNotFoundError('Arquivo de origem não está disponível.')
    if job['kind'] == 'preview':
        media.ensure_preview(source, directory/'preview.mp4', progress, cancelled)
        return
    if job['kind'] == 'process':
        from .ranking import rank
        options = payload
        store.update_project(pid, status='processing', error=None)

        # Check for stage checkpoint from prior run (resuming after failure/retry)
        raw_checkpoint = job.get('checkpoint')
        if isinstance(raw_checkpoint, str):
            try:
                checkpoint = json.loads(raw_checkpoint) if raw_checkpoint.strip() else {}
            except Exception:
                checkpoint = {}
        elif isinstance(raw_checkpoint, dict):
            checkpoint = dict(raw_checkpoint)
        else:
            checkpoint = {}

        timeline = None
        saved_timeline = None

        # Check if media analysis was already completed and safely persisted
        if checkpoint.get('timeline_path') and Path(checkpoint['timeline_path']).is_file():
            saved_timeline = Path(checkpoint['timeline_path'])

        if saved_timeline is not None:
            try:
                timeline = json.loads(saved_timeline.read_text())
                progress('Retomando da análise de mídia salva', 0.65)
            except Exception:
                timeline = None

        if timeline is None:
            # Fingerprint source incrementally; no video allocation or repeated per-candidate hashing.
            progress('Identificando conteúdo', .01)
            hasher = hashlib.sha256()
            with source.open('rb') as file:
                while chunk := file.read(1024*1024):
                    if cancelled():
                        raise InterruptedError('Job cancelado.')
                    hasher.update(chunk)
            analysis_options = {k:options.get(k) for k in ['start','end','allow_images']}
            analysis_options['whisper_model'] = os.environ.get('LOCALCLIP_WHISPER_MODEL','base')
            key = hashlib.sha256(store.dumps([hasher.hexdigest(),analysis_options,PIPELINE_VERSION]).encode()).hexdigest()
            work = store.cache_root()/'analysis'/key
            work.mkdir(parents=True, exist_ok=True, mode=0o700)
            timeline_path = work/'timeline.json'
            if timeline_path.exists():
                timeline = json.loads(timeline_path.read_text())
                progress('Timeline reaproveitada do cache', .65)
            else:
                timeline = media.analyze(source, work, options, lambda s,p: progress(s,.05+.6*p), cancelled)
                store.atomic_json(timeline_path,timeline)

            # Keep an uncommitted analysis in the content-addressed cache. A failed
            # reanalysis must never replace the project's published timeline.
            checkpoint = {
                'stage': 'media_analysis',
                'timeline_path': str(timeline_path),
                'analysis_key': key,
                'completed_stages': ['identify', 'media_analysis'],
                'updated_at': time.time(),
            }
            if jid:
                store.update_job(jid, checkpoint=checkpoint, stage='Análise de mídia concluída', progress=0.68)

        if cancelled():
            raise InterruptedError('Job cancelado.')

        # Stage: Ranking with dynamically evaluated active provider configuration
        current_providers = store.selected_providers()
        if checkpoint.get('stage') == 'ranking_failed':
            progress('Retomando avaliação com provedores atualizados', 0.70)
        else:
            progress('Avaliando candidatos com IA', 0.70)

        last_failed_provider = None
        def record_ai_usage(event):
            nonlocal last_failed_provider
            if event.get('error'):
                last_failed_provider = event.get('provider_id')
            store.record_usage(pid, event)
            primary = current_providers.get('primary')
            fallback = current_providers.get('fallback')
            if (jid and event.get('error') and primary and fallback
                    and event.get('provider_id') == primary.get('id')):
                notice = f"{primary['id']} falhou. Continuando com {fallback['id']}."
                checkpoint.setdefault('fallback_events', [])
                if notice not in checkpoint['fallback_events']:
                    checkpoint['fallback_events'].append(notice)
                store.update_job(jid, checkpoint=checkpoint, stage=notice)

        try:
            candidates = rank(
                timeline,
                options,
                current_providers,
                record_ai_usage,
                store.cache_root() / 'ai',
            )
        except BaseException as exc:
            # Safely record failed stage and failed provider into checkpoint
            primary_p = current_providers.get('primary')
            failed_p_id = last_failed_provider or (primary_p.get('id') if isinstance(primary_p, dict) else None)
            checkpoint['stage'] = 'ranking_failed'
            checkpoint['failed_provider'] = failed_p_id
            checkpoint['error'] = f'{type(exc).__name__}: {exc}'[:1000]
            checkpoint['updated_at'] = time.time()
            if jid:
                store.update_job(jid, checkpoint=checkpoint, failed_provider=failed_p_id)
            raise

        if cancelled():
            raise InterruptedError('Job cancelado.')

        for candidate in candidates:
            # Stable ranking IDs belong to the semantic cache, not the global DB key.
            candidate['analysis_id'] = candidate['id']
            candidate['id'] = store.uid()
            words = candidate.get('words') or [w for w in timeline.get('words',[]) if w['start']>=candidate['start'] and w['end']<=candidate['end']]
            candidate['words'] = words
            candidate.setdefault('edit', {
                **{k: options[k] for k in ['format', 'subtitle_style', 'subtitle_size', 'subtitle_position'] if k in options},
                'reframe': True,
                'subtitles': True,
                'start': candidate['start'],
                'end': candidate['end'],
                'title': candidate.get('title', 'Corte'),
                'crop_x': None,
                'remove_ranges': [],
                'words': words,
            })
            candidate['revision'] = 1

        store.atomic_json(directory/'timeline.json', timeline)
        store.update_project(pid, options=options)
        store.save_candidates(pid, candidates)

        checkpoint['stage'] = 'completed'
        if checkpoint.pop('failed_provider', None):
            checkpoint['recovered_after_provider_failure'] = True
        checkpoint.pop('error', None)
        checkpoint['completed_stages'] = ['identify', 'media_analysis', 'ranking', 'assembly']
        checkpoint['candidates_count'] = len(candidates)
        checkpoint['updated_at'] = time.time()
        if jid:
            store.update_job(jid, checkpoint=checkpoint)

        progress(f'{len(candidates)} candidatos selecionados', 1.)
    elif job['kind'] == 'render':
        cid = job['candidate_id']
        candidate = store.get_candidate(pid,cid)
        store.update_project(pid,status='rendering',error=None)
        timeline = json.loads((directory/'timeline.json').read_text())
        out = directory/'renders'/f'{cid}-{candidate.get("revision",1)}.mp4'
        out.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        try:
            result = media.render(source,out,candidate,timeline,project['options'],progress,cancelled)
            if cancelled():
                raise InterruptedError('Job cancelado.')
            candidate['render_path'] = str(result)
            store.update_candidate(pid,cid,candidate)
        except BaseException:
            out.unlink(missing_ok=True)
            raise
    else:
        raise ValueError('Tipo de job desconhecido.')


class Worker:
    def __init__(self):
        ctx = multiprocessing.get_context('spawn')
        self.stop = ctx.Event()
        self.process = ctx.Process(target=worker_loop,args=(self.stop,),daemon=False,name='localclip-worker')

    def start(self):
        self.process.start()

    def close(self):
        self.stop.set()
        self.process.join(8)
        if self.process.is_alive():
            try:
                os.killpg(self.process.pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.process.join(3)
        if self.process.is_alive():
            os.killpg(self.process.pid,signal.SIGKILL)
            self.process.join()
