"""Media processing engine for local-first video clipping.

Handles video probing, secure URL ingestion, interval-scoped audio analysis,
speech-to-text with word-level timestamps (faster-whisper), silence/energy detection,
timeline assembly, and multi-format FFmpeg rendering with ASS subtitles,
reframe / split-screen, internal range cutouts, and hardware-accelerated VAAPI encoding
with clean CPU fallback.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import logging
import math
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import wave
import numpy as np

from . import visual

logger = logging.getLogger(__name__)

# Cached VAAPI hardware acceleration state
_VAAPI_DEVICE = os.environ.get("LOCALCLIP_VAAPI_DEVICE", "/dev/dri/renderD128")
_VAAPI_SUPPORTED: bool | None = None


def is_vaapi_supported() -> bool:
    """Probe and cache VAAPI hardware encoding capability.

    Tests /dev/dri/renderD128 with AMD/Intel VAAPI pipeline. Caches result
    to avoid re-probing during active jobs.
    """
    global _VAAPI_SUPPORTED
    if _VAAPI_SUPPORTED is not None:
        return _VAAPI_SUPPORTED

    dev = Path(_VAAPI_DEVICE)
    if not dev.exists():
        _VAAPI_SUPPORTED = False
        return False

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-vaapi_device", str(dev),
        "-f", "lavfi", "-i", "color=size=128x128:rate=1",
        "-vf", "format=nv12,hwupload",
        "-frames:v", "1",
        "-c:v", "h264_vaapi",
        "-f", "null", "-",
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5.0)
        _VAAPI_SUPPORTED = (res.returncode == 0)
    except Exception as e:
        logger.debug("Falha no teste de hardware VAAPI: %s", e)
        _VAAPI_SUPPORTED = False

    logger.info("Suporte a aceleração por hardware VAAPI: %s (dispositivo: %s)", _VAAPI_SUPPORTED, dev)
    return _VAAPI_SUPPORTED


class SafeSSRFContext:
    """Guards against SSRF across all outbound DNS lookups, redirects, and CDN requests."""

    def __enter__(self):
        self._orig_getaddrinfo = socket.getaddrinfo

        def _guarded_getaddrinfo(host, port, *args, **kwargs):
            if host:
                h_str = str(host).lower().strip().strip("[]")
                blocked = {
                    "localhost", "127.0.0.1", "::1", "0.0.0.0",
                    "metadata.google.internal", "instance-data",
                }
                if h_str in blocked or h_str.endswith(".local") or h_str.endswith(".internal"):
                    raise ValueError(f"SSRF bloqueou host proibido: {host}")
            res = self._orig_getaddrinfo(host, port, *args, **kwargs)
            if not res:
                raise ValueError(f"Não foi possível resolver endereço para: {host}")
            for entry in res:
                ip_str = entry[4][0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                    if (
                        not ip.is_global
                        or ip.is_private
                        or ip.is_loopback
                        or ip.is_link_local
                        or ip.is_multicast
                        or ip.is_reserved
                        or ip.is_unspecified
                    ):
                        raise ValueError(f"SSRF bloqueou acesso a IP local ou privado ({host} -> {ip_str})")
                except ValueError as ve:
                    if "SSRF" in str(ve):
                        raise
            return res

        socket.getaddrinfo = _guarded_getaddrinfo
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        socket.getaddrinfo = self._orig_getaddrinfo


# Re-export thumbnail helpers for convenience
extract_thumbnail = visual.extract_thumbnail
extract_thumbnail_base64 = visual.extract_thumbnail_base64
extract_representative_thumbnail = visual.extract_representative_thumbnail
save_representative_thumbnail = visual.save_representative_thumbnail

# Common stopwords in Portuguese and English to filter out from keyword extraction
STOPWORDS = {
    # Portuguese
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "é", "com", "não",
    "uma", "os", "no", "se", "na", "por", "mais", "as", "dos", "como", "mas", "foi",
    "ao", "ele", "das", "tem", "à", "seu", "sua", "ou", "ser", "quando", "muito",
    "nos", "já", "eu", "também", "só", "pelo", "pela", "até", "isso", "ela", "entre",
    "era", "depois", "sem", "mesmo", "aos", "ter", "seus", "quem", "nas", "me", "esse",
    "eles", "estão", "você", "tinha", "foram", "essa", "num", "nem", "suas", "meu",
    "às", "minha", "têm", "numa", "pelos", "elas", "havia", "seja", "qual", "será",
    "nós", "tenho", "lhe", "deles", "essas", "esses", "pelas", "este", "fosse", "dele",
    "tu", "te", "vocês", "vos", "lhes", "meus", "minhas", "teu", "tua", "teus", "tuas",
    "nosso", "nossa", "nossos", "nossas", "dela", "delas", "aqui", "ali", "então",
    "onde", "porque", "porquê", "pra", "pro", "né", "tá", "aí", "olha", "bem", "tudo",
    # English
    "the", "and", "to", "of", "a", "in", "is", "that", "for", "it", "as", "was", "with",
    "on", "at", "by", "this", "be", "are", "from", "or", "have", "an", "not", "your",
    "you", "we", "he", "she", "they", "but", "all", "so", "what", "there", "about",
}


def _kill_process_group(proc: subprocess.Popen) -> None:
    """Terminate subprocess and its entire process group cleanly."""
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


def validate_public_url(url: str) -> None:
    """Validate that a URL is safe for public network access and protects against SSRF.

    Rejects private IPv4/IPv6 addresses, loopbacks, link-local, multicast,
    and reserved ranges upon DNS resolution.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL não pode ser vazia.")

    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Esquema de URL inválido '{parsed.scheme}'. Apenas HTTP e HTTPS são permitidos.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL sem hostname válido.")

    hostname_clean = hostname.lower().strip().strip("[]")
    blocked_hosts = {
        "localhost", "127.0.0.1", "::1", "0.0.0.0",
        "metadata.google.internal", "instance-data",
    }
    if hostname_clean in blocked_hosts or hostname_clean.endswith(".local") or hostname_clean.endswith(".internal"):
        raise ValueError(f"Acesso a host local ou restrito não permitido: {hostname}")

    # Check directly if hostname is IP literal
    try:
        direct_ip = ipaddress.ip_address(hostname_clean)
        if (
            not direct_ip.is_global
            or direct_ip.is_private
            or direct_ip.is_loopback
            or direct_ip.is_link_local
            or direct_ip.is_multicast
            or direct_ip.is_reserved
            or direct_ip.is_unspecified
        ):
            raise ValueError(f"Acesso a IP local ou privado proibido ({hostname_clean}).")
    except ValueError as e:
        if "proibido" in str(e):
            raise

    # Resolve IP and verify each address
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"Falha ao resolver hostname '{hostname}': {e}")

    if not addr_info:
        raise ValueError(f"Não foi possível resolver hostname '{hostname}'.")

    for entry in addr_info:
        ip_str = entry[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if (
            not ip.is_global
            or ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"Acesso a rede local ou privada proibido (resolvido para {ip_str}).")


def probe(path: Path) -> dict:
    """Inspect media file using ffprobe and return stream metadata.

    Restricts input reading to safe local protocols (file, pipe, crypto, data)
    and refuses unhandled network playlist formats (HLS/DASH).

    Returns dict matching shared contract:
    {
        'duration': float,
        'width': int,
        'height': int,
        'fps': float,
        'size': int,
        'codec': str,
        'audio_codec': str | None,
        'has_audio': bool,
        'has_video': bool,
        'rotation': int,
        'display_width': int,
        'display_height': int,
        'bitrate': int | None,
        'sample_rate': int | None,
        'channels': int | None,
        'format_name': str,
    }
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-protocol_whitelist", "file,pipe,crypto,data",
        "-show_entries", "format=duration,size,bit_rate,format_name:format_tags",
        "-show_entries", "stream=index,codec_type,codec_name,width,height,sample_aspect_ratio,display_aspect_ratio,r_frame_rate,avg_frame_rate,channels,sample_rate:stream_tags=rotate,title,TITLE:stream_side_data=rotation",
        "-of", "json",
        str(file_path),
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Falha ao inspecionar vídeo com ffprobe: {e.stderr.strip() or e}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Erro ao decodificar saída JSON do ffprobe: {e}")

    fmt = data.get("format", {})
    format_name = fmt.get("format_name", "")

    # Reject playlist/manifest containers that could trigger external fetches
    disallowed_playlist_formats = {"hls", "applehttp", "dash", "concat"}
    fmt_names = {x.strip().lower() for x in format_name.split(",")} if format_name else set()
    if fmt_names and fmt_names.issubset(disallowed_playlist_formats):
        raise ValueError(f"Formato de playlist ou manifesto não suportado para processamento local: {format_name}")

    streams = data.get("streams", [])

    video_stream: dict | None = None
    audio_stream: dict | None = None

    for s in streams:
        c_type = s.get("codec_type")
        if c_type == "video" and video_stream is None:
            video_stream = s
        elif c_type == "audio" and audio_stream is None:
            audio_stream = s

    if video_stream is None:
        raise ValueError("O arquivo não contém fluxo de vídeo válido.")

    # Duration
    try:
        duration = float(fmt.get("duration") or video_stream.get("duration") or (audio_stream.get("duration") if audio_stream else 0.0) or 0.0)
    except (ValueError, TypeError):
        duration = 0.0

    # Dimensions
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)

    # Frame rate
    fps = 30.0
    for rate_key in ("avg_frame_rate", "r_frame_rate"):
        rate_val = video_stream.get(rate_key)
        if rate_val and "/" in rate_val:
            num, den = rate_val.split("/", 1)
            try:
                num_f, den_f = float(num), float(den)
                if den_f > 0 and num_f > 0:
                    fps = round(num_f / den_f, 2)
                    break
            except ValueError:
                pass

    # Rotation
    rotation = 0
    tags = video_stream.get("tags", {})
    if "rotate" in tags:
        try:
            rotation = int(float(tags["rotate"])) % 360
        except ValueError:
            pass
    for side in video_stream.get("side_data_list", []):
        if "rotation" in side:
            try:
                rotation = int(float(side["rotation"])) % 360
            except ValueError:
                pass

    # Sample and Display Aspect Ratios
    sar = video_stream.get("sample_aspect_ratio")
    dar = video_stream.get("display_aspect_ratio")
    sar_factor = 1.0
    if sar and sar not in ("0:1", "1:1"):
        sep = ":" if ":" in sar else ("/" if "/" in sar else None)
        if sep:
            try:
                s_num, s_den = sar.split(sep, 1)
                s_den_f = float(s_den)
                if s_den_f > 0:
                    sar_factor = float(s_num) / s_den_f
            except (ValueError, TypeError):
                sar_factor = 1.0

    scaled_width = int(round(width * sar_factor)) if (sar_factor > 0 and abs(sar_factor - 1.0) > 0.001) else width
    display_width = scaled_width
    display_height = height
    if rotation in (90, 270):
        display_width, display_height = height, scaled_width
    # Audio details
    has_audio = audio_stream is not None
    audio_codec = audio_stream.get("codec_name") if audio_stream else None
    sample_rate = int(audio_stream["sample_rate"]) if (audio_stream and audio_stream.get("sample_rate")) else None
    channels = int(audio_stream["channels"]) if (audio_stream and audio_stream.get("channels")) else None

    # Size and Bitrate
    size = int(fmt.get("size") or file_path.stat().st_size)
    bitrate = int(fmt.get("bit_rate")) if fmt.get("bit_rate") else None

    # Format tags and title metadata
    fmt_tags = fmt.get("tags", {})
    source_title = fmt_tags.get("title") or fmt_tags.get("TITLE")
    if not source_title and video_stream:
        v_tags = video_stream.get("tags", {})
        source_title = v_tags.get("title") or v_tags.get("TITLE")

    # Check sidecar metadata (e.g. from yt-dlp url_metadata.json or source_info.json)
    if not source_title:
        for sidecar_name in ("url_metadata.json", "source_info.json"):
            sidecar = file_path.parent / sidecar_name
            if sidecar.is_file():
                try:
                    sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
                    if sidecar_data.get("title"):
                        source_title = str(sidecar_data["title"]).strip()
                        break
                except Exception:
                    pass


    return {
        "title": str(source_title).strip() if source_title else None,
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "fps": fps,
        "size": size,
        "codec": video_stream.get("codec_name", "unknown"),
        "audio_codec": audio_codec,
        "has_audio": has_audio,
        "has_video": True,
        "rotation": rotation,
        "sample_aspect_ratio": sar or "1:1",
        "display_aspect_ratio": dar,
        "display_width": display_width,
        "display_height": display_height,
        "bitrate": bitrate,
        "sample_rate": sample_rate,
        "channels": channels,
        "format_name": format_name or "mp4",
    }


def extract_source_title(path: Path | str, default: str | None = None) -> str:
    """Identify source title from video metadata tags, sidecar info, or filename stem."""
    p = Path(path)
    # Check sidecar first
    for sidecar_name in ("url_metadata.json", "source_info.json"):
        sidecar = p.parent / sidecar_name
        if sidecar.is_file():
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                if data.get("title"):
                    return str(data["title"]).strip()
            except Exception:
                pass

    if p.is_file():
        try:
            meta = probe(p)
            if meta.get("title"):
                return str(meta["title"]).strip()
        except Exception:
            pass

    # Fallback to file stem or default
    cleaned = p.stem.strip()
    if cleaned and cleaned not in ("source", "video", "source.media"):
        return cleaned
    return default or "Vídeo"


def ensure_project_thumbnail(
    source_or_dir: Path | str,
    output_path: Path | str | None = None,
) -> Path:
    """Ensure a persistent project thumbnail exists at thumbnail.jpg.

    Accepts a video path or project directory. If the thumbnail already exists and is non-empty,
    returns its path. Otherwise, extracts a representative frame from the source video or preview.
    """
    p = Path(source_or_dir)
    if p.is_dir():
        thumb_path = p / "thumbnail.jpg"
        if thumb_path.is_file() and thumb_path.stat().st_size > 0:
            return thumb_path
        # Look for source or preview
        for cand in (p / "preview.mp4", p / "source", p / "source.media"):
            if cand.is_file():
                return visual.extract_representative_thumbnail(cand, thumb_path)
        for cand in p.glob("*.mp4"):
            if cand.is_file():
                return visual.extract_representative_thumbnail(cand, thumb_path)
        raise FileNotFoundError(f"Nenhum vídeo encontrado no diretório do projeto: {p}")
    else:
        out = Path(output_path) if output_path else p.parent / "thumbnail.jpg"
        if out.is_file() and out.stat().st_size > 0:
            return out
        return visual.extract_representative_thumbnail(p, out)


def enforce_cut_settings(candidate: dict) -> dict:
    """Guarantee reframe and subtitles are enabled on candidate cuts including legacy ones."""
    out = dict(candidate)
    edit = dict(out.get("edit") or {})
    edit["reframe"] = True
    edit["subtitles"] = True
    out["edit"] = edit
    return out


def ingest_url(
    url: str,
    dest: Path,
    progress: Callable[[str, float], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Path:
    """Ingest public online video into dest using yt-dlp with network safety guarantees.

    Verifies against SSRF, respects legal access (no DRM bypass, no private scraping),
    monitors download progress, and supports clean cancellation with partial file cleanup.
    """
    validate_public_url(url)
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("iniciando_download", 0.05)

    try:
        import yt_dlp

        # Hook to update progress and check cancellation
        def progress_hook(d: dict) -> None:
            if cancel and cancel():
                raise RuntimeError("Download cancelado pelo usuário.")
            if d.get("status") == "downloading" and progress:
                downloaded = float(d.get("downloaded_bytes", 0))
                total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
                if total > 0:
                    pct = min(0.95, max(0.05, downloaded / total))
                    progress("baixando", round(pct, 2))

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": str(dest_path),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": False,
            "writethumbnail": True,
            "progress_hooks": [progress_hook],
        }

        info_dict: dict = {}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            with SafeSSRFContext():
                res_info = ydl.extract_info(url, download=True)
                if isinstance(res_info, dict):
                    info_dict = res_info
    except BaseException as e:
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        # Clean up any partial files (.part, .ytdl)
        for part in dest_path.parent.glob(f"{dest_path.name}*"):
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
        if cancel and cancel():
            raise RuntimeError("Download cancelado pelo usuário.") from e
        raise RuntimeError(f"Erro ao baixar vídeo com yt-dlp: {e}") from e

    # Handle output extensions (yt-dlp may output dest_path.mp4 or dest_path.mkv)
    if not dest_path.exists():
        candidates = list(dest_path.parent.glob(f"{dest_path.name}.*"))
        valid_candidates = [
            c for c in candidates
            if not c.name.endswith((".part", ".ytdl")) and c.is_file() and c.stat().st_size > 0
        ]
        if valid_candidates:
            mp4_c = [c for c in valid_candidates if c.suffix.lower() == ".mp4"]
            dest_path = mp4_c[0] if mp4_c else valid_candidates[0]
        else:
            raise FileNotFoundError(f"Arquivo baixado não foi encontrado no destino: {dest_path}")

    if dest_path.stat().st_size == 0:
        dest_path.unlink(missing_ok=True)
        raise ValueError("O arquivo baixado está vazio.")

    # Save URL metadata sidecar safely
    source_title = info_dict.get("title")
    meta_payload = {
        "title": source_title,
        "url": url,
        "id": info_dict.get("id"),
        "uploader": info_dict.get("uploader"),
        "duration": info_dict.get("duration"),
    }
    for sidecar_name in ("url_metadata.json", "source_info.json"):
        try:
            (dest_path.parent / sidecar_name).write_text(
                json.dumps(meta_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # Ensure persistent thumbnail at dest_path.parent / "thumbnail.jpg"
    thumb_dest = dest_path.parent / "thumbnail.jpg"
    thumb_saved = False

    # 1. Prefer official yt-dlp downloaded thumbnail if available
    candidate_official_thumbs = (
        list(dest_path.parent.glob(f"{dest_path.stem}*.webp"))
        + list(dest_path.parent.glob(f"{dest_path.stem}*.jpg"))
        + list(dest_path.parent.glob(f"{dest_path.stem}*.png"))
        + list(dest_path.parent.glob(f"{dest_path.stem}*.jpeg"))
    )
    candidate_official_thumbs = [c for c in candidate_official_thumbs if c.resolve() != thumb_dest.resolve()]

    for raw_thumb in candidate_official_thumbs:
        if raw_thumb.is_file() and raw_thumb.stat().st_size > 0:
            tmp_t = thumb_dest.with_name(f".thumb_{uuid4().hex[:8]}.tmp.jpg")
            cmd_convert = [
                "ffmpeg", "-nostdin", "-v", "error", "-y",
                "-protocol_whitelist", "file,pipe,crypto,data",
                "-i", str(raw_thumb),
                "-vf", "scale='min(512,iw)':'min(512,ih)':force_original_aspect_ratio=decrease",
                "-f", "image2", "-c:v", "mjpeg", "-q:v", "3",
                str(tmp_t),
            ]
            try:
                c_res = subprocess.run(cmd_convert, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                if c_res.returncode == 0 and tmp_t.is_file() and tmp_t.stat().st_size > 0:
                    tmp_t.chmod(0o600)
                    tmp_t.replace(thumb_dest)
                    thumb_dest.chmod(0o600)
                    thumb_saved = True
                    break
            except Exception:
                pass
            finally:
                tmp_t.unlink(missing_ok=True)

    # Clean up raw yt-dlp thumbnail files to keep project dir tidy
    for raw_thumb in candidate_official_thumbs:
        try:
            raw_thumb.unlink(missing_ok=True)
        except OSError:
            pass

    # 2. Fallback to representative frame from local video if official thumbnail failed or absent
    if not thumb_saved or not thumb_dest.is_file() or thumb_dest.stat().st_size == 0:
        try:
            visual.extract_representative_thumbnail(dest_path, thumb_dest)
        except Exception as e:
            logger.warning("Falha ao extrair thumbnail representativa de fallback: %s", e)

    if progress:
        progress("download_concluido", 1.0)

    return dest_path


def _extract_timeline_thumbnails(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    scenes: list[dict],
    audio_events: list[dict],
    visual_events: list[dict],
    max_count: int = 12,
) -> list[dict]:
    """Sample representative keyframe thumbnails across the timeline when allow_images is True."""
    points: set[float] = {start_sec, min(end_sec, round(start_sec + 1.0, 2))}
    for s in scenes:
        mid = round((s["start"] + s["end"]) / 2.0, 2)
        if start_sec <= mid <= end_sec:
            points.add(mid)
    for ve in visual_events:
        if start_sec <= ve["start"] <= end_sec:
            points.add(round(ve["start"], 2))
    for ae in audio_events:
        if start_sec <= ae["start"] <= end_sec:
            points.add(round(ae["start"], 2))

    sorted_points = sorted(list(points))
    if len(sorted_points) > max_count:
        step = len(sorted_points) / max_count
        selected_points = [sorted_points[int(i * step)] for i in range(max_count)]
    else:
        selected_points = sorted_points

    res: list[dict] = []
    for t in selected_points:
        try:
            b64 = visual.extract_thumbnail_base64(video_path, t, max_size=512)
            res.append({
                "time": round(t, 2),
                "image_b64": b64,
                "mime_type": "image/jpeg",
            })
        except Exception as e:
            logger.debug("Falha ao extrair miniatura em t=%.2f: %s", t, e)
    return res


def analyze(
    path: Path,
    workdir: Path,
    options: dict,
    progress: Callable[[str, float], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> dict:
    """Execute local multimodal analysis within options-scoped interval.

    Extracts audio, detects silence, computes RMS energy, runs faster-whisper transcription
    with word-level timestamps and VAD, detects scenes, tracks subjects, and builds
    the structured timeline.
    """
    video_path = Path(path)
    if not video_path.exists():
        raise FileNotFoundError(f"Vídeo de entrada não encontrado: {video_path}")

    workdir_path = Path(workdir)
    workdir_path.mkdir(parents=True, exist_ok=True)

    meta = probe(video_path)
    total_duration = meta["duration"]

    # Scope interval
    start_sec = max(0.0, float(options.get("start") or 0.0))
    if options.get("end") is not None:
        end_sec = min(total_duration, float(options["end"]))
    else:
        end_sec = total_duration

    if end_sec <= start_sec:
        raise ValueError(f"Intervalo de análise inválido: início {start_sec:.2f}s maior ou igual ao fim {end_sec:.2f}s.")

    logger.info("Analyzing %s from %.2fs to %.2fs (duration: %.2fs)", video_path, start_sec, end_sec, end_sec - start_sec)

    has_audio = bool(meta.get("has_audio", False))

    if has_audio:
        # 1. Audio Extraction (16kHz mono WAV for Whisper & analysis)
        if cancel and cancel():
            raise RuntimeError("Análise cancelada pelo usuário.")
        if progress:
            progress("extraindo_audio", 0.08)

        wav_path = workdir_path / "audio_16k.wav"
        cmd_extract = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-protocol_whitelist", "file,pipe,crypto,data",
            "-ss", f"{start_sec:.3f}",
            "-to", f"{end_sec:.3f}",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "16000",
            str(wav_path),
        ]

        proc = subprocess.Popen(cmd_extract, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, preexec_fn=os.setsid)
        try:
            _, err = proc.communicate(timeout=120.0)
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg falhou ao extrair áudio: {err.decode('utf-8', errors='ignore')}")
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            raise RuntimeError("Timeout ao extrair áudio.")
        except BaseException:
            _kill_process_group(proc)
            raise

        # 2. Silence Detection via FFmpeg
        if cancel and cancel():
            raise RuntimeError("Análise cancelada pelo usuário.")
        if progress:
            progress("detectando_silencio", 0.18)

        silence_list = _detect_silence_ffmpeg(video_path, start_sec, end_sec, cancel=cancel)

        # 3. Audio Energy Analysis & Events
        if cancel and cancel():
            raise RuntimeError("Análise cancelada pelo usuário.")
        if progress:
            progress("analisando_audio", 0.28)

        audio_events = _analyze_audio_energy(wav_path, start_sec, end_sec)

        # 4. Speech-to-Text Transcription (faster-whisper)
        if cancel and cancel():
            raise RuntimeError("Análise cancelada pelo usuário.")
        if progress:
            progress("transcrevendo_fala", 0.40)

        segments, words_flat = _transcribe_audio_faster_whisper(
            wav_path,
            start_sec,
            progress=progress,
            cancel=cancel,
        )
    else:
        logger.info("Vídeo sem faixa de áudio detectada: prosseguindo com análise puramente visual.")
        silence_list = []
        audio_events = []
        segments = []
        words_flat = []

    # 5. Scene Detection
    if cancel and cancel():
        raise RuntimeError("Análise cancelada pelo usuário.")
    if progress:
        progress("detectando_cenas", 0.70)

    scenes_list = visual.detect_scenes(video_path, start_sec, end_sec, threshold=0.3, cancel=cancel)

    # 6. Visual Tracking & Visual Events (aspect-ratio-aware dimensions)
    if cancel and cancel():
        raise RuntimeError("Análise cancelada pelo usuário.")
    if progress:
        progress("rastreando_sujeitos", 0.85)

    tracks_list, visual_events = visual.track_subjects(
        video_path,
        start_sec,
        end_sec,
        sample_fps=2.0,
        cancel=cancel,
        source_width=meta.get("display_width", meta.get("width")),
        source_height=meta.get("display_height", meta.get("height")),
    )

    # 7. Thumbnails (when allow_images is True)
    thumbnails_list: list[dict] = []
    if options.get("allow_images"):
        if progress:
            progress("extraindo_miniaturas", 0.92)
        thumbnails_list = _extract_timeline_thumbnails(video_path, start_sec, end_sec, scenes_list, audio_events, visual_events)

    # 8. Keywords and Semantic Tags
    if cancel and cancel():
        raise RuntimeError("Análise cancelada pelo usuário.")
    if progress:
        progress("extraindo_metadados", 0.95)

    keywords_list, semantic_tags_list = _extract_keywords_and_tags(words_flat, options, audio_events, visual_events, has_audio=has_audio)

    if progress:
        progress("concluido", 1.0)

    timeline = {
        "start": round(start_sec, 3),
        "end": round(end_sec, 3),
        "segments": segments,
        "words": words_flat,
        "scenes": scenes_list,
        "silence": silence_list,
        "audio_events": audio_events,
        "visual_events": visual_events,
        "tracks": tracks_list,
        "thumbnails": thumbnails_list,
        "keywords": keywords_list,
        "semantic_tags": semantic_tags_list,
    }

    return timeline


def _detect_silence_ffmpeg(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    noise_db: float = -30.0,
    min_duration: float = 0.5,
    cancel: Callable[[], bool] | None = None,
) -> list[dict]:
    """Detect silence intervals using FFmpeg silencedetect."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v", "info",
        "-protocol_whitelist", "file,pipe,crypto,data",
        "-ss", f"{start_sec:.3f}",
        "-to", f"{end_sec:.3f}",
        "-i", str(video_path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
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

    silence_starts: list[float] = []
    silence_intervals: list[dict] = []
    re_start = re.compile(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)")
    re_end = re.compile(r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)")

    try:
        assert proc.stderr is not None
        for line in proc.stderr:
            if cancel and cancel():
                _kill_process_group(proc)
                raise RuntimeError("Detecção de silêncio cancelada.")
            m_s = re_start.search(line)
            if m_s:
                silence_starts.append(float(m_s.group(1)))
            m_e = re_end.search(line)
            if m_e:
                end_rel = float(m_e.group(1))
                start_rel = silence_starts.pop(0) if silence_starts else 0.0
                abs_s = round(start_sec + start_rel, 3)
                abs_e = round(start_sec + end_rel, 3)
                if abs_e > abs_s:
                    silence_intervals.append({"start": abs_s, "end": abs_e})

        proc.wait(timeout=30.0)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
    except BaseException:
        _kill_process_group(proc)
        raise

    return silence_intervals


def _analyze_audio_energy(wav_path: Path, start_sec: float, end_sec: float) -> list[dict]:
    """Compute streaming RMS energy profile using wave module, avoiding full memory load."""
    if not wav_path.exists():
        return []

    rms_values: list[float] = []
    window_sec = 0.5

    try:
        with wave.open(str(wav_path), "rb") as wf:
            framerate = wf.getframerate()
            sampwidth = wf.getsampwidth()
            nchannels = wf.getnchannels()
            if framerate <= 0 or sampwidth != 2:
                logger.warning("Formato WAV inesperado para energia: rate=%s width=%s", framerate, sampwidth)
                return []

            window_frames = max(1, int(window_sec * framerate))
            while True:
                raw_chunk = wf.readframes(window_frames)
                if not raw_chunk:
                    break
                samples = np.frombuffer(raw_chunk, dtype=np.int16).astype(np.float32) / 32768.0
                if nchannels > 1:
                    samples = samples[::nchannels]
                if len(samples) == 0:
                    break
                rms = float(np.sqrt(np.mean(samples**2)))
                rms_values.append(rms)
    except Exception as e:
        logger.warning("Falha ao analisar energia do áudio: %s", e)
        return []

    if not rms_values:
        return []

    median_rms = float(np.median(rms_values))
    threshold_rms = max(0.08, median_rms * 2.8)

    audio_events: list[dict] = []
    in_spike = False
    spike_start = 0.0
    max_spike_rms = 0.0

    for i, rms in enumerate(rms_values):
        t = start_sec + (i * window_sec)
        if rms >= threshold_rms:
            if not in_spike:
                in_spike = True
                spike_start = t
                max_spike_rms = rms
            else:
                max_spike_rms = max(max_spike_rms, rms)
        else:
            if in_spike:
                spike_end = min(end_sec, t)
                confidence = round(min(1.0, max_spike_rms / (threshold_rms * 1.5 + 1e-6)), 2)
                audio_events.append({
                    "start": round(spike_start, 2),
                    "end": round(spike_end, 2),
                    "type": "audio_energy_spike",
                    "confidence": confidence,
                    "evidence": {
                        "peak_rms": round(max_spike_rms, 3),
                        "baseline_rms": round(median_rms, 3),
                        "uncertainty": "Sinal físico detectado; causa semântica (risada/grito/aplauso) não verificada",
                    },
                })
                in_spike = False

    if in_spike:
        audio_events.append({
            "start": round(spike_start, 2),
            "end": round(end_sec, 2),
            "type": "audio_energy_spike",
            "confidence": 0.85,
            "evidence": {
                "peak_rms": round(max_spike_rms, 3),
                "baseline_rms": round(median_rms, 3),
                "uncertainty": "Sinal físico detectado; causa semântica não verificada",
            },
        })

    return audio_events


def _transcribe_audio_faster_whisper(
    wav_path: Path,
    start_sec: float,
    progress: Callable[[str, float], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Transcribe audio using faster-whisper with word timestamps and VAD on CPU."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("faster-whisper não está disponível no ambiente.") from e

    model_name = os.environ.get("LOCALCLIP_WHISPER_MODEL", "base")
    cpu_threads = min(2, int(os.environ.get("LOCALCLIP_CPU_THREADS", "2")))
    logger.info("Initializing faster-whisper model (%s, CPU, int8, cpu_threads=%d)...", model_name, cpu_threads)
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=cpu_threads)

    if cancel and cancel():
        raise RuntimeError("Transcrição cancelada pelo usuário.")

    segments_gen, info = model.transcribe(
        str(wav_path),
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        word_timestamps=True,
    )

    segments_out: list[dict] = []
    words_flat_out: list[dict] = []

    for seg in segments_gen:
        if cancel and cancel():
            raise RuntimeError("Transcrição cancelada pelo usuário.")

        seg_start_abs = round(start_sec + float(seg.start), 3)
        seg_end_abs = round(start_sec + float(seg.end), 3)

        seg_words: list[dict] = []
        if seg.words:
            for w in seg.words:
                if w.start is None or w.end is None:
                    continue
                clean_text = w.word.strip()
                if not clean_text:
                    continue
                w_start_abs = round(start_sec + float(w.start), 3)
                w_end_abs = round(start_sec + float(w.end), 3)

                # Validate timestamps without inventing artificial time
                if w_end_abs <= w_start_abs:
                    if seg_end_abs > w_start_abs:
                        w_end_abs = min(seg_end_abs, round(w_start_abs + 0.05, 3))
                    else:
                        continue

                w_start_abs = max(seg_start_abs, w_start_abs)
                w_end_abs = min(seg_end_abs, w_end_abs)
                if w_end_abs <= w_start_abs:
                    continue

                word_dict = {
                    "start": w_start_abs,
                    "end": w_end_abs,
                    "word": clean_text,
                }
                seg_words.append(word_dict)
                words_flat_out.append(word_dict)

        segments_out.append({
            "start": seg_start_abs,
            "end": seg_end_abs,
            "text": seg.text.strip(),
            "words": seg_words,
            "speaker": None,
        })

    return segments_out, words_flat_out


def _extract_keywords_and_tags(
    words: list[dict],
    options: dict,
    audio_events: list[dict],
    visual_events: list[dict],
    has_audio: bool = True,
) -> tuple[list[str], list[str]]:
    """Extract informative keywords and semantic tags from transcript and physical events."""
    word_counts: dict[str, int] = {}
    capitalized_counts: dict[str, int] = {}

    for w in words:
        raw = w.get("word", "").strip()
        cleaned = re.sub(r"[^\w\sáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", "", raw).strip()
        if len(cleaned) < 3:
            continue
        lower = cleaned.lower()
        if lower in STOPWORDS:
            continue

        word_counts[lower] = word_counts.get(lower, 0) + 1
        if cleaned[0].isupper():
            capitalized_counts[lower] = capitalized_counts.get(lower, 0) + 1

    # Score: frequency + bonus for proper nouns
    scored_terms: list[tuple[str, float]] = []
    for term, count in word_counts.items():
        score = count * (2.0 if capitalized_counts.get(term, 0) > 0 else 1.0)
        scored_terms.append((term, score))

    scored_terms.sort(key=lambda x: x[1], reverse=True)
    keywords = [t[0] for t in scored_terms[:15]]

    # Semantic tags
    tags: set[str] = set()
    genre = options.get("genre")
    if genre and genre != "Auto":
        tags.add(f"genero:{genre.lower()}")

    if not has_audio:
        tags.add("sem_audio")

    clip_model = options.get("clip_model")
    if clip_model and clip_model != "Auto":
        tags.add(f"modelo:{clip_model.lower()}")

    if any(ev.get("type") == "audio_energy_spike" for ev in audio_events):
        tags.add("audio_dinamico")

    if any(ev.get("type") == "multiple_faces" for ev in visual_events):
        tags.add("multiplos_sujeitos")
    elif any(ev.get("type") == "single_speaker_visual" for ev in visual_events):
        tags.add("talking_head")

    if any(ev.get("type") == "high_motion" for ev in visual_events):
        tags.add("alto_movimento")

    if len(words) > 50:
        tags.add("fala_continua")

    return keywords, sorted(list(tags))


def compute_kept_intervals(start: float, end: float, remove_ranges: list[dict]) -> list[tuple[float, float]]:
    """Compute remaining intervals [start, end] after cutting remove_ranges."""
    if end <= start:
        return []

    cleaned: list[tuple[float, float]] = []
    for r in sorted(remove_ranges, key=lambda x: float(x.get("start", 0) if isinstance(x, dict) else getattr(x, "start", 0))):
        rs = float(r.get("start", 0) if isinstance(r, dict) else getattr(r, "start", 0))
        re = float(r.get("end", 0) if isinstance(r, dict) else getattr(r, "end", 0))
        clamped_s = max(start, rs)
        clamped_e = min(end, re)
        if clamped_e > clamped_s:
            cleaned.append((clamped_s, clamped_e))

    # Merge overlapping remove ranges
    merged_removes: list[list[float]] = []
    for rs, re in cleaned:
        if not merged_removes or rs > merged_removes[-1][1]:
            merged_removes.append([rs, re])
        else:
            merged_removes[-1][1] = max(merged_removes[-1][1], re)

    # Compute kept intervals
    kept: list[tuple[float, float]] = []
    curr = start
    for rs, re in merged_removes:
        if rs > curr:
            kept.append((round(curr, 3), round(rs, 3)))
        curr = max(curr, re)
    if curr < end:
        kept.append((round(curr, 3), round(end, 3)))

    return kept


def remap_timestamp(t: float, kept: list[tuple[float, float]]) -> float | None:
    """Map original video timestamp to rendered output time, or None if cut out."""
    accum = 0.0
    for ks, ke in kept:
        if ks <= t <= ke:
            return round(accum + (t - ks), 3)
        elif t < ks:
            return None
        accum += (ke - ks)
    return None


def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cs."""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape_ass_text(text: str) -> str:
    """Escape text for ASS subtitles."""
    # Remove/replace control braces and slashes
    t = text.replace("\\", "/").replace("{", "(").replace("}", ")")
    return t.strip()


def generate_ass_subtitles(
    words: list[dict],
    kept_intervals: list[tuple[float, float]],
    out_path: Path,
    style_mode: str = "highlight",
    font_size: int = 48,
    position: str = "bottom",
    play_res_x: int = 1080,
    play_res_y: int = 1920,
) -> Path:
    """Generate an Advanced SubStation Alpha (.ass) subtitle file.

    Remaps word timestamps across kept intervals and formats lines with
    karaoke/active-word color highlight or clean classic subtitles.
    Ensures strictly monotonic word timestamps and safe screen margin.
    """
    # 1. Remap words to output time
    remapped_words: list[dict] = []
    for w in words:
        orig_s = float(w.get("start", 0) if isinstance(w, dict) else getattr(w, "start", 0))
        orig_e = float(w.get("end", 0) if isinstance(w, dict) else getattr(w, "end", 0))
        word_text = str(w.get("word", "") if isinstance(w, dict) else getattr(w, "word", "")).strip()
        if not word_text:
            continue

        mapped_s = remap_timestamp(orig_s, kept_intervals)
        mapped_e = remap_timestamp(orig_e, kept_intervals)
        if mapped_s is not None and mapped_e is not None and mapped_e > mapped_s:
            remapped_words.append({
                "start": mapped_s,
                "end": mapped_e,
                "word": word_text,
            })

    # Sort and guarantee strictly monotonic sequence
    remapped_words.sort(key=lambda x: x["start"])
    for i in range(1, len(remapped_words)):
        if remapped_words[i]["start"] < remapped_words[i - 1]["end"]:
            remapped_words[i]["start"] = remapped_words[i - 1]["end"]
        if remapped_words[i]["end"] <= remapped_words[i]["start"]:
            remapped_words[i]["end"] = round(remapped_words[i]["start"] + 0.05, 3)

    # Alignment and margins for position:
    # 2 = Bottom-Center, 5 = Middle-Center, 8 = Top-Center
    if position == "top":
        alignment = 8
        margin_v = 140
    elif position == "center":
        alignment = 5
        margin_v = 0
    else:  # bottom: 240px for 9:16 safe zone above TikTok/Reels/Shorts UI
        alignment = 2
        margin_v = 240 if play_res_y >= 1920 else 160

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,{alignment},40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events_lines: list[str] = []

    # Group remapped words into readable lines (3 to 5 words per line)
    lines: list[list[dict]] = []
    cur_line: list[dict] = []
    for w in remapped_words:
        if not cur_line:
            cur_line.append(w)
            continue
        prev = cur_line[-1]
        pause = w["start"] - prev["end"]
        ends_sentence = prev["word"].endswith((".", "!", "?", ":"))
        if len(cur_line) >= 5 or pause >= 0.5 or ends_sentence:
            lines.append(cur_line)
            cur_line = [w]
        else:
            cur_line.append(w)
    if cur_line:
        lines.append(cur_line)

    highlight_color = "&H0000FFFF&"  # Vibrant yellow accent in BGR hex
    normal_color = "&H00FFFFFF&"     # White in BGR hex

    for line_words in lines:
        if not line_words:
            continue
        line_start = line_words[0]["start"]
        line_end = line_words[-1]["end"]

        if style_mode == "classic":
            # Simple bold dialogue text for the line duration
            clean_text = " ".join(escape_ass_text(w["word"]) for w in line_words)
            s_time = format_ass_time(line_start)
            e_time = format_ass_time(line_end)
            events_lines.append(f"Dialogue: 0,{s_time},{e_time},Default,,0,0,0,,{clean_text}")
        else:
            # Word-level highlight style:
            # Each word in the line illuminates while it is spoken
            for idx, active_w in enumerate(line_words):
                w_s = format_ass_time(active_w["start"])
                w_e = format_ass_time(active_w["end"])

                # Build line with active word highlighted
                parts = []
                for j, w in enumerate(line_words):
                    escaped_w = escape_ass_text(w["word"])
                    if j == idx:
                        parts.append(f"{{\\c{highlight_color}}}{escaped_w}{{\\c{normal_color}}}")
                    else:
                        parts.append(escaped_w)
                line_str = " ".join(parts)
                events_lines.append(f"Dialogue: 0,{w_s},{w_e},Default,,0,0,0,,{line_str}")

                # If there's an audible pause before the next word, display unhighlighted text
                if idx + 1 < len(line_words):
                    next_s = line_words[idx + 1]["start"]
                    if next_s > active_w["end"] + 0.05:
                        pause_s = format_ass_time(active_w["end"])
                        pause_e = format_ass_time(next_s)
                        full_unhighlighted = " ".join(escape_ass_text(w["word"]) for w in line_words)
                        events_lines.append(f"Dialogue: 0,{pause_s},{pause_e},Default,,0,0,0,,{full_unhighlighted}")

    full_ass_content = header + "\n".join(events_lines) + "\n"
    out_path.write_text(full_ass_content, encoding="utf-8")
    return out_path


def render(
    path: Path,
    output: Path,
    candidate: dict,
    timeline: dict,
    options: dict,
    progress: Callable[[str, float], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Path:
    """Render final video clip for candidate with reframe, subtitles, and internal cutouts.

    Attempts hardware-accelerated VAAPI encoding on AMD/Intel devices. Falls back
    cleanly to CPU (libx264) on driver or pipeline errors without masking user cancellation.
    Enforces square pixels (setsar=1) across all format pipelines.
    """
    video_path = Path(path)
    if not video_path.exists():
        raise FileNotFoundError(f"Vídeo de entrada não encontrado: {video_path}")

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta = probe(video_path)
    src_w = meta.get("display_width", meta.get("width", 1920))
    src_h = meta.get("display_height", meta.get("height", 1080))
    sar_str = meta.get("sample_aspect_ratio") or "1:1"
    has_non_square_sar = sar_str not in ("1:1", "0:1", None, "")
    sar_norm_filter = "scale=trunc(iw*sar/2)*2:ih,setsar=1" if has_non_square_sar else ""

    # Read overrides: edit > candidate > options
    edit = candidate.get("edit") or {}

    clip_start = float(edit.get("start", candidate.get("start", 0.0)))
    clip_end = float(edit.get("end", candidate.get("end", clip_start + 30.0)))
    target_format = str(edit.get("format") or options.get("format", "9:16"))
    # Guarantee reframe and subtitles ON for generated cuts including legacy settings
    is_generated_cut = bool(
        candidate.get("id")
        or candidate.get("analysis_id")
        or candidate.get("score") is not None
        or options.get("is_generated")
    )
    if is_generated_cut:
        reframe_active = True
        subtitles_active = True
    else:
        reframe_active = bool(edit.get("reframe") if edit.get("reframe") is not None else True)
        subtitles_active = bool(edit.get("subtitles") if edit.get("subtitles") is not None else True)
    auto_zoom_active = bool(edit.get("auto_zoom") if edit.get("auto_zoom") is not None else True)
    zoom_level_val = float(edit.get("zoom_level", 1.25))

    sub_style = str(edit.get("subtitle_style") or options.get("subtitle_style", "highlight"))
    sub_size = int(edit.get("subtitle_size") or options.get("subtitle_size", 48))
    sub_pos = str(edit.get("subtitle_position") or options.get("subtitle_position", "bottom"))
    crop_x = edit.get("crop_x")
    if crop_x is not None:
        crop_x = float(crop_x)
    remove_ranges = edit.get("remove_ranges") or []
    words = edit.get("words") or candidate.get("words") or timeline.get("words") or []

    # Compute kept intervals
    kept_intervals = compute_kept_intervals(clip_start, clip_end, remove_ranges)
    if not kept_intervals:
        raise ValueError("O intervalo resultante após remoções é vazio.")

    total_output_duration = sum(k[1] - k[0] for k in kept_intervals)

    # Temporary directory for ASS file and intermediate scripts
    temp_dir = Path(tempfile.mkdtemp(prefix="localclip_render_"))

    try:
        if cancel and cancel():
            raise RuntimeError("Renderização cancelada pelo usuário.")
        if progress:
            progress("preparando_filtros", 0.10)

        # 1. Build reframe / format filter
        tracks = timeline.get("tracks", [])
        scenes = timeline.get("scenes", [])
        reframe_flt, is_split, layout_info = visual.build_reframe_filter(
            source_width=src_w,
            source_height=src_h,
            target_format=target_format,
            reframe=reframe_active,
            tracks=tracks,
            manual_crop_x=crop_x,
            start_time=clip_start,
            end_time=clip_end,
            kept_intervals=kept_intervals,
            auto_zoom=auto_zoom_active,
            zoom_level=zoom_level_val,
            scenes=scenes,
        )
        # 2. Build Subtitles if requested
        ass_filter_str = ""
        if subtitles_active and words:
            ass_path = temp_dir / "subs.ass"
            play_x = 1080 if target_format in ("9:16", "1:1") else 1920
            play_y = 1920 if target_format == "9:16" else (1080 if target_format == "1:1" else 1080)
            generate_ass_subtitles(
                words=words,
                kept_intervals=kept_intervals,
                out_path=ass_path,
                style_mode=sub_style,
                font_size=sub_size,
                position=sub_pos,
                play_res_x=play_x,
                play_res_y=play_y,
            )
            # Escape path for FFmpeg filtergraph
            escaped_ass = str(ass_path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
            ass_filter_str = f"ass='{escaped_ass}'"

        has_audio = bool(meta.get("has_audio", False))
        is_single_clean = (len(kept_intervals) == 1 and not remove_ranges)

        def _build_cmd(use_vaapi: bool) -> list[str]:
            cmd: list[str] = ["ffmpeg", "-nostdin", "-y"]
            if use_vaapi:
                cmd.extend(["-vaapi_device", _VAAPI_DEVICE])

            cmd.extend(["-protocol_whitelist", "file,pipe,crypto,data"])

            if is_single_clean:
                k_start, k_end = kept_intervals[0]
                cmd.extend(["-ss", f"{k_start:.3f}", "-to", f"{k_end:.3f}", "-i", str(video_path)])

                if is_split:
                    out_tail = ",format=nv12,hwupload[outv]" if use_vaapi else "[outv]"
                    prefix_flt = ""
                    if sar_norm_filter:
                        prefix_flt = f"[0:v]{sar_norm_filter}[v_norm];"
                        reframe_flt_applied = reframe_flt.replace("[0:v]", "[v_norm]", 1)
                    else:
                        reframe_flt_applied = reframe_flt
                    if ass_filter_str:
                        full_filter = f"{prefix_flt}{reframe_flt_applied};[reframe_v]{ass_filter_str},setsar=1{out_tail}"
                    else:
                        full_filter = f"{prefix_flt}{reframe_flt_applied};[reframe_v]setsar=1{out_tail}"
                    cmd.extend(["-filter_complex", full_filter, "-map", "[outv]"])
                    if has_audio:
                        cmd.extend(["-map", "0:a?"])
                else:
                    vf_parts = []
                    if sar_norm_filter:
                        vf_parts.append(sar_norm_filter)
                    vf_parts.append(reframe_flt)
                    if ass_filter_str:
                        vf_parts.append(ass_filter_str)
                    vf_parts.append("setsar=1")
                    if use_vaapi:
                        vf_parts.extend(["format=nv12", "hwupload"])
                    cmd.extend(["-vf", ",".join(vf_parts)])
            else:
                cmd.extend(["-i", str(video_path)])
                cond_parts = [f"gte(t,{ks:.6f})*lt(t,{ke:.6f})" for ks, ke in kept_intervals]
                select_cond = "+".join(cond_parts)
                # Preserve VFR timing; subtract only the source gaps, not frame count.
                offsets = [f"{kept_intervals[0][0]:.6f}"]
                for (_, previous_end), (next_start, _) in zip(kept_intervals, kept_intervals[1:]):
                    offsets.append(f"gte(T,{next_start:.6f})*{next_start - previous_end:.6f}")
                v_select = f"[0:v]select='{select_cond}',setpts='(T-({'+'.join(offsets)}))/TB'"
                if sar_norm_filter:
                    v_select += f",{sar_norm_filter}"

                out_tail = ",format=nv12,hwupload[outv]" if use_vaapi else "[outv]"

                if is_split:
                    pane_lx = layout_info.get("split_details", {}).get("left_x", 0.25)
                    pane_rx = layout_info.get("split_details", {}).get("right_x", 0.75)
                    full_filter = (
                        f"{v_select}[v_cut];"
                        f"[v_cut]split=2[v_top_in][v_bot_in];"
                        f"[v_top_in]crop=w='min(iw,ih*1.125)':h='ih':"
                        f"x='clip((iw*{pane_lx:.3f})-(ow/2),0,iw-ow)':y=0,scale=1080:960,setsar=1[v_top];"
                        f"[v_bot_in]crop=w='min(iw,ih*1.125)':h='ih':"
                        f"x='clip((iw*{pane_rx:.3f})-(ow/2),0,iw-ow)':y=0,scale=1080:960,setsar=1[v_bot];"
                        f"[v_top][v_bot]vstack=inputs=2,setsar=1[v_stacked];"
                    )
                    if ass_filter_str:
                        full_filter += f"[v_stacked]{ass_filter_str},setsar=1{out_tail}"
                    else:
                        full_filter += f"[v_stacked]setsar=1{out_tail}"
                else:
                    vf_cut = f"{v_select},{reframe_flt}"
                    if ass_filter_str:
                        vf_cut += f",{ass_filter_str}"
                    vf_cut += f",setsar=1{out_tail}"
                    full_filter = vf_cut

                if has_audio:
                    a_select = f"[0:a]aselect='{select_cond}',asetpts=N/SR/TB[outa]"
                    full_filter += f";{a_select}"
                    cmd.extend(["-filter_complex", full_filter, "-map", "[outv]", "-map", "[outa]", "-shortest"])
                else:
                    cmd.extend(["-filter_complex", full_filter, "-map", "[outv]"])

            # Codec settings
            if use_vaapi:
                cmd.extend(["-c:v", "h264_vaapi", "-b:v", "4M"])
            else:
                cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p"])

            if has_audio:
                cmd.extend(["-c:a", "aac", "-b:a", "192k"])
            else:
                cmd.append("-an")

            cmd.extend(["-movflags", "+faststart", str(out_path)])
            return cmd

        def _execute_ffmpeg(cmd: list[str]) -> None:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid,
            )

            time_regex = re.compile(r"time=([0-9:.]+)")
            stderr_lines: list[str] = []

            try:
                assert proc.stderr is not None
                for line in proc.stderr:
                    stderr_lines.append(line)
                    if cancel and cancel():
                        _kill_process_group(proc)
                        if out_path.exists():
                            out_path.unlink(missing_ok=True)
                        raise RuntimeError("Renderização cancelada pelo usuário.")

                    match = time_regex.search(line)
                    if match and progress and total_output_duration > 0:
                        parts = match.group(1).split(":")
                        if len(parts) == 3:
                            try:
                                elapsed = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                                pct = min(0.98, max(0.20, 0.20 + 0.78 * (elapsed / total_output_duration)))
                                progress("renderizando", round(pct, 2))
                            except ValueError:
                                pass

                proc.wait(timeout=240.0)
                if proc.returncode != 0:
                    if out_path.exists():
                        out_path.unlink(missing_ok=True)
                    err_msg = "".join(stderr_lines[-15:]).strip()
                    raise RuntimeError(f"FFmpeg render falhou com código {proc.returncode}: {err_msg}")

            except subprocess.TimeoutExpired:
                _kill_process_group(proc)
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                raise RuntimeError("Timeout na renderização FFmpeg.")
            except BaseException:
                _kill_process_group(proc)
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                raise

        # Check VAAPI hardware acceleration
        vaapi_available = is_vaapi_supported()
        if vaapi_available:
            try:
                logger.info("Iniciando renderização com aceleração por hardware VAAPI (%s)...", _VAAPI_DEVICE)
                cmd_vaapi = _build_cmd(use_vaapi=True)
                _execute_ffmpeg(cmd_vaapi)
            except RuntimeError as re_err:
                # If user cancelled, do not fallback
                if (cancel and cancel()) or "cancelada" in str(re_err).lower() or "cancel" in str(re_err).lower():
                    raise
                logger.warning("Renderização VAAPI falhou (%s). Executando fallback automático para CPU (libx264)...", re_err)
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                cmd_cpu = _build_cmd(use_vaapi=False)
                _execute_ffmpeg(cmd_cpu)
        else:
            logger.info("Renderização em CPU (libx264)...")
            cmd_cpu = _build_cmd(use_vaapi=False)
            _execute_ffmpeg(cmd_cpu)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("Falha na renderização: arquivo de saída não foi gerado.")

    if progress:
        progress("render_concluido", 1.0)

    logger.info("Render completed successfully: %s (%d bytes)", out_path, out_path.stat().st_size)
    return out_path


def ensure_preview(
    path: Path,
    output: Path,
    progress: Callable[[str, float], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Path:
    """Ensure a video file is formatted as a browser-playable MP4 (H.264 / AAC with faststart).

    If the input is already an MP4 with H.264 and AAC, remuxes quickly or copies.
    If input uses incompatible container or codecs (MKV, MOV, ProRes, VP9, HEVC, AV1),
    transcodes to a lightweight 720p H.264 proxy with square pixels (setsar=1).
    Supports cancellation and progress callback.
    """
    in_path = Path(path)
    if not in_path.exists():
        raise FileNotFoundError(f"Arquivo de origem para preview não encontrado: {in_path}")

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta = probe(in_path)
    v_codec = (meta.get("codec") or "").lower()
    a_codec = (meta.get("audio_codec") or "").lower()
    ext = in_path.suffix.lower()

    sar = meta.get("sample_aspect_ratio")
    is_square_sar = sar in ("1:1", "0:1", None, "")
    rotation = meta.get("rotation", 0)

    # Browser-compatible check: MP4 container with h264/avc1 and aac (or no audio) with square pixels and no rotation
    is_browser_native = (
        ext in (".mp4", ".m4v")
        and v_codec in ("h264", "avc1")
        and (a_codec in ("aac", "mp4a") or not meta.get("has_audio"))
        and is_square_sar
        and rotation == 0
    )

    if is_browser_native and meta.get("width", 0) <= 1920:
        if progress:
            progress("remuxando_preview", 0.5)
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-protocol_whitelist", "file,pipe,crypto,data",
            "-i", str(in_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ]
    else:
        if progress:
            progress("transcodificando_preview", 0.1)
        # 720p proxy with square pixels preserving displayed aspect ratio
        vf_preview_parts = []
        if not is_square_sar:
            vf_preview_parts.append("scale=trunc(iw*sar/2)*2:ih,setsar=1")
        vf_preview_parts.append("scale='min(1280,iw)':-2")
        vf_preview_parts.append("setsar=1")
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-protocol_whitelist", "file,pipe,crypto,data",
            "-i", str(in_path),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-vf", ",".join(vf_preview_parts),
            "-pix_fmt", "yuv420p",
        ]
        if meta.get("has_audio"):
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            cmd.append("-an")
        cmd.extend([
            "-movflags", "+faststart",
            str(out_path),
        ])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=os.setsid,
    )

    total_dur = meta.get("duration", 0.0)
    time_regex = re.compile(r"time=([0-9:.]+)")
    stderr_lines: list[str] = []
    try:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_lines.append(line)
            if cancel and cancel():
                _kill_process_group(proc)
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                raise RuntimeError("Geração de preview cancelada pelo usuário.")

            match = time_regex.search(line)
            if match and progress and total_dur > 0:
                parts = match.group(1).split(":")
                if len(parts) == 3:
                    try:
                        elapsed = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                        pct = min(0.98, max(0.10, elapsed / total_dur))
                        progress("gerando_preview", round(pct, 2))
                    except ValueError:
                        pass

        proc.wait(timeout=180.0)
        if proc.returncode != 0:
            if out_path.exists():
                out_path.unlink(missing_ok=True)
            err_msg = "".join(stderr_lines[-15:]).strip()
            raise RuntimeError(f"Falha ao gerar preview: {err_msg}")

    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        if out_path.exists():
            out_path.unlink(missing_ok=True)
        raise RuntimeError("Timeout ao gerar preview.")
    except BaseException:
        _kill_process_group(proc)
        if out_path.exists():
            out_path.unlink(missing_ok=True)
        raise

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("Arquivo de preview gerado está vazio ou inexistente.")

    # Guarantee persistent project thumbnail exists at project_dir / 'thumbnail.jpg'
    thumb_path = out_path.parent / "thumbnail.jpg"
    if not thumb_path.is_file() or thumb_path.stat().st_size == 0:
        try:
            visual.extract_representative_thumbnail(out_path, thumb_path)
        except Exception as e:
            logger.warning("Falha ao gerar thumbnail representativa em ensure_preview: %s", e)

    if progress:
        progress("preview_concluido", 1.0)

    return out_path
