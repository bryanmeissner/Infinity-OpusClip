import pytest
from fastapi.testclient import TestClient
from localclip import storage
from localclip.app import app
from localclip.schemas import Edit, Options

@pytest.fixture
def db(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALCLIP_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setenv('LOCALCLIP_CACHE_DIR',str(tmp_path/'cache'))
    storage.initialize()
    return tmp_path

@pytest.fixture
def client(db):
    # No lifespan: tests cover API state transitions without starting a worker.
    return TestClient(app)

def test_cross_origin_cannot_mutate(client):
    response=client.post('/api/projects/url',headers={'Origin':'https://attacker.example','X-LocalClip':'1'},json={'url':'https://example.com/video.mp4'})
    assert response.status_code==403
    assert storage.list_projects()==[]

def test_simple_cross_site_request_blocked(client):
    response=client.post('/api/projects/url',json={'url':'https://example.com/video.mp4'})
    assert response.status_code==403
    assert storage.list_projects()==[]

def test_dns_rebinding_host_blocked(client):
    response=client.get('/api/bootstrap',headers={'Host':'attacker.example'})
    assert response.status_code==403

def test_queue_excludes_duplicate_work_and_cancel_prevents_claim(db):
    pid=storage.create_project('video')
    first=storage.enqueue(pid,'process',{})
    with pytest.raises(ValueError):
        storage.enqueue(pid,'render',{},'candidate')
    assert storage.cancel_job(first['id'])['state']=='cancelled'
    assert storage.claim_job() is None
    second=storage.enqueue(pid,'process',{})
    assert storage.claim_job()['id']==second['id']

def test_restart_marks_running_interrupted(db):
    pid=storage.create_project('video')
    job=storage.enqueue(pid,'process',{})
    storage.claim_job()
    storage.initialize()
    assert storage.get_job(job['id'])['state']=='interrupted'

def test_edit_invalidates_render_and_blocks_export(client,db):
    pid=storage.create_project('video','/not-used',{'duration':90})
    storage.update_project(pid,options={'start':0,'end':90})
    cid=storage.uid()
    storage.save_candidates(pid,[{'id':cid,'start':0,'end':20,'title':'old','render_path':'old.mp4','revision':1}])
    response=client.patch(f'/api/projects/{pid}/candidates/{cid}',headers={'X-LocalClip':'1'},json={'start':1,'end':25,'title':'new','words':[]})
    assert response.status_code==200
    assert response.json()['rendered'] is False
    assert response.json()['revision']==2
    assert client.get(f'/api/projects/{pid}/candidates/{cid}/export').status_code==409

def test_rendering_project_rejects_edit(client,db):
    pid=storage.create_project('video','unused',{'duration':90})
    cid=storage.uid()
    storage.save_candidates(pid,[{'id':cid,'start':0,'end':20,'title':'old'}])
    storage.enqueue(pid,'render',{},cid)
    response=client.patch(f'/api/projects/{pid}/candidates/{cid}',headers={'X-LocalClip':'1'},json={'start':1,'end':25,'title':'new'})
    assert response.status_code==409
    assert storage.get_candidate(pid,cid)['title']=='old'

@pytest.mark.parametrize('ranges',[[{'start':2,'end':8},{'start':7,'end':9}],[{'start':0,'end':20}],[{'start':19,'end':21}]])
def test_reject_invalid_removal_intervals(ranges):
    with pytest.raises(ValueError):
        Edit(start=0,end=20,title='t',remove_ranges=ranges)

def test_word_outside_clip_rejected():
    with pytest.raises(ValueError):
        Edit(start=10,end=20,title='t',words=[{'start':9,'end':11,'word':'fala'}])

def test_options_nonfinite_time_rejected():
    with pytest.raises(ValueError):
        Options(start=float('nan'))


def test_delete_project_preserves_external_original(client, db):
    original = db / 'original.mp4'
    original.write_bytes(b'original')
    pid = storage.create_project('video', original, {'duration': 10})
    directory = storage.project_dir(pid)
    (directory / 'preview.mp4').write_bytes(b'owned copy')
    response = client.delete(f'/api/projects/{pid}', headers={'X-LocalClip': '1'})
    assert response.status_code == 200
    assert original.read_bytes() == b'original'
    assert not directory.exists()
    assert client.get(f'/api/projects/{pid}').status_code == 404


def test_delete_project_rejects_active_job(client, db):
    pid = storage.create_project('video')
    job = storage.enqueue(pid, 'process', {})
    response = client.delete(f'/api/projects/{pid}', headers={'X-LocalClip': '1'})
    assert response.status_code == 409
    assert storage.get_job(job['id'])['state'] == 'queued'
    assert storage.get_project(pid)['id'] == pid


def test_failed_reanalysis_preserves_previous_timeline_and_options(db, monkeypatch):
    import json
    from localclip import jobs, media, ranking

    source = db / 'source.media'
    source.write_bytes(b'analysis fixture')
    pid = storage.create_project('video', source, {'duration': 20})
    previous_options = {'start': 0, 'end': 10}
    previous_timeline = {'start': 0, 'end': 10}
    storage.update_project(pid, options=previous_options)
    timeline_path = storage.project_dir(pid) / 'timeline.json'
    storage.atomic_json(timeline_path, previous_timeline)
    storage.save_candidates(pid, [{'id': 'existing', 'start': 0, 'end': 10}])
    monkeypatch.setattr(media, 'analyze', lambda *args: {'start': 10, 'end': 20})

    def fail_ranking(*args):
        raise RuntimeError('provider failed')

    monkeypatch.setattr(ranking, 'rank', fail_ranking)
    with pytest.raises(RuntimeError):
        jobs.execute({'project_id': pid, 'kind': 'process', 'payload': {'start': 10, 'end': 20}},
                     lambda *args: None, lambda: False)
    assert storage.get_project(pid)['options'] == previous_options
    assert json.loads(timeline_path.read_text()) == previous_timeline
    assert storage.get_candidate(pid, 'existing')['end'] == 10


@pytest.mark.parametrize('start,end,status', [
    (0, 5.055, 200),
    (0, None, 200),
    (1.125, 4.95, 200),
    (0, 5.056, 400),
    (5.055, None, 400),
    (2, 2, 422),
    (-0.1, 4, 422),
])
def test_process_interval_respects_exact_source_duration(client, start, end, status):
    pid = storage.create_project('fractional video', '/not-used', {'duration': 5.055})
    response = client.post(f'/api/projects/{pid}/process',
                           headers={'X-LocalClip': '1'}, json={'start': start, 'end': end})
    assert response.status_code == status
    project = storage.get_project(pid)
    if status == 200:
        job = storage.claim_job()
        assert job['id'] == response.json()['id']
        assert job['payload']['start'] == start
        assert job['payload']['end'] == (5.055 if end is None else end)
    else:
        assert project['jobs'] == []

def test_omp_login_endpoint_rejects_unlisted_provider(client):
    response = client.post('/api/omp/login', headers={'X-LocalClip': '1'}, json={'provider': 'anthropic; rm -rf ~'})
    assert response.status_code == 400

def test_provider_test_uses_unsaved_form_config(client, monkeypatch):
    """Testing must exercise the values on screen, not only what was saved earlier."""
    from localclip import providers
    seen = {}
    monkeypatch.setattr(providers, 'health_check', lambda cfg: seen.update(cfg) or {'ok': True, 'message': 'ok'})
    response = client.post('/api/providers/glm/test', headers={'X-LocalClip': '1'},
                           json={'kind': 'glm', 'model': 'glm-4.5-flash', 'base_url': ''})
    assert response.status_code == 200
    assert seen['id'] == 'glm' and seen['model'] == 'glm-4.5-flash'

def test_provider_test_rejects_plain_http_remote_endpoint(client):
    response = client.post('/api/providers/openai/test', headers={'X-LocalClip': '1'},
                           json={'kind': 'openai', 'model': 'gpt-6-luna', 'base_url': 'http://evil.example/v1'})
    assert response.status_code == 400

@pytest.mark.parametrize('endpoint', [
    'http://remote.example/v1',
    'https://user:password@remote.example/v1',
    'https://remote.example/v1?api_key=not-a-real-key',
    'https://remote.example/v1#fragment',
])
def test_model_discovery_rejects_unsafe_endpoints_before_sending_credentials(client, monkeypatch, endpoint):
    from localclip import providers

    def unexpected_request(config):
        pytest.fail('Unsafe endpoint reached model discovery')

    monkeypatch.setattr(providers, 'list_provider_models', unexpected_request)
    response = client.post('/api/providers/compatible/models',
                           headers={'X-LocalClip': '1'},
                           json={'kind': 'compatible', 'model': 'local',
                                 'base_url': endpoint, 'api_key': 'not-a-real-key'})
    assert response.status_code == 400


def test_multiple_durations_are_exclusive_of_auto_and_legacy_flags_normalize(client):
    pid = storage.create_project('video', '/not-used', {'duration': 120})
    response = client.post(f'/api/projects/{pid}/process', headers={'X-LocalClip': '1'},
                           json={'durations': ['<30s', '60s–89s'], 'results': 2,
                                 'reframe': False, 'subtitles': False})
    assert response.status_code == 200
    payload = storage.claim_job()['payload']
    assert payload['durations'] == ['<30s', '60s–89s']
    assert payload['reframe'] is True and payload['subtitles'] is True
    assert payload['results'] is None
    with pytest.raises(ValueError):
        Options.model_validate({'durations': ['Auto', '30s–59s']})


def test_rename_updates_list_and_detail_without_touching_source(client):
    pid = storage.create_project('original', '/not-used', {'duration': 12})
    response = client.patch(f'/api/projects/{pid}', headers={'X-LocalClip': '1'},
                            json={'display_name': '  Melhores momentos  '})
    assert response.status_code == 200
    assert response.json()['display_name'] == 'Melhores momentos'
    assert client.get('/api/projects').json()[0]['display_name'] == 'Melhores momentos'
    assert storage.get_project(pid, internal=True)['source'] == '/not-used'


def test_retry_preserves_completed_checkpoint_and_rejects_active_job(client):
    pid = storage.create_project('video')
    jid = storage.enqueue(pid, 'process', {})['id']
    assert client.post(f'/api/jobs/{jid}/retry', headers={'X-LocalClip': '1'}).status_code == 400
    storage.claim_job()
    checkpoint = {'completed': ['timeline'], 'artifact': 'analysis/a.json'}
    storage.update_job(jid, state='failed', checkpoint=checkpoint, error='provider unavailable')
    response = client.post(f'/api/jobs/{jid}/retry', headers={'X-LocalClip': '1'})
    assert response.status_code == 200
    assert response.json()['checkpoint'] == checkpoint
    assert response.json()['attempts'] == 1
    assert storage.claim_job()['id'] == jid
