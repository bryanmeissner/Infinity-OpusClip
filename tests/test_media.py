import shutil
import subprocess

import pytest

from localclip import media


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_vfr_removal_preserves_elapsed_time(tmp_path, monkeypatch):
    source = tmp_path / 'vfr.mp4'
    output = tmp_path / 'cut.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc2=size=160x120:rate=20:duration=4', '-vf',
        "setpts='if(lt(N,40),N/(10*TB),(4+(N-40)/20)/TB)'",
        '-fps_mode', 'vfr', '-c:v', 'libx264', str(source),
    ], check=True, capture_output=True)
    monkeypatch.setattr(media, 'is_vaapi_supported', lambda: False)
    media.render(source, output, {
        'start': 0, 'end': 4,
        'edit': {'format': '9:16', 'subtitles': False,
                 'remove_ranges': [{'start': 1, 'end': 2}]},
    }, {'tracks': []}, {})
    # Frame-count / average-FPS retiming shortened this to 2.45 seconds.
    assert media.probe(output)['duration'] == pytest.approx(3.0, abs=0.1)


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_reframe_moving_person_tracking_and_zoom(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'is_vaapi_supported', lambda: False)
    source = tmp_path / 'source_16_9.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc=size=640x360:rate=25:duration=2',
        '-c:v', 'libx264', str(source),
    ], check=True, capture_output=True)

    # Synthetic tracks simulating a person moving left to right and stepping closer
    moving_tracks = [
        {'time': 0.0, 'boxes': [{'x': 0.20, 'y': 0.20, 'w': 0.12, 'h': 0.12}]},
        {'time': 0.5, 'boxes': [{'x': 0.35, 'y': 0.22, 'w': 0.15, 'h': 0.15}]},
        {'time': 1.0, 'boxes': [{'x': 0.50, 'y': 0.25, 'w': 0.18, 'h': 0.18}]},
        {'time': 1.5, 'boxes': [{'x': 0.65, 'y': 0.23, 'w': 0.22, 'h': 0.22}]},
        {'time': 2.0, 'boxes': [{'x': 0.75, 'y': 0.20, 'w': 0.24, 'h': 0.24}]},
    ]

    for fmt, (exp_w, exp_h) in [('9:16', (1080, 1920)), ('1:1', (1080, 1080)), ('16:9', (1920, 1080))]:
        out_file = tmp_path / f'out_{fmt.replace(":", "_")}.mp4'
        media.render(source, out_file, {
            'start': 0, 'end': 2,
            'edit': {'format': fmt, 'reframe': True, 'subtitles': False},
        }, {'tracks': moving_tracks}, {})

        meta = media.probe(out_file)
        assert meta['width'] == exp_w
        assert meta['height'] == exp_h
        assert meta['duration'] == pytest.approx(2.0, abs=0.15)

    # Validate trajectory invariants directly
    traj = media.visual.compute_reframe_trajectory(moving_tracks, 0.0, 2.0)
    assert traj['has_faces'] is True
    assert traj['is_dynamic'] is True
    assert traj['has_zoom'] is True
    assert 1.0 <= traj['min_zoom'] < traj['max_zoom'] <= 1.25
    assert len(traj['keypoints']) >= 2
    assert traj['keypoints'][0]['t'] == 0.0
    assert traj['keypoints'][-1]['t'] == 2.0


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_reframe_crop_follows_subject_while_zoom_changes(tmp_path):
    """Crop position must track the per-frame scaled size, not the first frame's size."""
    import numpy as np

    source = tmp_path / 'gradient.mp4'
    # Luma encodes the normalized source column, so the output centre reveals where the crop landed.
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        "nullsrc=s=640x360:d=4:r=10,geq=lum='16+X*219/W':cb=128:cr=128",
        '-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-qp', '0', str(source),
    ], check=True, capture_output=True)
    # Close-up face (no zoom) that steps back (zoom to max) while its centre stays at x=0.6.
    tracks = [{'time': t / 2, 'boxes': [{'x': 0.6 - s / 2, 'y': 0.35, 'w': s, 'h': s}]}
              for t, s in enumerate([0.3, 0.3, 0.3, 0.2, 0.12, 0.08, 0.08, 0.08, 0.08])]
    flt, _, info = media.visual.build_reframe_filter(
        640, 360, '9:16', reframe=True, tracks=tracks, start_time=0.0, end_time=4.0, zoom_level=2.0,
    )
    traj = info['trajectory']
    assert traj['has_zoom'] is True and traj['max_zoom'] > 1.8

    w, h = 90, 160
    raw = subprocess.run([
        'ffmpeg', '-v', 'error', '-i', str(source), '-vf', f'{flt},scale={w}:{h}',
        '-pix_fmt', 'yuv420p', '-f', 'rawvideo', '-',
    ], check=True, capture_output=True).stdout
    frame_size = w * h * 3 // 2
    frames = [np.frombuffer(raw[i:i + w * h], np.uint8).reshape(h, w) for i in range(0, len(raw), frame_size)]
    for index in (0, len(frames) - 1):
        centre = float(frames[index][h // 2, w // 2 - 1:w // 2 + 1].mean())
        # A crop frozen at the first frame's width lands near x=0.3 once zoom reaches 2x.
        assert (centre - 16) / 219 == pytest.approx(0.6, abs=0.03)

@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_reframe_no_faces_graceful_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'is_vaapi_supported', lambda: False)
    source = tmp_path / 'source_no_faces.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc=size=640x360:rate=25:duration=2',
        '-c:v', 'libx264', str(source),
    ], check=True, capture_output=True)

    empty_tracks = [{'time': 0.0, 'boxes': []}, {'time': 1.0, 'boxes': []}]
    out_file = tmp_path / 'out_fallback.mp4'
    media.render(source, out_file, {
        'start': 0, 'end': 2,
        'edit': {'format': '9:16', 'reframe': True, 'subtitles': False},
    }, {'tracks': empty_tracks}, {})

    meta = media.probe(out_file)
    assert meta['width'] == 1080
    assert meta['height'] == 1920
    assert meta['duration'] == pytest.approx(2.0, abs=0.15)

    traj = media.visual.compute_reframe_trajectory(empty_tracks, 0.0, 2.0)
    assert traj['has_faces'] is False
    assert traj['is_dynamic'] is False
    assert traj['has_zoom'] is False
    assert traj['min_zoom'] == 1.0
    assert traj['max_zoom'] == 1.0


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_reframe_manual_crop_and_disabled_pixel_behavior(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'is_vaapi_supported', lambda: False)
    source = tmp_path / 'source_pattern.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc=size=640x360:rate=25:duration=1',
        '-c:v', 'libx264', str(source),
    ], check=True, capture_output=True)

    out_left = tmp_path / 'out_left.mp4'
    out_right = tmp_path / 'out_right.mp4'
    out_disabled = tmp_path / 'out_disabled.mp4'

    tracks = [{'time': 0.0, 'boxes': [{'x': 0.8, 'y': 0.2, 'w': 0.1, 'h': 0.1}]}]
    media.render(source, out_left, {'start': 0, 'end': 1, 'edit': {'format': '9:16', 'crop_x': 0.15, 'reframe': True, 'subtitles': False}}, {'tracks': tracks}, {})
    media.render(source, out_right, {'start': 0, 'end': 1, 'edit': {'format': '9:16', 'crop_x': 0.85, 'reframe': True, 'subtitles': False}}, {'tracks': tracks}, {})
    media.render(source, out_disabled, {'start': 0, 'end': 1, 'edit': {'format': '9:16', 'reframe': False, 'subtitles': False}}, {'tracks': tracks}, {})

    thumb_left = media.visual.extract_thumbnail(out_left, 0.5)
    thumb_right = media.visual.extract_thumbnail(out_right, 0.5)
    thumb_dis = media.visual.extract_thumbnail(out_disabled, 0.5)

    # Pixel verification: manual crop at different positions must yield distinct frame pixels
    assert thumb_left != thumb_right
    assert thumb_left != thumb_dis

    # Metadata verification: manual crop and disabled reframe omit dynamic trajectory
    _, _, info_man = media.visual.build_reframe_filter(1920, 1080, '9:16', reframe=True, tracks=tracks, manual_crop_x=0.30)
    assert info_man['crop_center_x'] == 0.30
    assert 'trajectory' not in info_man

    _, _, info_dis = media.visual.build_reframe_filter(1920, 1080, '9:16', reframe=False, tracks=tracks)
    assert 'trajectory' not in info_dis


def test_reframe_cuts_exclude_samples_invariant():
    tracks_with_cut_extreme = [
        {'time': 10.0, 'boxes': [{'x': 0.2, 'y': 0.2, 'w': 0.15, 'h': 0.15}]},
        {'time': 11.0, 'boxes': [{'x': 0.3, 'y': 0.2, 'w': 0.15, 'h': 0.15}]},
        {'time': 13.0, 'boxes': [{'x': 0.9, 'y': 0.9, 'w': 0.15, 'h': 0.15}]},  # Inside cut interval [12..14]
        {'time': 15.0, 'boxes': [{'x': 0.6, 'y': 0.2, 'w': 0.15, 'h': 0.15}]},
        {'time': 17.0, 'boxes': [{'x': 0.7, 'y': 0.2, 'w': 0.15, 'h': 0.15}]},
    ]
    tracks_without_cut_sample = [
        {'time': 10.0, 'boxes': [{'x': 0.2, 'y': 0.2, 'w': 0.15, 'h': 0.15}]},
        {'time': 11.0, 'boxes': [{'x': 0.3, 'y': 0.2, 'w': 0.15, 'h': 0.15}]},
        {'time': 15.0, 'boxes': [{'x': 0.6, 'y': 0.2, 'w': 0.15, 'h': 0.15}]},
        {'time': 17.0, 'boxes': [{'x': 0.7, 'y': 0.2, 'w': 0.15, 'h': 0.15}]},
    ]
    kept = [(10.0, 12.0), (14.0, 18.0)]
    traj_with = media.visual.compute_reframe_trajectory(tracks_with_cut_extreme, 10.0, 18.0, kept)
    traj_without = media.visual.compute_reframe_trajectory(tracks_without_cut_sample, 10.0, 18.0, kept)

    # Cut exclusion invariant: outlier sample inside cut range must be completely excluded
    assert traj_with['duration'] == 6.0
    assert traj_with['keypoints'] == traj_without['keypoints']
    assert traj_with['avg_x'] == traj_without['avg_x']
    assert traj_with['avg_zoom'] == traj_without['avg_zoom']

@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_reframe_portrait_source_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'is_vaapi_supported', lambda: False)
    source = tmp_path / 'source_portrait.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc=size=720x1280:rate=25:duration=2',
        '-c:v', 'libx264', str(source),
    ], check=True, capture_output=True)

    tracks = [
        {'time': 0.0, 'boxes': [{'x': 0.4, 'y': 0.3, 'w': 0.2, 'h': 0.2}]},
        {'time': 1.0, 'boxes': [{'x': 0.5, 'y': 0.4, 'w': 0.2, 'h': 0.2}]},
    ]
    for fmt, (exp_w, exp_h) in [('16:9', (1920, 1080)), ('1:1', (1080, 1080)), ('9:16', (1080, 1920))]:
        out_file = tmp_path / f'out_port_{fmt.replace(":", "_")}.mp4'
        media.render(source, out_file, {
            'start': 0, 'end': 2,
            'edit': {'format': fmt, 'reframe': True, 'subtitles': False},
        }, {'tracks': tracks}, {})
        meta = media.probe(out_file)
        assert meta['width'] == exp_w
        assert meta['height'] == exp_h
        assert meta['duration'] == pytest.approx(2.0, abs=0.15)


def test_reframe_multiple_people_group_framing_and_safe_zoom():
    """When multiple people fit in the frame, track group center with safe zoom without cutting faces."""
    tracks_close = [
        {"time": 0.0, "boxes": [{"x": 0.40, "y": 0.25, "w": 0.10, "h": 0.10}, {"x": 0.55, "y": 0.25, "w": 0.09, "h": 0.09}]},
        {"time": 0.5, "boxes": [{"x": 0.40, "y": 0.25, "w": 0.09, "h": 0.09}, {"x": 0.55, "y": 0.25, "w": 0.10, "h": 0.10}]},
        {"time": 1.0, "boxes": [{"x": 0.40, "y": 0.25, "w": 0.10, "h": 0.10}, {"x": 0.55, "y": 0.25, "w": 0.09, "h": 0.09}]},
    ]
    traj = media.visual.compute_reframe_trajectory(tracks_close, 0.0, 1.0, target_format='9:16')
    assert traj['has_faces'] is True
    # Group center is (0.40 + 0.64) / 2 = 0.52
    assert 0.48 <= traj['avg_x'] <= 0.56
    # No erratic oscillation between subjects
    x_kps = [k['x'] for k in traj['keypoints']]
    assert max(x_kps) - min(x_kps) < 0.05
    # Safe zoom preserves both faces
    assert traj['max_zoom'] <= 1.10


def test_reframe_multiple_people_far_persistent_tracking():
    """When multiple people are too far apart to fit in one pane, maintain persistent tracking without ping-ponging."""
    tracks_far = [
        {"time": 0.0, "boxes": [{"x": 0.20, "y": 0.25, "w": 0.15, "h": 0.15}, {"x": 0.70, "y": 0.25, "w": 0.14, "h": 0.14}]},
        {"time": 0.5, "boxes": [{"x": 0.20, "y": 0.25, "w": 0.14, "h": 0.14}, {"x": 0.70, "y": 0.25, "w": 0.15, "h": 0.15}]},
        {"time": 1.0, "boxes": [{"x": 0.20, "y": 0.25, "w": 0.15, "h": 0.15}, {"x": 0.70, "y": 0.25, "w": 0.14, "h": 0.14}]},
    ]
    traj = media.visual.compute_reframe_trajectory(tracks_far, 0.0, 1.0, target_format='9:16')
    # Persistent tracking on first selected subject without ping-ponging across screen
    x_kps = [k['x'] for k in traj['keypoints']]
    assert max(x_kps) - min(x_kps) < 0.05
    # Conservative zoom: 1.0x when multiple separated people are in scene
    assert traj['max_zoom'] == 1.0


def test_reframe_scene_cut_transition_no_cross_scene_gliding():
    """Scene transitions cut immediately without cross-scene whip-pans or pre-cut drift."""
    tracks_cut = [
        {"time": 0.0, "boxes": [{"x": 0.75, "y": 0.25, "w": 0.10, "h": 0.10}]},
        {"time": 0.5, "boxes": [{"x": 0.75, "y": 0.25, "w": 0.10, "h": 0.10}]},
        {"time": 1.0, "boxes": [{"x": 0.15, "y": 0.25, "w": 0.10, "h": 0.10}]},
        {"time": 1.5, "boxes": [{"x": 0.15, "y": 0.25, "w": 0.10, "h": 0.10}]},
    ]
    scenes = [{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 1.5}]
    traj = media.visual.compute_reframe_trajectory(tracks_cut, 0.0, 1.5, scenes=scenes)
    before_cut = [k['x'] for k in traj['keypoints'] if k['t'] < 1.0]
    after_cut = [k['x'] for k in traj['keypoints'] if k['t'] >= 1.0]
    assert all(x > 0.75 for x in before_cut)
    assert all(x < 0.25 for x in after_cut)


def test_reframe_mixed_layout_does_not_activate_split_and_preserves_single_subject():
    """In mixed sequences (e.g. 2 people cutting to 1 person), split screen is NOT activated, avoiding single subject duplication."""
    mixed_tracks = [
        {"time": 0.0, "boxes": [{"x": 0.31, "y": 0.40, "w": 0.08, "h": 0.13}, {"x": 0.65, "y": 0.40, "w": 0.08, "h": 0.13}]},
        {"time": 0.5, "boxes": [{"x": 0.31, "y": 0.40, "w": 0.08, "h": 0.13}, {"x": 0.65, "y": 0.40, "w": 0.08, "h": 0.13}]},
        {"time": 1.0, "boxes": [{"x": 0.31, "y": 0.40, "w": 0.08, "h": 0.13}, {"x": 0.65, "y": 0.40, "w": 0.08, "h": 0.13}]},
        {"time": 1.5, "boxes": [{"x": 0.31, "y": 0.40, "w": 0.08, "h": 0.13}, {"x": 0.65, "y": 0.40, "w": 0.08, "h": 0.13}]},
        {"time": 2.0, "boxes": [{"x": 0.48, "y": 0.40, "w": 0.08, "h": 0.14}]},
        {"time": 2.5, "boxes": [{"x": 0.54, "y": 0.40, "w": 0.07, "h": 0.13}]},
        {"time": 3.0, "boxes": [{"x": 0.48, "y": 0.40, "w": 0.07, "h": 0.13}]},
        {"time": 3.5, "boxes": [{"x": 0.42, "y": 0.40, "w": 0.07, "h": 0.13}]},
    ]
    layout = media.visual.analyze_face_layout(mixed_tracks, 0.0, 4.0)
    assert layout["split_recommended"] is False

    flt, is_split, info = media.visual.build_reframe_filter(
        source_width=640,
        source_height=360,
        target_format="9:16",
        reframe=True,
        tracks=mixed_tracks,
        start_time=0.0,
        end_time=4.0,
    )
    assert is_split is False
    traj = info["trajectory"]
    assert traj["has_faces"] is True

@pytest.mark.parametrize('last_boxes', [[], [{'x': 0.2, 'y': 0.3, 'w': 0.1, 'h': 0.15}]])
def test_split_requires_persistent_people_even_for_brief_layout_changes(last_boxes):
    pair = [{'x': 0.2, 'y': 0.3, 'w': 0.1, 'h': 0.15},
            {'x': 0.7, 'y': 0.3, 'w': 0.1, 'h': 0.15}]
    tracks = [{'time': i * 0.5, 'boxes': pair} for i in range(8)]
    assert media.visual.analyze_face_layout(tracks, 0, 4)['split_recommended'] is True
    tracks[-1]['boxes'] = last_boxes
    assert media.visual.analyze_face_layout(tracks, 0, 4)['split_recommended'] is False

@pytest.mark.parametrize('ys,height,expected_visible', [
    ((0.10, 0.75), 0.10, 1),
    ((0.30, 0.50), 0.08, 1),
    ((0.39, 0.51), 0.04, 2),
])
def test_portrait_to_landscape_preserves_people_in_effective_crop(ys, height, expected_visible):
    boxes = [{'x': 0.45, 'y': y, 'w': 0.10, 'h': height} for y in ys]
    tracks = [{'time': i * 0.5, 'boxes': boxes if i % 2 == 0 else boxes[::-1]}
              for i in range(5)]
    _, _, info = media.visual.build_reframe_filter(
        1080, 1920, '16:9', True, tracks, start_time=0, end_time=2)
    for point in info['trajectory']['keypoints']:
        # Final FFmpeg crop uses a 1080x608 window and 40% headroom.
        visible_w = 1080 / (1080 * point['z'])
        visible_h = 608 / (1920 * point['z'])
        left = max(0, min(point['x'] - visible_w / 2, 1 - visible_w))
        top = max(0, min(point['y'] - 0.4 * visible_h, 1 - visible_h))
        visible = [b for b in boxes if left <= b['x'] and b['x'] + b['w'] <= left + visible_w
                   and top <= b['y'] and b['y'] + b['h'] <= top + visible_h]
        assert len(visible) == expected_visible


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_representative_thumbnail_extraction_local(tmp_path):
    """Extract representative persistent thumbnail avoiding initial pitch-black frames."""
    source = tmp_path / 'sample.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc=size=640x360:rate=25:duration=3',
        '-c:v', 'libx264', str(source),
    ], check=True, capture_output=True)

    thumb_out = tmp_path / 'thumbnail.jpg'
    result_path = media.extract_representative_thumbnail(source, thumb_out)
    assert result_path == thumb_out
    assert thumb_out.is_file()
    assert thumb_out.stat().st_size > 0

    # Verify JPEG SOI marker
    header = thumb_out.read_bytes()[:2]
    assert header == b'\xff\xd8'

    # Verify permissions (0o600)
    mode = thumb_out.stat().st_mode & 0o777
    assert mode == 0o600


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_ensure_project_thumbnail_directory_and_cache(tmp_path):
    """ensure_project_thumbnail locates preview/source in project dir and returns cached thumbnail."""
    project_dir = tmp_path / 'proj_123'
    project_dir.mkdir(parents=True)
    preview = project_dir / 'preview.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc=size=320x240:rate=25:duration=1',
        '-c:v', 'libx264', str(preview),
    ], check=True, capture_output=True)

    thumb = media.ensure_project_thumbnail(project_dir)
    assert thumb == project_dir / 'thumbnail.jpg'
    assert thumb.is_file()
    mtime_first = thumb.stat().st_mtime

    # Calling again on existing project thumbnail returns existing path immediately
    thumb_again = media.ensure_project_thumbnail(project_dir)
    assert thumb_again == thumb
    assert thumb_again.stat().st_mtime == mtime_first


def test_source_title_metadata_resolution(tmp_path):
    """extract_source_title checks sidecar info, format metadata, and filename stems cleanly."""
    proj_dir = tmp_path / 'proj'
    proj_dir.mkdir()
    video_path = proj_dir / 'meu_podcast_viral.mp4'
    video_path.touch()

    # 1. Fallback to filename stem when no metadata sidecar exists
    assert media.extract_source_title(video_path) == 'meu_podcast_viral'

    # 2. Sidecar url_metadata.json takes precedence
    sidecar = proj_dir / 'url_metadata.json'
    sidecar.write_text('{"title": "Episódio 42 - Entrevista com Especialista"}', encoding='utf-8')
    assert media.extract_source_title(video_path) == 'Episódio 42 - Entrevista com Especialista'

    # 3. Default fallback for generic names
    generic_path = tmp_path / 'source.media'
    generic_path.touch()
    assert media.extract_source_title(generic_path, default='Título Padrão') == 'Título Padrão'


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_ingest_url_official_thumbnail_conversion_and_fallback(tmp_path, monkeypatch):
    """ingest_url converts official yt-dlp thumbnail to thumbnail.jpg or falls back to video extraction."""
    dest_path = tmp_path / 'source'
    video_file = tmp_path / 'source.mp4'

    # Create dummy video
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc=size=320x240:rate=25:duration=1',
        '-c:v', 'libx264', str(video_file),
    ], check=True, capture_output=True)

    # Create mock official thumbnail
    mock_raw_thumb = tmp_path / 'source.webp'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'color=c=blue:size=320x240:d=1',
        '-vframes', '1', str(mock_raw_thumb),
    ], check=True, capture_output=True)

    # Mock yt_dlp
    class DummyYDL:
        def __init__(self, opts):
            self.opts = opts
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download=True):
            return {'title': 'Vídeo Oficial do Canal', 'id': 'abc1234', 'uploader': 'Canal'}

    monkeypatch.setattr(media, 'validate_public_url', lambda url: None)
    import yt_dlp
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', DummyYDL)

    out = media.ingest_url('https://example.com/watch?v=123', dest_path)
    assert out.is_file()

    # Verify thumbnail.jpg was created and raw .webp was cleaned up
    thumb = dest_path.parent / 'thumbnail.jpg'
    assert thumb.is_file()
    assert thumb.stat().st_size > 0
    assert not mock_raw_thumb.exists()

    # Verify sidecar info
    info_file = dest_path.parent / 'source_info.json'
    assert info_file.is_file()
    assert 'Vídeo Oficial do Canal' in info_file.read_text(encoding='utf-8')


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='FFmpeg required')
def test_render_guarantees_reframe_and_subtitles_on_for_generated_cuts(tmp_path, monkeypatch):
    """Generated cuts force reframe=True and subtitles=True even when legacy settings had them disabled."""
    monkeypatch.setattr(media, 'is_vaapi_supported', lambda: False)
    source = tmp_path / 'src_cut.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc=size=640x360:rate=25:duration=2',
        '-c:v', 'libx264', str(source),
    ], check=True, capture_output=True)

    out_cut = tmp_path / 'out_cut.mp4'

    # Candidate representing a generated cut from the ranking pipeline (contains 'id' and 'score')
    # With legacy options disabling reframe and subtitles
    candidate = {
        'id': 'cand_123',
        'analysis_id': 'anal_456',
        'score': 85.0,
        'start': 0.0,
        'end': 1.0,
        'edit': {
            'format': '9:16',
            'reframe': False,      # Legacy cut setting
            'subtitles': False,    # Legacy cut setting
            'start': 0.0,
            'end': 1.0,
            'words': [{'start': 0.1, 'end': 0.8, 'word': 'teste'}],
        },
    }
    legacy_options = {
        'reframe': False,
        'subtitles': False,
        'format': '9:16',
    }

    timeline = {
        'tracks': [{'time': 0.0, 'boxes': [{'x': 0.7, 'y': 0.2, 'w': 0.15, 'h': 0.15}]}],
        'words': [{'start': 0.1, 'end': 0.8, 'word': 'teste'}],
    }

    res = media.render(source, out_cut, candidate, timeline, legacy_options)
    assert res.is_file()
    assert res.stat().st_size > 0

    # Helper enforce_cut_settings test
    normalized = media.enforce_cut_settings(candidate)
    assert normalized['edit']['reframe'] is True
    assert normalized['edit']['subtitles'] is True
