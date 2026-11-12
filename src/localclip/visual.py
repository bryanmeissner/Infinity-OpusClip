"""Visual processing pipeline for local video clipping.

Handles scene cut detection, face/subject tracking, visual event analysis,
crop and reframe geometry (including split-screen for multi-speaker layouts),
and lightweight thumbnail extraction.
"""

from __future__ import annotations

import base64
import logging
import math
import os
import re
import signal
import subprocess
from pathlib import Path
from typing import Callable
from uuid import uuid4

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Cached Haar Cascade Classifiers for face detection
_FACE_CASCADE: cv2.CascadeClassifier | None = None
_PROFILE_CASCADE: cv2.CascadeClassifier | None = None


def get_face_cascade() -> cv2.CascadeClassifier | None:
    """Load and cache the frontal face cascade classifier."""
    global _FACE_CASCADE
    if _FACE_CASCADE is not None and not _FACE_CASCADE.empty():
        return _FACE_CASCADE

    search_paths = [
        getattr(cv2, "data", None) and getattr(cv2.data, "haarcascades", None)
        and os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"),
        "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
    ]

    for p in search_paths:
        if p and os.path.exists(p):
            cascade = cv2.CascadeClassifier(p)
            if not cascade.empty():
                _FACE_CASCADE = cascade
                logger.debug("Loaded frontal face cascade from %s", p)
                return _FACE_CASCADE

    logger.warning("No frontal face cascade XML found in search paths")
    return None


def get_profile_cascade() -> cv2.CascadeClassifier | None:
    """Load and cache the profile face cascade classifier for side angles."""
    global _PROFILE_CASCADE
    if _PROFILE_CASCADE is not None and not _PROFILE_CASCADE.empty():
        return _PROFILE_CASCADE

    search_paths = [
        getattr(cv2, "data", None) and getattr(cv2.data, "haarcascades", None)
        and os.path.join(cv2.data.haarcascades, "haarcascade_profileface.xml"),
        "/usr/share/opencv4/haarcascades/haarcascade_profileface.xml",
        "/usr/share/opencv/haarcascades/haarcascade_profileface.xml",
    ]

    for p in search_paths:
        if p and os.path.exists(p):
            cascade = cv2.CascadeClassifier(p)
            if not cascade.empty():
                _PROFILE_CASCADE = cascade
                logger.debug("Loaded profile face cascade from %s", p)
                return _PROFILE_CASCADE

    return None


def detect_scenes(
    video_path: Path,
    start_time: float,
    end_time: float,
    threshold: float = 0.3,
    cancel: Callable[[], bool] | None = None,
) -> list[dict]:
    """Detect scene cut boundaries within [start_time, end_time].

    Returns a list of dicts: [{'start': float, 'end': float}, ...]
    with absolute timestamps relative to the original video.
    """
    if end_time <= start_time:
        return [{"start": round(start_time, 3), "end": round(end_time, 3)}]

    duration = end_time - start_time
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v", "info",
        "-protocol_whitelist", "file,pipe,crypto,data",
        "-ss", f"{start_time:.3f}",
        "-to", f"{end_time:.3f}",
        "-i", str(video_path),
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-",
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=os.setsid,
    )

    cuts: list[float] = []
    # Pattern to match pts_time from showinfo: "pts_time:12.345"
    pts_regex = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")

    try:
        assert proc.stderr is not None
        for line in proc.stderr:
            if cancel and cancel():
                _kill_process_group(proc)
                raise RuntimeError("Scene detection cancelled by user.")
            match = pts_regex.search(line)
            if match:
                rel_time = float(match.group(1))
                abs_time = start_time + rel_time
                if start_time < abs_time < end_time:
                    cuts.append(round(abs_time, 3))
        proc.wait(timeout=30.0)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
    except BaseException:
        _kill_process_group(proc)
        raise

    # Sort and remove near-duplicate cuts (within 0.5s)
    cuts = sorted(list(set(cuts)))
    filtered_cuts: list[float] = []
    for c in cuts:
        if not filtered_cuts or (c - filtered_cuts[-1]) >= 0.5:
            filtered_cuts.append(c)

    # Build continuous intervals [start_time, c1], [c1, c2], ..., [cn, end_time]
    scenes: list[dict] = []
    current_start = start_time
    for c in filtered_cuts:
        if c > current_start + 0.2:
            scenes.append({"start": round(current_start, 3), "end": round(c, 3)})
            current_start = c
    if current_start < end_time:
        scenes.append({"start": round(current_start, 3), "end": round(end_time, 3)})

    if not scenes:
        scenes = [{"start": round(start_time, 3), "end": round(end_time, 3)}]

    return scenes


def detect_faces_in_frame(
    frame_bgr: np.ndarray,
    cascade: cv2.CascadeClassifier | None = None,
) -> list[dict]:
    """Detect faces in a single BGR frame, returning normalized coordinates [0.0..1.0]."""
    if cascade is None:
        cascade = get_face_cascade()
    if cascade is None:
        return []

    h, w = frame_bgr.shape[:2]
    if h == 0 or w == 0:
        return []

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    # Run detection
    # Run frontal face detection
    faces = list(cascade.detectMultiScale(
        gray,
        scaleFactor=1.15,
        minNeighbors=4,
        minSize=(int(w * 0.05), int(h * 0.05)),
        maxSize=(int(w * 0.90), int(h * 0.90)),
    ))
    if len(faces) == 0:
        # Global equalization fallback for poor native contrast
        faces = list(cascade.detectMultiScale(
            cv2.equalizeHist(gray),
            scaleFactor=1.15,
            minNeighbors=4,
            minSize=(int(w * 0.05), int(h * 0.05)),
            maxSize=(int(w * 0.90), int(h * 0.90)),
        ))

    # If no frontal face found, check profile face cascade (including horizontal flip)
    if len(faces) == 0:
        prof_cascade = get_profile_cascade()
        if prof_cascade:
            prof_faces = prof_cascade.detectMultiScale(
                gray,
                scaleFactor=1.15,
                minNeighbors=4,
                minSize=(int(w * 0.05), int(h * 0.05)),
                maxSize=(int(w * 0.90), int(h * 0.90)),
            )
            if len(prof_faces) > 0:
                faces = list(prof_faces)
            else:
                # Test flipped image for opposite side profile
                flipped_gray = cv2.flip(gray, 1)
                flipped_faces = prof_cascade.detectMultiScale(
                    flipped_gray,
                    scaleFactor=1.15,
                    minNeighbors=4,
                    minSize=(int(w * 0.05), int(h * 0.05)),
                    maxSize=(int(w * 0.90), int(h * 0.90)),
                )
                for (fx, fy, fw, fh) in flipped_faces:
                    # Invert horizontal coordinate back to original frame
                    faces.append((w - (fx + fw), fy, fw, fh))

    boxes: list[dict] = []
    for (x, y, fw, fh) in faces:
        boxes.append({
            "x": round(float(x) / w, 4),
            "y": round(float(y) / h, 4),
            "w": round(float(fw) / w, 4),
            "h": round(float(fh) / h, 4),
        })
    return boxes


def track_subjects(
    video_path: Path,
    start_time: float,
    end_time: float,
    sample_fps: float = 2.0,
    cancel: Callable[[], bool] | None = None,
    source_width: int | None = None,
    source_height: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """Sample video frames across [start_time, end_time] to track subjects and detect visual events.

    Returns:
        (tracks, visual_events)
        tracks: [{'time': float, 'boxes': [{'x': float, 'y': float, 'w': float, 'h': float}]}]
        visual_events: [{'start': float, 'end': float, 'type': str, 'confidence': float, 'evidence': dict}]
    """
    if end_time <= start_time:
        return ([], [])

    duration = end_time - start_time
    if source_width and source_height and source_width > 0 and source_height > 0:
        if source_width >= source_height:
            sample_w = 640
            sample_h = max(2, int(round(640 * source_height / source_width)) // 2 * 2)
        else:
            sample_h = 640
            sample_w = max(2, int(round(640 * source_width / source_height)) // 2 * 2)
    else:
        sample_w = 640
        sample_h = 360
    frame_bytes_len = sample_w * sample_h * 3

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v", "error",
        "-protocol_whitelist", "file,pipe,crypto,data",
        "-ss", f"{start_time:.3f}",
        "-to", f"{end_time:.3f}",
        "-i", str(video_path),
        "-vf", f"fps={sample_fps:.2f}:start_time=0:round=up,scale={sample_w}:{sample_h},setsar=1",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "pipe:1",
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )

    cascade = get_face_cascade()
    tracks: list[dict] = []
    frame_stats: list[dict] = []
    prev_gray: np.ndarray | None = None
    frame_idx = 0

    try:
        assert proc.stdout is not None
        while True:
            if cancel and cancel():
                _kill_process_group(proc)
                raise RuntimeError("Visual tracking cancelled by user.")

            raw_frame = proc.stdout.read(frame_bytes_len)
            if len(raw_frame) < frame_bytes_len:
                break

            current_time = round(start_time + (frame_idx / sample_fps), 3)
            if current_time > end_time:
                break

            frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((sample_h, sample_w, 3))

            # Face detection
            boxes = detect_faces_in_frame(frame, cascade) if cascade else []
            tracks.append({
                "time": current_time,
                "boxes": boxes,
            })

            # Motion estimation
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            motion_score = 0.0
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                motion_score = float(np.mean(diff))
            prev_gray = gray

            frame_stats.append({
                "time": current_time,
                "num_faces": len(boxes),
                "motion": motion_score,
            })
            frame_idx += 1

        proc.wait(timeout=30.0)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
    except BaseException:
        _kill_process_group(proc)
        raise

    visual_events = _classify_visual_events(frame_stats, start_time, end_time)
    return tracks, visual_events


def _classify_visual_events(
    frame_stats: list[dict],
    start_time: float,
    end_time: float,
) -> list[dict]:
    """Classify visual events based on physical detector observations with uncertainty annotations."""
    if not frame_stats:
        return []

    events: list[dict] = []
    # Identify spans of consistent conditions
    # 1. Multi-person spans
    multi_spans: list[tuple[float, float]] = []
    single_spans: list[tuple[float, float]] = []
    high_motion_spans: list[tuple[float, float]] = []
    static_spans: list[tuple[float, float]] = []

    for s in frame_stats:
        t = s["time"]
        num_faces = s["num_faces"]
        motion = s["motion"]

        # Physical classifications
        if motion > 22.0:
            high_motion_spans.append((t, t + 0.5))
        elif motion < 3.0 and num_faces == 0:
            static_spans.append((t, t + 0.5))

        if num_faces >= 2:
            multi_spans.append((t, t + 0.5))
        elif num_faces == 1:
            single_spans.append((t, t + 0.5))

    # Helper to merge overlapping spans
    def merge_spans(spans: list[tuple[float, float]], min_duration: float = 1.0) -> list[tuple[float, float]]:
        if not spans:
            return []
        spans = sorted(spans, key=lambda x: x[0])
        merged: list[list[float]] = [[spans[0][0], spans[0][1]]]
        for s, e in spans[1:]:
            if s <= merged[-1][1] + 0.6:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        return [(round(m[0], 2), round(m[1], 2)) for m in merged if (m[1] - m[0]) >= min_duration]

    for s, e in merge_spans(multi_spans, min_duration=1.5):
        events.append({
            "start": s,
            "end": e,
            "type": "multiple_faces",
            "confidence": 0.85,
            "evidence": {
                "detected": "2+ faces in frame",
                "uncertainty": "Identity and talking status unconfirmed locally",
            },
        })

    for s, e in merge_spans(single_spans, min_duration=2.0):
        events.append({
            "start": s,
            "end": e,
            "type": "single_speaker_visual",
            "confidence": 0.88,
            "evidence": {
                "detected": "1 dominant face in frame",
                "uncertainty": "Detector confidence based on frontal face cascade",
            },
        })

    for s, e in merge_spans(high_motion_spans, min_duration=1.0):
        events.append({
            "start": s,
            "end": e,
            "type": "high_motion",
            "confidence": 0.80,
            "evidence": {
                "detected": "Inter-frame luminance displacement above threshold",
                "uncertainty": "Physical camera movement or subject action",
            },
        })

    for s, e in merge_spans(static_spans, min_duration=2.5):
        events.append({
            "start": s,
            "end": e,
            "type": "static_or_presentation",
            "confidence": 0.75,
            "evidence": {
                "detected": "Negligible motion and no faces detected",
                "uncertainty": "Could be slide, graphic overlay, or empty scene",
            },
        })

    events.sort(key=lambda x: x["start"])
    return events


def analyze_face_layout(
    tracks: list[dict],
    start_time: float,
    end_time: float,
) -> dict:
    """Analyze face spatial distribution within [start_time, end_time].

    Detects if there are multiple subjects separated horizontally
    (e.g., podcast / interview setup) to recommend split screen.
    """
    relevant_tracks = [t for t in tracks if start_time <= t.get("time", 0.0) <= end_time]
    if not relevant_tracks:
        return {
            "split_recommended": False,
            "primary_x": 0.5,
            "confidence": 0.5,
            "multi_subject_ratio": 0.0,
        }

    frames_with_faces = 0
    frames_with_multi = 0
    all_centers: list[float] = []
    left_centers: list[float] = []
    right_centers: list[float] = []

    for t in relevant_tracks:
        boxes = t.get("boxes", [])
        if not boxes:
            continue
        frames_with_faces += 1
        if len(boxes) >= 2:
            frames_with_multi += 1

        centers = [b["x"] + (b["w"] / 2.0) for b in boxes]
        all_centers.extend(centers)

        for cx in centers:
            if cx < 0.45:
                left_centers.append(cx)
            elif cx > 0.55:
                right_centers.append(cx)

    if not all_centers:
        return {
            "split_recommended": False,
            "primary_x": 0.5,
            "confidence": 0.5,
            "multi_subject_ratio": 0.0,
        }

    multi_ratio = frames_with_multi / max(frames_with_faces, 1)
    has_bimodal = (
        len(left_centers) >= max(3, int(0.20 * len(all_centers))) and
        len(right_centers) >= max(3, int(0.20 * len(all_centers)))
    )

    # Static panes are safe only with multiple subjects throughout the sampled clip.
    # Even a brief single-person section would otherwise duplicate that subject.
    # Missed detections conservatively choose the dynamic single-frame trajectory.
    if frames_with_multi == len(relevant_tracks) and has_bimodal:
        left_mean = float(np.mean(left_centers))
        right_mean = float(np.mean(right_centers))
        sep = right_mean - left_mean
        if sep >= 0.28:
            return {
                "split_recommended": True,
                "left_x": round(float(np.clip(left_mean, 0.15, 0.45)), 3),
                "right_x": round(float(np.clip(right_mean, 0.55, 0.85)), 3),
                "separation": round(sep, 3),
                "confidence": round(min(0.95, 0.6 + multi_ratio * 0.4), 2),
                "multi_subject_ratio": round(multi_ratio, 2),
            }

    # Single dominant subject or mixed layout (preserves single/group trajectory without duplicate panes)
    median_x = float(np.median(all_centers))
    return {
        "split_recommended": False,
        "primary_x": round(median_x, 3),
        "confidence": 0.85,
        "multi_subject_ratio": round(multi_ratio, 2),
    }


def compute_reframe_trajectory(
    tracks: list[dict],
    start_time: float,
    end_time: float,
    kept_intervals: list[tuple[float, float]] | None = None,
    default_x: float = 0.5,
    default_y: float = 0.5,
    min_zoom: float = 1.0,
    max_zoom: float = 1.25,
    auto_zoom: bool = True,
    scenes: list[dict] | None = None,
    target_format: str = "9:16",
    source_width: int = 1920,
    source_height: int = 1080,
) -> dict:
    """Compute bounded smooth temporal subject-following and modest face-based auto zoom.

    Maps source video face tracks into output time (accounting for kept intervals and cuts),
    interpolates across missing detections, applies bidirectional EMA temporal smoothing,
    and generates compact piecewise-linear expressions evaluated natively by FFmpeg.
    """
    if kept_intervals is None:
        intervals = [(float(start_time), float(end_time))]
    else:
        intervals = [(float(k[0]), float(k[1])) for k in kept_intervals if k[1] > k[0]]

    total_duration = sum(k[1] - k[0] for k in intervals)
    if total_duration <= 0.05:
        return {
            "has_faces": False,
            "is_dynamic": False,
            "has_zoom": False,
            "x_expr": f"{default_x:.3f}",
            "y_expr": f"{default_y:.3f}",
            "z_expr": f"{min_zoom:.3f}",
            "avg_x": default_x,
            "avg_y": default_y,
            "avg_zoom": min_zoom,
            "min_zoom": min_zoom,
            "max_zoom": min_zoom,
            "keypoints": [{"t": 0.0, "x": default_x, "y": default_y, "z": min_zoom}],
            "duration": total_duration,
        }

    # Crop dimensions and headroom must match the final aspect-ratio crop.
    if source_width > 0 and source_height > 0:
        if target_format == "16:9":
            ar = 16.0 / 9.0
        elif target_format == "1:1":
            ar = 1.0
        else:
            ar = 9.0 / 16.0
        src_ar = source_width / source_height
        if src_ar >= ar:
            crop_w = float((source_height * ar) / source_width)
            crop_h = 1.0
        else:
            crop_w = 1.0
            crop_h = float(src_ar / ar)
    else:
        crop_w = 0.316 if target_format == "9:16" else (0.5625 if target_format == "1:1" else 1.0)
        crop_h = 1.0
    headroom = 0.35 if target_format == "9:16" else 0.40

    # 1. Map tracks from source time into output timeline
    samples: list[dict] = []
    prev_cx = default_x
    prev_cy = default_y
    for t in tracks:
        src_t = float(t.get("time", 0.0))
        cum_out = 0.0
        for ks, ke in intervals:
            if ks <= src_t <= ke:
                out_t = cum_out + (src_t - ks)
                boxes = t.get("boxes", [])
                if boxes:
                    if len(boxes) == 1:
                        b = boxes[0]
                        cx = float(np.clip(b["x"] + b["w"] / 2.0, 0.15, 0.85))
                        cy = float(np.clip(b["y"] + b["h"] / 2.0, 0.15, 0.85))
                        face_dim = max(b.get("h", 0.15), b.get("w", 0.15))
                        if auto_zoom and max_zoom > min_zoom:
                            z = min_zoom + (max_zoom - min_zoom) * float(
                                np.clip((0.26 - face_dim) / (0.26 - 0.10), 0.0, 1.0)
                            )
                        else:
                            z = min_zoom
                    else:
                        # Multiple people detected in frame
                        x_min = min(b["x"] for b in boxes)
                        x_max = max(b["x"] + b["w"] for b in boxes)
                        y_min = min(b["y"] for b in boxes)
                        y_max = max(b["y"] + b["h"] for b in boxes)
                        group_w = x_max - x_min
                        group_h = y_max - y_min

                        # Both axes must fit, including the space above the focus
                        # consumed by headroom. Otherwise frame a person, not empty space.
                        safe_max = min(
                            max_zoom, 1.10,
                            crop_w / (group_w + 0.06),
                            2 * headroom * crop_h / (group_h + 0.06),
                        )
                        fits_group = safe_max >= min_zoom
                        if fits_group:
                            cx = float(np.clip((x_min + x_max) / 2.0, 0.15, 0.85))
                            cy = float(np.clip((y_min + y_max) / 2.0, 0.15, 0.85))
                            # Keep zoom conservative so no faces are cut when framing a group
                            if group_w > 0.5 * crop_w or not auto_zoom:
                                z = min_zoom
                            else:
                                eff_dim = max(group_w, group_h)
                                z = min_zoom + (safe_max - min_zoom) * float(
                                    np.clip((0.26 - eff_dim) / (0.26 - 0.10), 0.0, 1.0)
                                )
                            visible_w, visible_h = crop_w / z, crop_h / z
                            left = max(0.0, min(cx - visible_w / 2, 1.0 - visible_w))
                            top = max(0.0, min(cy - headroom * visible_h, 1.0 - visible_h))
                            fits_group = (left <= x_min and x_max <= left + visible_w
                                          and top <= y_min and y_max <= top + visible_h)
                        if not fits_group:
                            # Preserve the nearest subject in two dimensions, so
                            # vertically separated people do not alternate either.
                            chosen = min(
                                boxes,
                                key=lambda b: ((b["x"] + b["w"] / 2.0 - prev_cx) ** 2
                                               + (b["y"] + b["h"] / 2.0 - prev_cy) ** 2)
                            )
                            cx = float(np.clip(chosen["x"] + chosen["w"] / 2.0, 0.15, 0.85))
                            cy = float(np.clip(chosen["y"] + chosen["h"] / 2.0, 0.15, 0.85))
                            # When tracking one subject among separated people, keep zoom safe (min_zoom)
                            z = min_zoom

                    prev_cx = cx
                    prev_cy = cy
                    samples.append({
                        "out_t": round(out_t, 3),
                        "x": cx,
                        "y": cy,
                        "z": round(z, 3),
                        "detected": True,
                    })
                else:
                    samples.append({
                        "out_t": round(out_t, 3),
                        "x": default_x,
                        "y": default_y,
                        "z": min_zoom,
                        "detected": False,
                    })
                break
            cum_out += (ke - ks)
    samples.sort(key=lambda s: s["out_t"])

    # 2. Check if ANY faces were detected across the clip
    detected_samples = [s for s in samples if s["detected"]]
    if not detected_samples:
        return {
            "has_faces": False,
            "is_dynamic": False,
            "has_zoom": False,
            "x_expr": f"{default_x:.3f}",
            "y_expr": f"{default_y:.3f}",
            "z_expr": f"{min_zoom:.3f}",
            "avg_x": default_x,
            "avg_y": default_y,
            "avg_zoom": min_zoom,
            "min_zoom": min_zoom,
            "max_zoom": min_zoom,
            "keypoints": [{"t": 0.0, "x": default_x, "y": default_y, "z": min_zoom}],
            "duration": round(total_duration, 3),
        }

    # 3. Interpolate missing detections:
    # Brief gaps (<= 2.0s) interpolate smoothly between detections.
    # Prolonged gaps (> 2.0s) smoothly ease to neutral center (default_x, default_y, min_zoom)
    # over 1.5s to prevent panning on stale faces during unrelated scenes / landscape b-roll.
    det_indices = [i for i, s in enumerate(samples) if s["detected"]]
    ease_dur = 1.5
    max_bridge = 2.0

    # Leading samples before first detection: ease in from neutral center
    # Leading samples before first detection: hold for max_bridge, then ease in
    first_idx = det_indices[0]
    first_t = samples[first_idx]["out_t"]
    for i in range(first_idx):
        t = samples[i]["out_t"]
        lead = first_t - t
        if lead <= max_bridge:
            samples[i]["x"] = samples[first_idx]["x"]
            samples[i]["y"] = samples[first_idx]["y"]
            samples[i]["z"] = samples[first_idx]["z"]
        elif lead <= max_bridge + ease_dur:
            u = (lead - max_bridge) / ease_dur
            samples[i]["x"] = default_x + (1.0 - u) * (samples[first_idx]["x"] - default_x)
            samples[i]["y"] = default_y + (1.0 - u) * (samples[first_idx]["y"] - default_y)
            samples[i]["z"] = min_zoom + (1.0 - u) * (samples[first_idx]["z"] - min_zoom)
        else:
            samples[i]["x"] = default_x
            samples[i]["y"] = default_y
            samples[i]["z"] = min_zoom

    # Gaps between consecutive detections
    for a_idx, b_idx in zip(det_indices[:-1], det_indices[1:]):
        ta, tb = samples[a_idx]["out_t"], samples[b_idx]["out_t"]
        gap = tb - ta
        if gap <= max_bridge:
            for i in range(a_idx + 1, b_idx):
                t = samples[i]["out_t"]
                u = (t - ta) / gap
                samples[i]["x"] = samples[a_idx]["x"] + u * (samples[b_idx]["x"] - samples[a_idx]["x"])
                samples[i]["y"] = samples[a_idx]["y"] + u * (samples[b_idx]["y"] - samples[a_idx]["y"])
                samples[i]["z"] = samples[a_idx]["z"] + u * (samples[b_idx]["z"] - samples[a_idx]["z"])
        else:
            for i in range(a_idx + 1, b_idx):
                t = samples[i]["out_t"]
                if t <= ta + ease_dur:
                    u = (t - ta) / ease_dur
                    samples[i]["x"] = samples[a_idx]["x"] + u * (default_x - samples[a_idx]["x"])
                    samples[i]["y"] = samples[a_idx]["y"] + u * (default_y - samples[a_idx]["y"])
                    samples[i]["z"] = samples[a_idx]["z"] + u * (min_zoom - samples[a_idx]["z"])
                elif t >= tb - ease_dur:
                    u = (t - (tb - ease_dur)) / ease_dur
                    samples[i]["x"] = default_x + u * (samples[b_idx]["x"] - default_x)
                    samples[i]["y"] = default_y + u * (samples[b_idx]["y"] - default_y)
                    samples[i]["z"] = min_zoom + u * (samples[b_idx]["z"] - min_zoom)
                else:
                    samples[i]["x"] = default_x
                    samples[i]["y"] = default_y
                    samples[i]["z"] = min_zoom

    # Trailing samples after last detection: hold for max_bridge, then ease out
    last_idx = det_indices[-1]
    last_t = samples[last_idx]["out_t"]
    for i in range(last_idx + 1, len(samples)):
        t = samples[i]["out_t"]
        elapsed = t - last_t
        if elapsed <= max_bridge:
            samples[i]["x"] = samples[last_idx]["x"]
            samples[i]["y"] = samples[last_idx]["y"]
            samples[i]["z"] = samples[last_idx]["z"]
        elif elapsed <= max_bridge + ease_dur:
            u = (elapsed - max_bridge) / ease_dur
            samples[i]["x"] = default_x + (1.0 - u) * (samples[last_idx]["x"] - default_x)
            samples[i]["y"] = default_y + (1.0 - u) * (samples[last_idx]["y"] - default_y)
            samples[i]["z"] = min_zoom + (1.0 - u) * (samples[last_idx]["z"] - min_zoom)
        else:
            samples[i]["x"] = default_x
            samples[i]["y"] = default_y
            samples[i]["z"] = min_zoom
    # 4. Map scene cut boundaries into output timeline
    output_cuts: list[float] = []
    if scenes:
        for sc in scenes:
            c_start = float(sc.get("start", 0.0))
            if c_start > float(start_time):
                cum = 0.0
                for ks, ke in intervals:
                    if ks <= c_start <= ke:
                        output_cuts.append(round(cum + (c_start - ks), 3))
                        break
                    cum += (ke - ks)
    output_cuts = sorted(list(set(output_cuts)))

    # 5. Temporal smoothing (bidirectional EMA segmented by cuts to eliminate jitter without bleeding across cuts)
    def _bidirectional_ema(vals: list[float], alpha: float) -> list[float]:
        if len(vals) < 2:
            return list(vals)
        fwd = [vals[0]]
        for v in vals[1:]:
            fwd.append(alpha * v + (1.0 - alpha) * fwd[-1])
        bwd = [fwd[-1]]
        for v in reversed(fwd[:-1]):
            bwd.append(alpha * v + (1.0 - alpha) * bwd[-1])
        bwd.reverse()
        return bwd

    # Partition samples into segments by scene cuts
    segments_indices: list[list[int]] = []
    cur_seg: list[int] = []
    cut_ptr = 0
    for i, s in enumerate(samples):
        st = s["out_t"]
        if cut_ptr < len(output_cuts) and st >= output_cuts[cut_ptr] and cur_seg:
            segments_indices.append(cur_seg)
            cur_seg = []
            cut_ptr += 1
        cur_seg.append(i)
    if cur_seg:
        segments_indices.append(cur_seg)

    smooth_x = [0.0] * len(samples)
    smooth_y = [0.0] * len(samples)
    smooth_z = [0.0] * len(samples)

    for seg in segments_indices:
        seg_xs = [samples[i]["x"] for i in seg]
        seg_ys = [samples[i]["y"] for i in seg]
        seg_zs = [samples[i]["z"] for i in seg]
        sm_x = _bidirectional_ema(seg_xs, alpha=0.85)
        sm_y = _bidirectional_ema(seg_ys, alpha=0.85)
        sm_z = _bidirectional_ema(seg_zs, alpha=0.35)
        for idx, sx, sy, sz in zip(seg, sm_x, sm_y, sm_z):
            smooth_x[idx] = sx
            smooth_y[idx] = sy
            smooth_z[idx] = sz

    sample_times = [s["out_t"] for s in samples]

    # 6. Keypoint selection across output duration (spaced ~1.5s to 2.5s, plus immediate cut transitions)
    step = max(0.5, min(2.0, total_duration / 25.0))
    raw_kp_times = [0.0]
    cur_t = step
    while cur_t < total_duration - 0.2:
        raw_kp_times.append(round(cur_t, 2))
        cur_t += step
    if raw_kp_times[-1] != round(total_duration, 2):
        raw_kp_times.append(round(total_duration, 2))

    # Add discrete cut keypoints around scene transitions (0.02s before and after cut)
    for c in output_cuts:
        if 0.05 < c < total_duration - 0.05:
            raw_kp_times.append(round(c - 0.02, 2))
            raw_kp_times.append(round(c + 0.02, 2))

    kp_times = sorted(list(set(raw_kp_times)))
    keypoints: list[dict] = []
    for kt in kp_times:
        # Determine matching segment for kt based on output_cuts
        seg_idx = 0
        while seg_idx < len(output_cuts) and kt >= output_cuts[seg_idx]:
            seg_idx += 1
        seg_idx = min(seg_idx, len(segments_indices) - 1)
        seg = segments_indices[seg_idx]

        seg_times = [samples[i]["out_t"] for i in seg]
        seg_sx = [smooth_x[i] for i in seg]
        seg_sy = [smooth_y[i] for i in seg]
        seg_sz = [smooth_z[i] for i in seg]

        kx = float(np.clip(np.interp(kt, seg_times, seg_sx), 0.15, 0.85))
        ky = float(np.clip(np.interp(kt, seg_times, seg_sy), 0.15, 0.85))
        kz = float(np.clip(np.interp(kt, seg_times, seg_sz), min_zoom, max_zoom))
        keypoints.append({
            "t": round(kt, 2),
            "x": round(kx, 3),
            "y": round(ky, 3),
            "z": round(kz, 3),
        })
    # 6. Check dynamic variation thresholds
    x_range = max(k["x"] for k in keypoints) - min(k["x"] for k in keypoints)
    y_range = max(k["y"] for k in keypoints) - min(k["y"] for k in keypoints)
    z_range = max(k["z"] for k in keypoints) - min(k["z"] for k in keypoints)

    is_dynamic = (x_range >= 0.03 or y_range >= 0.03)
    has_zoom = (z_range >= 0.02 or any(k["z"] > 1.03 for k in keypoints))

    # Construct flat piecewise-linear expression telescoping across keypoints (zero nested if() calls)
    def _build_linear_sum(kps: list[dict], field: str) -> str:
        if len(kps) < 2:
            return f"{kps[0][field]:.3f}"
        v0 = kps[0][field]
        terms = [f"{v0:.3f}"]
        for k0, k1 in zip(kps[:-1], kps[1:]):
            delta = k1[field] - k0[field]
            dt = max(0.01, k1["t"] - k0["t"])
            if abs(delta) >= 0.001:
                terms.append(f"({delta:+.3f})*clip((t-{k0['t']:.2f})/{dt:.2f},0,1)")
        return "+".join(terms) if len(terms) > 1 else f"{v0:.3f}"

    x_expr = _build_linear_sum(keypoints, "x") if is_dynamic else f"{np.mean([k['x'] for k in keypoints]):.3f}"
    y_expr = _build_linear_sum(keypoints, "y") if is_dynamic else f"{np.mean([k['y'] for k in keypoints]):.3f}"
    z_expr = _build_linear_sum(keypoints, "z") if has_zoom else "1.000"

    return {
        "has_faces": True,
        "is_dynamic": is_dynamic,
        "has_zoom": has_zoom,
        "x_expr": x_expr,
        "y_expr": y_expr,
        "z_expr": z_expr,
        "avg_x": round(float(np.mean([k["x"] for k in keypoints])), 3),
        "avg_y": round(float(np.mean([k["y"] for k in keypoints])), 3),
        "avg_zoom": round(float(np.mean([k["z"] for k in keypoints])), 3),
        "min_zoom": round(float(min(k["z"] for k in keypoints)), 3),
        "max_zoom": round(float(max(k["z"] for k in keypoints)), 3),
        "keypoints": keypoints,
        "duration": round(total_duration, 3),
    }


def build_reframe_filter(
    source_width: int,
    source_height: int,
    target_format: str,
    reframe: bool,
    tracks: list[dict],
    manual_crop_x: float | None = None,
    start_time: float = 0.0,
    end_time: float = 0.0,
    kept_intervals: list[tuple[float, float]] | None = None,
    auto_zoom: bool = True,
    zoom_level: float = 1.25,
    scenes: list[dict] | None = None,
) -> tuple[str, bool, dict]:
    """Construct FFmpeg filtergraph for format conversion, dynamic cropping, and auto zoom.

    Formats:
        '9:16' -> 1080x1920
        '1:1'  -> 1080x1080
        '16:9' -> 1920x1080

    Returns:
        (filter_str, is_split, layout_info)
    """
    layout_info = {
        "target_format": target_format,
        "reframe_active": reframe,
        "is_split": False,
    }

    # Check split screen layout for 9:16 target (intentionally static for dual-speaker interview stability)
    if target_format == "9:16" and reframe and manual_crop_x is None:
        layout = analyze_face_layout(tracks, start_time, end_time)
        if layout.get("split_recommended", False):
            layout_info["is_split"] = True
            layout_info["split_details"] = layout
            lx = layout["left_x"]
            rx = layout["right_x"]
            pane_filter = (
                f"[0:v]split=2[v_top_in][v_bot_in];"
                f"[v_top_in]crop=w='min(iw,ih*1.125)':h='ih':"
                f"x='clip((iw*{lx:.3f})-(ow/2),0,iw-ow)':y=0,scale=1080:960,setsar=1[v_top];"
                f"[v_bot_in]crop=w='min(iw,ih*1.125)':h='ih':"
                f"x='clip((iw*{rx:.3f})-(ow/2),0,iw-ow)':y=0,scale=1080:960,setsar=1[v_bot];"
                f"[v_top][v_bot]vstack=inputs=2,setsar=1[reframe_v]"
            )
            return pane_filter, True, layout_info

    # Target resolution and aspect ratio mappings
    if target_format == "16:9":
        target_w, target_h = 1920, 1080
        ar = 16.0 / 9.0
        headroom = 0.40
    elif target_format == "1:1":
        target_w, target_h = 1080, 1080
        ar = 1.0
        headroom = 0.40
    else:  # default "9:16"
        target_w, target_h = 1080, 1920
        ar = 9.0 / 16.0
        headroom = 0.35

    # Base crop dimensions preserving target aspect ratio without anamorphic squeeze
    if source_width > 0 and source_height > 0:
        src_ar = source_width / source_height
        if src_ar >= ar:
            base_h = 2 * int(source_height // 2)
            base_w = 2 * int(round((base_h * ar) / 2.0))
        else:
            base_w = 2 * int(source_width // 2)
            base_h = 2 * int(round((base_w / ar) / 2.0))
    else:
        base_w, base_h = target_w, target_h

    # Case 1: Manual crop override (fixed horizontal center, no dynamic zoom)
    if manual_crop_x is not None:
        cx = float(np.clip(manual_crop_x, 0.0, 1.0))
        layout_info["crop_center_x"] = round(cx, 3)
        y_expr = "'(ih-oh)/2'" if target_format in ("1:1", "16:9") else "0"
        flt = (
            f"crop=w={base_w}:h={base_h}:"
            f"x='clip(iw*{cx:.3f}-ow/2,0,iw-ow)':y={y_expr},"
            f"scale={target_w}:{target_h},setsar=1"
        )
        return flt, False, layout_info

    # Case 2: Reframe disabled (static neutral center, no dynamic zoom)
    if not reframe:
        y_expr = "'(ih-oh)/2'" if target_format in ("1:1", "16:9") else "0"
        flt = (
            f"crop=w={base_w}:h={base_h}:"
            f"x='(iw-ow)/2':y={y_expr},"
            f"scale={target_w}:{target_h},setsar=1"
        )
        return flt, False, layout_info

    # Case 3: Reframe active — compute trajectory and auto zoom
    traj = compute_reframe_trajectory(
        tracks=tracks,
        start_time=start_time,
        end_time=end_time,
        kept_intervals=kept_intervals,
        default_x=0.5,
        default_y=0.5,
        min_zoom=1.0,
        max_zoom=max(1.0, min(2.5, float(zoom_level))),
        auto_zoom=auto_zoom,
        scenes=scenes,
        target_format=target_format,
        source_width=source_width,
        source_height=source_height,
    )
    layout_info["trajectory"] = traj
    layout_info["crop_center_x"] = traj["avg_x"]

    if not traj["has_faces"]:
        y_expr = "'(ih-oh)/2'" if target_format in ("1:1", "16:9") else "0"
        flt = (
            f"crop=w={base_w}:h={base_h}:"
            f"x='(iw-ow)/2':y={y_expr},"
            f"scale={target_w}:{target_h},setsar=1"
        )
        return flt, False, layout_info

    x_expr = traj["x_expr"]
    y_expr = traj["y_expr"]
    z_expr = traj["z_expr"]
    has_zoom = traj["has_zoom"]

    w_scaled = f"({source_width}*({z_expr}))" if source_width > 0 else f"(iw*({z_expr}))"
    h_scaled = f"({source_height}*({z_expr}))" if source_height > 0 else f"(ih*({z_expr}))"

    if has_zoom:
        flt = (
            f"scale=w='2*trunc(({w_scaled})/2)':h='2*trunc(({h_scaled})/2)':eval=frame,"
            f"crop=w={base_w}:h={base_h}:"
            f"x='clip({w_scaled}*({x_expr})-ow/2,0,{w_scaled}-ow)':"
            f"y='clip({h_scaled}*({y_expr})-{headroom:.2f}*oh,0,{h_scaled}-oh)',"
            f"scale={target_w}:{target_h},setsar=1"
        )
    else:
        flt = (
            f"crop=w={base_w}:h={base_h}:"
            f"x='clip(iw*({x_expr})-ow/2,0,iw-ow)':"
            f"y='clip(ih*({y_expr})-{headroom:.2f}*oh,0,ih-oh)',"
            f"scale={target_w}:{target_h},setsar=1"
        )
    return flt, False, layout_info

def extract_thumbnail(
    video_path: Path,
    timestamp: float,
    max_size: int = 512,
) -> bytes:
    """Extract a single JPEG thumbnail at timestamp via FFmpeg stdout pipe."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v", "error",
        "-protocol_whitelist", "file,pipe,crypto,data",
        "-ss", f"{max(0.0, timestamp):.3f}",
        "-i", str(video_path),
        "-vframes", "1",
        "-vf", f"scale='min({max_size},iw)':'min({max_size},ih)':force_original_aspect_ratio=decrease",
        "-f", "image2",
        "-c:v", "mjpeg",
        "pipe:1",
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError(f"Failed to extract thumbnail at {timestamp}s from {video_path}")
    return res.stdout


def extract_thumbnail_base64(
    video_path: Path,
    timestamp: float,
    max_size: int = 512,
) -> str:
    """Extract thumbnail and return raw base64 string."""
    raw = extract_thumbnail(video_path, timestamp, max_size)
    return base64.b64encode(raw).decode("ascii")


def extract_representative_thumbnail(
    video_path: Path | str,
    output_path: Path | str | None = None,
    timestamp: float | None = None,
    duration: float | None = None,
    max_size: int = 512,
) -> Path:
    """Extract a representative persistent thumbnail to disk atomically with safe permissions.

    If timestamp is omitted, dynamically tests candidate timestamps (e.g. 15% duration)
    to avoid blank/black initial frames or static opening cards.
    Atomically stores the image at output_path (defaulting to video_path.parent / 'thumbnail.jpg').
    """
    in_path = Path(video_path)
    if not in_path.is_file():
        raise FileNotFoundError(f"Vídeo de origem não encontrado: {in_path}")

    out_path = Path(output_path) if output_path else in_path.parent / "thumbnail.jpg"
    out_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Determine candidate timestamps
    if timestamp is not None and timestamp >= 0:
        candidate_ts = [float(timestamp)]
    else:
        dur = float(duration) if duration is not None and duration > 0 else 0.0
        if dur <= 0:
            try:
                cmd_dur = [
                    "ffprobe", "-v", "error",
                    "-protocol_whitelist", "file,pipe,crypto,data",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(in_path),
                ]
                res_d = subprocess.run(cmd_dur, capture_output=True, text=True, timeout=10)
                if res_d.returncode == 0 and res_d.stdout.strip():
                    dur = float(res_d.stdout.strip())
            except Exception:
                dur = 0.0

        if dur >= 10.0:
            candidate_ts = [min(dur * 0.15, 5.0), dur * 0.35, dur * 0.6, dur * 0.8]
        elif dur >= 2.0:
            candidate_ts = [dur * 0.2, dur * 0.5, dur * 0.8]
        elif dur > 0.0:
            candidate_ts = [dur * 0.5, 0.0]
        else:
            candidate_ts = [1.0, 0.5, 0.0]

    tmp_path = out_path.with_name(f".{out_path.stem}_{uuid4().hex[:8]}.tmp.jpg")
    success = False

    for ts in candidate_ts:
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-v", "error",
            "-y",
            "-protocol_whitelist", "file,pipe,crypto,data",
            "-ss", f"{max(0.0, ts):.3f}",
            "-i", str(in_path),
            "-vframes", "1",
            "-vf", f"scale='min({max_size},iw)':'min({max_size},ih)':force_original_aspect_ratio=decrease",
            "-f", "image2",
            "-c:v", "mjpeg",
            "-q:v", "3",
            str(tmp_path),
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            if res.returncode == 0 and tmp_path.is_file() and tmp_path.stat().st_size > 0:
                frame = cv2.imread(str(tmp_path), cv2.IMREAD_GRAYSCALE)
                if frame is None:
                    continue
                representative = (float(frame.std()) >= 10
                                  and 12 < float(frame.mean()) < 245)
                # Keep the first decodable frame as a fallback, but seek past
                # monochrome intros and fades for the persisted representative.
                if not success or (timestamp is None and representative):
                    tmp_path.chmod(0o600)
                    tmp_path.replace(out_path)
                    out_path.chmod(0o600)
                    success = True
                if timestamp is not None or representative:
                    break
        except Exception:
            pass
        finally:
            tmp_path.unlink(missing_ok=True)

    if not success:
        # Direct stdout pipe fallback
        try:
            raw_bytes = extract_thumbnail(in_path, 0.0, max_size)
            tmp_path.write_bytes(raw_bytes)
            tmp_path.chmod(0o600)
            tmp_path.replace(out_path)
            out_path.chmod(0o600)
            success = True
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Falha ao extrair thumbnail representativa de {in_path}: {e}") from e

    return out_path


save_representative_thumbnail = extract_representative_thumbnail

def _kill_process_group(proc: subprocess.Popen) -> None:
    """Safely terminate a subprocess and its process group."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
            proc.wait(timeout=1.0)
    except (ProcessLookupError, OSError):
        pass
