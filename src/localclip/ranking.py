"""Local-first candidate generation and explainable potential ranking engine.

Implements natural boundary detection, structured criteria matching,
hybrid deterministic + semantic scoring, explicit penalties, genre/platform/model
weight matrix adaptations, timeline evidence extraction, and edit structure generation.
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from localclip import providers as providers_module


# ---------------------------------------------------------------------------
# Constants: Punctuation and Linguistic Patterns (Portuguese focus)
# ---------------------------------------------------------------------------

TERMINAL_PUNCTUATION = (".", "!", "?", "…")
CLAUSE_PUNCTUATION = (",", ";", ":", "—", "-")

DANGLING_OPENERS = {
    "e", "mas", "porém", "contudo", "todavia", "entretanto", "então",
    "porque", "porquê", "pois", "aí", "daí", "quando", "já", "onde",
    "como", "que", "se", "ou", "caso", "enquanto"
}

DANGLING_CLOSERS = {
    "e", "mas", "porém", "contudo", "porque", "porquê", "pois", "então",
    "quando", "se", "que", "como", "ou", "já", "onde", "para", "com",
    "de", "em", "por", "sobre", "até", "sem", "ou seja", "quer dizer"
}

HOOK_TRIGGER_WORDS = {
    "como", "por que", "porque", "qual", "quais", "quem", "quando", "onde",
    "segredo", "nunca", "sempre", "ninguém", "todos", "olha", "veja", "descubra",
    "cuidado", "erro", "maior", "melhor", "pior", "primeiro", "incrível",
    "inacreditável", "verdade", "mentira", "fato", "segredo", "você", "sabia"
}

EMOTION_TRIGGER_WORDS = {
    "incrível", "absurdo", "demais", "nossa", "meu deus", "loucura",
    "sensacional", "maravilhoso", "chocante", "ridículo", "engraçado",
    "hilário", "medo", "raiva", "alegria", "surpresa", "bizarro"
}


# ---------------------------------------------------------------------------
# Genre Weights Matrix (All 27 genres from schemas.py)
# 9 dimensions: hook, flow, value, platform_fit, narrative, emotion, audio, visual, shareability
# ---------------------------------------------------------------------------

GENRE_WEIGHTS: dict[str, dict[str, float]] = {
    "Auto": {
        "hook": 0.16, "flow": 0.12, "value": 0.14, "platform_fit": 0.10,
        "narrative": 0.14, "emotion": 0.12, "audio": 0.08, "visual": 0.08,
        "shareability": 0.06
    },
    "Podcast": {
        "hook": 0.14, "flow": 0.16, "value": 0.16, "platform_fit": 0.10,
        "narrative": 0.16, "emotion": 0.10, "audio": 0.08, "visual": 0.04,
        "shareability": 0.06
    },
    "Lifestyle": {
        "hook": 0.15, "flow": 0.12, "value": 0.12, "platform_fit": 0.11,
        "narrative": 0.12, "emotion": 0.13, "audio": 0.07, "visual": 0.10,
        "shareability": 0.08
    },
    "Vlog": {
        "hook": 0.16, "flow": 0.13, "value": 0.10, "platform_fit": 0.10,
        "narrative": 0.14, "emotion": 0.14, "audio": 0.07, "visual": 0.09,
        "shareability": 0.07
    },
    "Viagem": {
        "hook": 0.15, "flow": 0.10, "value": 0.10, "platform_fit": 0.10,
        "narrative": 0.11, "emotion": 0.14, "audio": 0.08, "visual": 0.15,
        "shareability": 0.07
    },
    "Comida": {
        "hook": 0.17, "flow": 0.11, "value": 0.13, "platform_fit": 0.10,
        "narrative": 0.11, "emotion": 0.12, "audio": 0.08, "visual": 0.12,
        "shareability": 0.06
    },
    "Beleza": {
        "hook": 0.16, "flow": 0.12, "value": 0.13, "platform_fit": 0.10,
        "narrative": 0.12, "emotion": 0.11, "audio": 0.06, "visual": 0.13,
        "shareability": 0.07
    },
    "Fitness": {
        "hook": 0.16, "flow": 0.11, "value": 0.14, "platform_fit": 0.10,
        "narrative": 0.11, "emotion": 0.14, "audio": 0.08, "visual": 0.10,
        "shareability": 0.06
    },
    "Esportes": {
        "hook": 0.19, "flow": 0.07, "value": 0.06, "platform_fit": 0.10,
        "narrative": 0.08, "emotion": 0.18, "audio": 0.12, "visual": 0.14,
        "shareability": 0.06
    },
    "Futebol": {
        "hook": 0.20, "flow": 0.06, "value": 0.06, "platform_fit": 0.10,
        "narrative": 0.08, "emotion": 0.18, "audio": 0.14, "visual": 0.12,
        "shareability": 0.06
    },
    "Basquete": {
        "hook": 0.20, "flow": 0.06, "value": 0.06, "platform_fit": 0.10,
        "narrative": 0.08, "emotion": 0.18, "audio": 0.13, "visual": 0.13,
        "shareability": 0.06
    },
    "Marketing": {
        "hook": 0.18, "flow": 0.13, "value": 0.18, "platform_fit": 0.10,
        "narrative": 0.13, "emotion": 0.09, "audio": 0.05, "visual": 0.06,
        "shareability": 0.08
    },
    "Talking Head": {
        "hook": 0.18, "flow": 0.15, "value": 0.15, "platform_fit": 0.10,
        "narrative": 0.15, "emotion": 0.12, "audio": 0.05, "visual": 0.04,
        "shareability": 0.06
    },
    "Discurso": {
        "hook": 0.16, "flow": 0.14, "value": 0.15, "platform_fit": 0.10,
        "narrative": 0.16, "emotion": 0.16, "audio": 0.05, "visual": 0.03,
        "shareability": 0.05
    },
    "Comentário": {
        "hook": 0.17, "flow": 0.14, "value": 0.16, "platform_fit": 0.10,
        "narrative": 0.14, "emotion": 0.12, "audio": 0.06, "visual": 0.05,
        "shareability": 0.06
    },
    "Entrevista": {
        "hook": 0.15, "flow": 0.15, "value": 0.16, "platform_fit": 0.10,
        "narrative": 0.16, "emotion": 0.11, "audio": 0.07, "visual": 0.04,
        "shareability": 0.06
    },
    "Entretenimento": {
        "hook": 0.18, "flow": 0.10, "value": 0.09, "platform_fit": 0.10,
        "narrative": 0.11, "emotion": 0.17, "audio": 0.11, "visual": 0.08,
        "shareability": 0.06
    },
    "Filmes": {
        "hook": 0.16, "flow": 0.11, "value": 0.10, "platform_fit": 0.10,
        "narrative": 0.14, "emotion": 0.16, "audio": 0.10, "visual": 0.07,
        "shareability": 0.06
    },
    "Reality": {
        "hook": 0.19, "flow": 0.10, "value": 0.07, "platform_fit": 0.10,
        "narrative": 0.12, "emotion": 0.19, "audio": 0.09, "visual": 0.07,
        "shareability": 0.07
    },
    "Notícias": {
        "hook": 0.18, "flow": 0.14, "value": 0.20, "platform_fit": 0.10,
        "narrative": 0.15, "emotion": 0.08, "audio": 0.05, "visual": 0.05,
        "shareability": 0.05
    },
    "Educacional": {
        "hook": 0.14, "flow": 0.15, "value": 0.24, "platform_fit": 0.10,
        "narrative": 0.16, "emotion": 0.06, "audio": 0.04, "visual": 0.04,
        "shareability": 0.07
    },
    "Produtos": {
        "hook": 0.17, "flow": 0.13, "value": 0.18, "platform_fit": 0.10,
        "narrative": 0.13, "emotion": 0.09, "audio": 0.06, "visual": 0.08,
        "shareability": 0.06
    },
    "História": {
        "hook": 0.14, "flow": 0.15, "value": 0.22, "platform_fit": 0.10,
        "narrative": 0.18, "emotion": 0.08, "audio": 0.04, "visual": 0.04,
        "shareability": 0.05
    },
    "Ciência e tecnologia": {
        "hook": 0.15, "flow": 0.15, "value": 0.23, "platform_fit": 0.10,
        "narrative": 0.15, "emotion": 0.07, "audio": 0.04, "visual": 0.05,
        "shareability": 0.06
    },
    "Música": {
        "hook": 0.16, "flow": 0.11, "value": 0.06, "platform_fit": 0.10,
        "narrative": 0.06, "emotion": 0.18, "audio": 0.22, "visual": 0.05,
        "shareability": 0.06
    },
    "Games": {
        "hook": 0.18, "flow": 0.09, "value": 0.08, "platform_fit": 0.10,
        "narrative": 0.09, "emotion": 0.18, "audio": 0.13, "visual": 0.09,
        "shareability": 0.06
    },
    "Outros": {
        "hook": 0.16, "flow": 0.12, "value": 0.14, "platform_fit": 0.10,
        "narrative": 0.14, "emotion": 0.12, "audio": 0.08, "visual": 0.08,
        "shareability": 0.06
    },
}


# ---------------------------------------------------------------------------
# Platform and Duration Parameters
# ---------------------------------------------------------------------------

PLATFORM_PARAMS: dict[str, dict[str, Any]] = {
    "TikTok": {
        "ideal_duration": 28.0,
        "duration_sigma": 12.0,
        "max_duration": 60.0,
        "hook_mult": 1.20,
        "emotion_mult": 1.15,
        "flow_mult": 0.95,
        "value_mult": 0.95,
        "visual_mult": 1.05,
        "shareability_mult": 1.05,
    },
    "YouTube Shorts": {
        "ideal_duration": 45.0,
        "duration_sigma": 25.0,
        "max_duration": 180.0,  # Official 3-minute limit for YouTube Shorts
        "hook_mult": 1.05,
        "emotion_mult": 0.95,
        "flow_mult": 1.05,
        "value_mult": 1.15,
        "visual_mult": 0.95,
        "shareability_mult": 1.05,
    },
    "Instagram Reels": {
        "ideal_duration": 32.0,
        "duration_sigma": 14.0,
        "max_duration": 90.0,
        "hook_mult": 1.10,
        "emotion_mult": 1.05,
        "flow_mult": 1.00,
        "value_mult": 0.95,
        "visual_mult": 1.15,
        "shareability_mult": 1.20,
    },
}

DURATION_TARGETS: dict[str, tuple[float, float, float]] = {
    # label: (min_duration, target_duration, max_duration)
    "Auto": (20.0, 40.0, 75.0),
    "<30s": (12.0, 22.0, 29.5),
    "30s–59s": (28.0, 42.0, 59.5),
    "60s–89s": (58.0, 72.0, 89.5),
    "90s–3min": (85.0, 130.0, 180.0),
    "3min–5min": (170.0, 240.0, 300.0),
    "5min–10min": (280.0, 420.0, 600.0),
}


# ---------------------------------------------------------------------------
# Helper Data Structures
# ---------------------------------------------------------------------------

class Sentence:
    __slots__ = (
        "start", "end", "text", "words", "has_terminal_punct",
        "starts_with_conjunction", "ends_with_conjunction",
        "has_question", "has_exclamation"
    )

    def __init__(
        self,
        start: float,
        end: float,
        text: str,
        words: list[dict],
        has_terminal_punct: bool,
        starts_with_conjunction: bool,
        ends_with_conjunction: bool,
        has_question: bool,
        has_exclamation: bool,
    ):
        self.start = start
        self.end = end
        self.text = text
        self.words = words
        self.has_terminal_punct = has_terminal_punct
        self.starts_with_conjunction = starts_with_conjunction
        self.ends_with_conjunction = ends_with_conjunction
        self.has_question = has_question
        self.has_exclamation = has_exclamation


# ---------------------------------------------------------------------------
# Natural Boundary Extraction
# ---------------------------------------------------------------------------

def _clean_word_token(word: str) -> str:
    return re.sub(r"[^\wáàâãéèêíïóôõöúçñÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ]", "", word).lower()
PORTUGUESE_STOPWORDS = {
    "a", "ao", "aos", "aquela", "aquelas", "aquele", "aqueles", "aquilo", "as", "até",
    "com", "como", "da", "das", "de", "dela", "delas", "dele", "deles", "depois",
    "do", "dos", "e", "é", "ela", "elas", "ele", "eles", "em", "entre", "era", "eram",
    "essa", "essas", "esse", "esses", "esta", "estas", "este", "estes", "eu", "foi",
    "fomos", "foram", "já", "lhe", "lhes", "mais", "mas", "me", "mesmo", "meu", "meus",
    "minha", "minhas", "muito", "na", "nas", "não", "no", "nos", "nós", "nossa",
    "nossas", "nosso", "nossos", "num", "numa", "o", "os", "ou", "para", "pela", "pelas",
    "pelo", "pelos", "por", "qual", "quando", "que", "quem", "se", "seja", "sem", "ser",
    "será", "seu", "seus", "só", "sua", "suas", "também", "te", "tem", "têm", "temos",
    "tenho", "ter", "teu", "teus", "tinha", "tinham", "tu", "tua", "tuas", "um", "uma",
    "você", "vocês", "vos", "sobre", "pra", "pro", "vai", "vou", "aí", "aqui", "ali",
}


def _semantic_tokens(candidate: dict) -> set[str]:
    """Extract cleaned non-stopword tokens from candidate text or words."""
    text = str(candidate.get("text") or candidate.get("summary") or "")
    if not text and candidate.get("words"):
        text = " ".join(str(w.get("word", "")) for w in candidate["words"] if isinstance(w, dict))
    raw_tokens = text.split()
    cleaned = {_clean_word_token(t) for t in raw_tokens}
    return {t for t in cleaned if len(t) > 2 and t not in PORTUGUESE_STOPWORDS}


def _semantic_similarity(a: dict, b: dict) -> float:
    """Compute semantic text overlap (Jaccard on content words) between two candidates."""
    tokens_a = _semantic_tokens(a)
    tokens_b = _semantic_tokens(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def parse_sentences_from_timeline(timeline: dict) -> list[Sentence]:
    """Parse discrete sentence units using word timestamps, punctuation, and pauses."""
    words = list(timeline.get("words", []))
    if not words:
        # Fallback to segments' words if top-level words is empty
        for seg in timeline.get("segments", []):
            words.extend(seg.get("words", []))

    if not words:
        # If no words at all, create synthetic sentences from segments or return empty
        sentences = []
        for seg in timeline.get("segments", []):
            s_start = float(seg.get("start", 0))
            s_end = float(seg.get("end", s_start + 1.0))
            txt = str(seg.get("text", "")).strip()
            if s_end > s_start:
                sentences.append(
                    Sentence(
                        start=s_start,
                        end=s_end,
                        text=txt,
                        words=[],
                        has_terminal_punct=txt.endswith(TERMINAL_PUNCTUATION),
                        starts_with_conjunction=False,
                        ends_with_conjunction=False,
                        has_question="?" in txt,
                        has_exclamation="!" in txt,
                    )
                )
        return sentences

    # Ensure words are sorted by start time
    sorted_words = sorted(words, key=lambda w: float(w.get("start", 0)))

    sentences: list[Sentence] = []
    curr_words: list[dict] = []

    for i, w in enumerate(sorted_words):
        curr_words.append(w)
        raw_word = str(w.get("word", "")).strip()

        # Check terminal punctuation at end of word
        ends_terminal = any(raw_word.endswith(p) for p in TERMINAL_PUNCTUATION)

        # Check pause to next word
        pause_to_next = 0.0
        if i + 1 < len(sorted_words):
            next_start = float(sorted_words[i + 1].get("start", 0))
            curr_end = float(w.get("end", next_start))
            pause_to_next = max(0.0, next_start - curr_end)

        is_last = (i == len(sorted_words) - 1)
        split_sentence = ends_terminal or (pause_to_next >= 0.55 and len(curr_words) >= 3) or is_last

        if split_sentence and curr_words:
            sent_start = float(curr_words[0].get("start", 0))
            sent_end = float(curr_words[-1].get("end", sent_start + 0.1))
            sent_text = " ".join(str(item.get("word", "")).strip() for item in curr_words)

            first_clean = _clean_word_token(str(curr_words[0].get("word", "")))
            last_clean = _clean_word_token(str(curr_words[-1].get("word", "")))

            sentences.append(
                Sentence(
                    start=sent_start,
                    end=sent_end,
                    text=sent_text,
                    words=list(curr_words),
                    has_terminal_punct=ends_terminal,
                    starts_with_conjunction=first_clean in DANGLING_OPENERS,
                    ends_with_conjunction=last_clean in DANGLING_CLOSERS,
                    has_question="?" in sent_text,
                    has_exclamation="!" in sent_text,
                )
            )
            curr_words = []

    return sentences


def snap_boundaries(
    start: float,
    end: float,
    timeline: dict,
    min_bound: float,
    max_bound: float,
    first_word_start: float | None = None,
    last_word_end: float | None = None,
) -> tuple[float, float]:
    """Snap start/end boundaries to scene cuts without cutting into included speech."""
    scenes = timeline.get("scenes", [])

    snapped_start = start
    snapped_end = end

    # Snap start to nearby scene cut if within 0.40s BEFORE or AT speech start,
    # but NEVER move start after the first word start (which would truncate the word)!
    for sc in scenes:
        sc_start = float(sc.get("start", -1))
        if abs(sc_start - start) <= 0.40 and sc_start >= min_bound:
            if first_word_start is None or sc_start <= first_word_start:
                snapped_start = sc_start
                break

    # Snap end to nearby scene cut if within 0.45s AFTER or AT speech end,
    # but NEVER move end before the last word end (which would truncate the word)!
    for sc in scenes:
        sc_end = float(sc.get("end", -1))
        if abs(sc_end - end) <= 0.45 and sc_end <= max_bound:
            if last_word_end is None or sc_end >= last_word_end:
                snapped_end = sc_end
                break

    # Inviolable invariants: never move start beyond first word or end before last word
    if first_word_start is not None:
        snapped_start = min(snapped_start, first_word_start)
    if last_word_end is not None:
        snapped_end = max(snapped_end, last_word_end)

    snapped_start = max(min_bound, snapped_start)
    snapped_end = min(max_bound, snapped_end)

    if snapped_end <= snapped_start:
        snapped_end = min(max_bound, snapped_start + 1.0)

    return round(snapped_start, 2), round(snapped_end, 2)

# ---------------------------------------------------------------------------
# Candidate Window Generation
# ---------------------------------------------------------------------------

def _temporal_iou(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    intersection = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    union = max(a_end, b_end) - min(a_start, b_start)
    return intersection / union if union > 0 else 0.0


def _temporal_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> tuple[float, float]:
    """Calculates temporal IoU and containment ratio (intersection / min(dur_a, dur_b))."""
    intersection = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    if intersection <= 0.0:
        return 0.0, 0.0
    union = max(a_end, b_end) - min(a_start, b_start)
    iou = intersection / union if union > 0.0 else 0.0
    dur_a = max(0.001, a_end - a_start)
    dur_b = max(0.001, b_end - b_start)
    containment = intersection / min(dur_a, dur_b)
    return iou, containment

def resolve_duration_targets(
    options: dict,
    source_duration: float,
) -> list[tuple[float, float, float, str]]:
    """Resolve (min_dur, target_dur, max_dur, label) tuples for each requested duration."""
    raw_durations = options.get("durations")
    if not raw_durations:
        single = options.get("duration", "Auto")
        dur_list = [single] if single else ["Auto"]
    elif isinstance(raw_durations, str):
        dur_list = [raw_durations]
    else:
        dur_list = list(raw_durations)

    if not dur_list:
        dur_list = ["Auto"]

    platform = options.get("platform", "TikTok")
    plat_info = PLATFORM_PARAMS.get(platform, PLATFORM_PARAMS["TikTok"])

    targets: list[tuple[float, float, float, str]] = []
    for dur_opt in dur_list:
        if dur_opt == "personalizada":
            c_min = float(options.get("custom_min", 15.0))
            c_max = float(options.get("custom_max", 60.0))
            if c_max < c_min:
                c_max = c_min
            min_dur = c_min
            target_dur = (c_min + c_max) / 2.0
            max_dur = c_max
        else:
            min_dur, target_dur, max_dur = DURATION_TARGETS.get(dur_opt, DURATION_TARGETS["Auto"])

        if dur_opt == "Auto":
            target_dur = plat_info["ideal_duration"]
            max_dur = min(max_dur, plat_info["max_duration"])

        # Adapt if source video is shorter than default target
        if source_duration < min_dur:
            min_dur = max(3.0, source_duration * 0.4)
            target_dur = source_duration * 0.8
            max_dur = source_duration

        targets.append((min_dur, target_dur, max_dur, dur_opt))

    return targets


def generate_candidate_windows(
    timeline: dict,
    options: dict,
    criteria: dict,
) -> list[dict]:
    """Generate natural boundary candidate windows spanning the timeline across requested durations."""
    t_start = float(options.get("start") or timeline.get("start") or 0.0)
    t_end = options.get("end")
    if t_end is not None:
        t_end = float(t_end)
    else:
        t_end = float(timeline.get("end") or 0.0)

    if t_end <= t_start:
        t_end = t_start + 60.0

    source_duration = t_end - t_start

    targets = resolve_duration_targets(options, source_duration)
    global_min_dur = min(t[0] for t in targets)
    global_max_dur = max(t[2] for t in targets)

    sentences = parse_sentences_from_timeline(timeline)
    raw_proposals: list[dict] = []

    # Strategy 1: Sentence-anchored multi-scale forward accumulation across requested targets
    if sentences:
        for i, s_start_sent in enumerate(sentences):
            if s_start_sent.start < t_start or s_start_sent.start >= t_end:
                continue

            curr_text_parts = []
            curr_words = []

            for j in range(i, len(sentences)):
                s_curr = sentences[j]
                if s_curr.end > t_end + 0.5:
                    break

                curr_text_parts.append(s_curr.text)
                curr_words.extend(s_curr.words)

                span_duration = s_curr.end - s_start_sent.start

                # Test against each duration target
                for t_min, t_target, t_max, t_label in targets:
                    if span_duration >= t_min * 0.90:
                        is_clean_conclusion = s_curr.has_terminal_punct and not s_curr.ends_with_conjunction
                        is_at_max = span_duration >= t_max

                        if (is_clean_conclusion or is_at_max) and span_duration <= t_max * 1.10:
                            raw_proposals.append({
                                "start": s_start_sent.start,
                                "end": s_curr.end,
                                "sentences": sentences[i : j + 1],
                                "words": list(curr_words),
                                "text": " ".join(curr_text_parts),
                                "justified_deviation": span_duration > t_max,
                                "anchor_type": "sentence_progression",
                                "target_dur": t_target,
                                "duration_bucket": t_label,
                            })

                if span_duration > global_max_dur * 1.15:
                    break

    # Strategy 2: High Interest Anchors (Audio events, Visual events, Keywords)
    audio_events = timeline.get("audio_events", [])
    visual_events = timeline.get("visual_events", [])
    req_keywords = set(criteria.get("keywords", []))

    anchor_moments: list[float] = []
    for ae in audio_events:
        ae_type = str(ae.get("type", "")).lower()
        if any(k in ae_type for k in ("laugh", "applause", "cheer", "shout", "riso")):
            anchor_moments.append(float(ae.get("start", 0)))

    for ve in visual_events:
        if float(ve.get("confidence", 0)) >= 0.7:
            anchor_moments.append(float(ve.get("start", 0)))

    # Window around anchor moments across targets
    if sentences:
        for a_time in anchor_moments:
            if not (t_start <= a_time <= t_end):
                continue
            closest_idx = min(
                range(len(sentences)),
                key=lambda idx: abs(sentences[idx].start - a_time),
            )
            start_idx = max(0, closest_idx - 1)
            while start_idx > 0 and sentences[start_idx].starts_with_conjunction:
                start_idx -= 1

            for t_min, t_target, t_max, t_label in targets:
                for end_idx in range(closest_idx, min(len(sentences), closest_idx + 8)):
                    span_dur = sentences[end_idx].end - sentences[start_idx].start
                    if t_min * 0.85 <= span_dur <= t_max * 1.05:
                        if sentences[end_idx].has_terminal_punct:
                            all_words = []
                            all_text = []
                            for s_item in sentences[start_idx : end_idx + 1]:
                                all_words.extend(s_item.words)
                                all_text.append(s_item.text)
                            raw_proposals.append({
                                "start": sentences[start_idx].start,
                                "end": sentences[end_idx].end,
                                "sentences": sentences[start_idx : end_idx + 1],
                                "words": all_words,
                                "text": " ".join(all_text),
                                "justified_deviation": False,
                                "anchor_type": "event_anchor",
                                "target_dur": t_target,
                                "duration_bucket": t_label,
                            })
                            break

    # Strategy 3: Multimodal Scene-based Fallback (if no or very few proposals from speech)
    if len(raw_proposals) < 3:
        scenes = timeline.get("scenes", [])
        if scenes:
            for i, sc in enumerate(scenes):
                sc_s = float(sc.get("start", 0))
                if sc_s < t_start or sc_s >= t_end:
                    continue
                for j in range(i, len(scenes)):
                    sc_e = float(scenes[j].get("end", sc_s + 5.0))
                    sc_dur = sc_e - sc_s
                    for t_min, t_target, t_max, t_label in targets:
                        if t_min * 0.8 <= sc_dur <= t_max * 1.05:
                            w_sub = [
                                w for w in timeline.get("words", [])
                                if float(w.get("start", 0)) >= sc_s and float(w.get("end", 0)) <= sc_e
                            ]
                            raw_proposals.append({
                                "start": sc_s,
                                "end": sc_e,
                                "sentences": [],
                                "words": w_sub,
                                "text": " ".join(str(w.get("word", "")).strip() for w in w_sub),
                                "justified_deviation": False,
                                "anchor_type": "scene_cut",
                                "target_dur": t_target,
                                "duration_bucket": t_label,
                            })
                            if sc_dur >= t_target:
                                break

    # Strategy 4: Unbroken natural interval if no multi-sentence window matched
    if not raw_proposals:
        if sentences:
            all_s_words = []
            all_s_text = []
            for s in sentences:
                all_s_words.extend(s.words)
                all_s_text.append(s.text)
            raw_proposals.append({
                "start": sentences[0].start,
                "end": sentences[-1].end,
                "sentences": sentences,
                "words": all_s_words,
                "text": " ".join(all_s_text),
                "justified_deviation": True,
                "anchor_type": "complete_utterance",
                "target_dur": targets[0][1],
                "duration_bucket": targets[0][3],
            })
        else:
            w_sub = [
                w for w in timeline.get("words", [])
                if float(w.get("start", 0)) >= t_start and float(w.get("end", 0)) <= t_end
            ]
            raw_proposals.append({
                "start": t_start,
                "end": t_end,
                "sentences": [],
                "words": w_sub,
                "text": " ".join(str(w.get("word", "")).strip() for w in w_sub),
                "justified_deviation": True,
                "anchor_type": "full_interval",
                "target_dur": targets[0][1],
                "duration_bucket": targets[0][3],
            })

    # Boundary snapping & quality pre-scoring
    processed_candidates: list[dict] = []
    for prop in raw_proposals:
        prop_words = prop.get("words", [])
        f_word_start = float(prop_words[0].get("start")) if prop_words else None
        l_word_end = float(prop_words[-1].get("end")) if prop_words else None

        snapped_s, snapped_e = snap_boundaries(
            prop["start"],
            prop["end"],
            timeline,
            t_start,
            t_end,
            first_word_start=f_word_start,
            last_word_end=l_word_end,
        )
        cand_dur = snapped_e - snapped_s
        if cand_dur < max(2.5, global_min_dur * 0.65):
            continue

        cand_words = [
            w for w in prop["words"]
            if float(w.get("start", 0)) >= snapped_s and float(w.get("end", 0)) <= snapped_e
        ]

        b_score = 50.0
        sents = prop.get("sentences", [])
        if sents:
            if sents[0].starts_with_conjunction:
                b_score -= 15.0
            if sents[-1].has_terminal_punct:
                b_score += 20.0
            if sents[-1].ends_with_conjunction:
                b_score -= 20.0

        target_dur = prop.get("target_dur") or min((t[1] for t in targets), key=lambda td: abs(cand_dur - td))
        dur_dev = abs(cand_dur - target_dur) / target_dur
        b_score -= min(30.0, dur_dev * 25.0)

        req_score = b_score
        cand_text_lower = prop["text"].lower()
        req_kws = [k.lower() for k in criteria.get("keywords", []) if len(k) > 2]
        if req_kws:
            hits = sum(1 for kw in req_kws if kw in cand_text_lower)
            req_score += min(50.0, hits * 25.0)

        req_topic = str(criteria.get("topic", "")).lower()
        if req_topic:
            topic_tokens = [t for t in req_topic.split() if len(t) > 2]
            if topic_tokens and any(t in cand_text_lower for t in topic_tokens):
                req_score += 35.0

        if criteria.get("reaction") == "riso":
            for ae in timeline.get("audio_events", []):
                ae_s = float(ae.get("start", 0))
                if snapped_s <= ae_s <= snapped_e:
                    if any(k in str(ae.get("type", "")).lower() for k in ("laugh", "riso")):
                        req_score += 45.0
                        break

        if criteria.get("action"):
            for ve in timeline.get("visual_events", []):
                ve_s = float(ve.get("start", 0))
                if snapped_s <= ve_s <= snapped_e:
                    req_score += 25.0
                    break

        processed_candidates.append({
            "start": snapped_s,
            "end": snapped_e,
            "duration": cand_dur,
            "text": prop["text"],
            "words": cand_words,
            "sentences": sents,
            "quality": b_score,
            "retrieval_score": req_score,
            "justified_deviation": prop["justified_deviation"],
            "anchor_type": prop["anchor_type"],
            "duration_bucket": prop.get("duration_bucket", targets[0][3]),
            "target_dur": target_dur,
        })

    # Deduplication via temporal IoU, keeping higher retrieval score
    processed_candidates.sort(key=lambda c: c["retrieval_score"], reverse=True)

    deduped: list[dict] = []
    for cand in processed_candidates:
        overlap = False
        for kept in deduped:
            # If candidates belong to different requested duration buckets, preserve both
            if cand.get("duration_bucket") != kept.get("duration_bucket") and len(targets) > 1:
                # Only suppress cross-bucket if containment is near-total (> 85%)
                _, containment = _temporal_overlap(cand["start"], cand["end"], kept["start"], kept["end"])
                if containment >= 0.85:
                    overlap = True
                    break
            else:
                iou, containment = _temporal_overlap(cand["start"], cand["end"], kept["start"], kept["end"])
                if iou >= 0.55 or containment >= 0.70:
                    overlap = True
                    break
        if not overlap:
            deduped.append(cand)


    # Final sort chronologically for evaluation
    deduped.sort(key=lambda c: c["start"])
    return deduped


# ---------------------------------------------------------------------------
# Structured Request Understanding (Local Fallback)
# ---------------------------------------------------------------------------

def local_understand_request(request: str, options: dict) -> dict:
    """Extract structured criteria locally when external AI provider is unavailable."""
    clip_model = options.get("clip_model", "Auto")
    req_clean = request.strip().lower()

    # Base modality from clip_model
    req_modality = "multimodal"
    if clip_model == "Conversa / Talking Head":
        req_modality = "text"
    elif clip_model == "Multimodal / Clip Anything":
        req_modality = "multimodal"

    if not req_clean:
        return {
            "topic": "",
            "emotion": "",
            "reaction": "",
            "action": "",
            "setting": "",
            "required_modality": req_modality,
            "keywords": [],
            "target_duration_bias": options.get("duration", "Auto"),
            "semantic_limitation": None,
            "mode": "local",
            "provider": None,
        }

    # Extract keywords
    stop_words = {
        "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da",
        "dos", "das", "em", "no", "na", "nos", "nas", "para", "por", "com",
        "como", "que", "se", "e", "ou", "quando", "onde", "quem", "qual",
        "pegue", "encontre", "mostre", "compile", "todos", "todas", "os",
        "melhores", "partes", "momentos", "vídeo"
    }
    raw_tokens = re.findall(r"\b\w{3,}\b", req_clean)
    keywords = [t for t in raw_tokens if t not in stop_words]

    # Detect requested emotion / reaction / modality
    reaction = ""
    emotion = ""
    action = ""

    if any(k in req_clean for k in ("rir", "risada", "engraçado", "engraçados", "hilário", "hilários", "piada", "comédia")):
        reaction = "riso"
        emotion = "alegria"
        if clip_model != "Conversa / Talking Head":
            req_modality = "audio"
    elif any(k in req_clean for k in ("reação", "reações", "surpresa", "chocado", "assustado", "inesperado", "inesperados", "susto")):
        reaction = "reação"
        emotion = "surpresa"
        if clip_model != "Conversa / Talking Head":
            req_modality = "multimodal"
    elif any(k in req_clean for k in ("gol", "jogada", "jogadas", "futebol", "drible", "cesta", "luta", "combate", "corrida", "ação")):
        reaction = "ação"
        emotion = "entusiasmo"
        action = "jogada ou dinâmica rápida"
        if clip_model != "Conversa / Talking Head":
            req_modality = "visual"
    elif any(k in req_clean for k in ("discussão", "debate", "argumento", "inteligência", "artificial", "história", "explicação", "entrevista", "falaram")):
        reaction = "argumento"
        emotion = "reflexão"
        req_modality = "text"

    return {
        "topic": " ".join(keywords[:3]),
        "emotion": emotion,
        "reaction": reaction,
        "action": action,
        "setting": "",
        "required_modality": req_modality,
        "keywords": keywords,
        "target_duration_bias": options.get("duration", "Auto"),
        "semantic_limitation": "Análise semântica avançada indisponível (sem provedor configurado). Critérios baseados em extração local de palavras-chave e sinais acústico-visuais.",
        "mode": "local",
        "provider": None,
    }

# ---------------------------------------------------------------------------
# Deterministic Scoring Dimensions & Timeline Evidence
# ---------------------------------------------------------------------------

def calculate_local_scores(
    cand: dict,
    timeline: dict,
    options: dict,
    criteria: dict,
) -> dict[str, float]:
    """Compute deterministic scores (0..100) and explicit penalties for candidate."""
    start = cand["start"]
    end = cand["end"]
    duration = end - start
    words = cand.get("words", [])
    sentences = cand.get("sentences", [])
    text = cand.get("text", "")
    genre = options.get("genre", "Auto")
    platform = options.get("platform", "TikTok")
    clip_model = options.get("clip_model", "Auto")

    # 1. Hook Score (0..100)
    # Speech onset latency
    latency = 0.0
    if words:
        first_word_start = float(words[0].get("start", start))
        latency = max(0.0, first_word_start - start)

    if latency <= 0.4:
        onset_score = 100.0
    elif latency <= 1.0:
        onset_score = 80.0
    elif latency <= 2.0:
        onset_score = 55.0
    else:
        onset_score = 25.0

    # Phrasing trigger words in first 10 words
    first_tokens = [_clean_word_token(str(w.get("word", ""))) for w in words[:10]]
    hook_word_count = sum(1 for tok in first_tokens if tok in HOOK_TRIGGER_WORDS)
    phrasing_score = min(100.0, 40.0 + hook_word_count * 20.0)
    if any(str(w.get("word", "")).endswith("?") for w in words[:12]):
        phrasing_score = min(100.0, phrasing_score + 25.0)

    # Early events in first 3.5s
    early_event_bonus = 0.0
    for ae in timeline.get("audio_events", []):
        if start <= float(ae.get("start", 0)) <= start + 3.5:
            early_event_bonus += 15.0
            break
    for ve in timeline.get("visual_events", []):
        if start <= float(ve.get("start", 0)) <= start + 3.5:
            early_event_bonus += 10.0
            break

    hook_score = min(100.0, onset_score * 0.45 + phrasing_score * 0.35 + early_event_bonus * 0.20)

    # 2. Flow Score (0..100)
    # Speech rate (WPM)
    wpm = (len(words) / duration) * 60.0 if duration > 0 else 0.0
    # Ideal Portuguese short-form speech rate: 140–165 WPM
    if wpm <= 0:
        flow_wpm = 30.0 if clip_model == "Multimodal / Clip Anything" else 10.0
    else:
        flow_wpm = max(10.0, 100.0 - abs(wpm - 150.0) * 0.9)

    # Rhythm stability (absence of large pauses)
    pause_penalties = 0.0
    for i in range(len(words) - 1):
        gap = float(words[i + 1].get("start", 0)) - float(words[i].get("end", 0))
        if gap > 1.2:
            pause_penalties += 15.0
        elif gap > 0.7:
            pause_penalties += 5.0

    flow_score = max(10.0, min(100.0, flow_wpm - pause_penalties))

    # 3. Value Score (0..100)
    # Lexical variety & information density
    unique_tokens = set(_clean_word_token(str(w.get("word", ""))) for w in words if len(str(w.get("word", ""))) > 3)
    lexical_density = (len(unique_tokens) / len(words)) if words else 0.0
    val_density_score = min(100.0, lexical_density * 130.0)

    # Overlap with timeline keywords and semantic tags
    tl_keywords = set(str(k).lower() for k in timeline.get("keywords", []))
    tl_tags = set(str(t).lower() for t in timeline.get("semantic_tags", []))
    kw_hits = sum(1 for tok in unique_tokens if tok in tl_keywords or tok in tl_tags)
    val_kw_score = min(100.0, 40.0 + kw_hits * 15.0)

    # Request criteria keyword match
    req_keywords = set(criteria.get("keywords", []))
    req_hits = sum(1 for tok in unique_tokens if tok in req_keywords)
    req_match_score = min(100.0, req_hits * 35.0) if req_keywords else 50.0

    value_score = min(100.0, val_density_score * 0.35 + val_kw_score * 0.35 + req_match_score * 0.30)

    # 4. Platform Fit Score (0..100)
    plat_info = PLATFORM_PARAMS.get(platform, PLATFORM_PARAMS["TikTok"])
    ideal_d = plat_info["ideal_duration"]
    sigma_d = plat_info["duration_sigma"]
    max_d = plat_info["max_duration"]

    # Gaussian fit curve around platform ideal duration
    dur_diff = duration - ideal_d
    plat_fit_score = math.exp(-((dur_diff / sigma_d) ** 2)) * 100.0

    # Platform ceiling rules (YouTube Shorts supports up to 3 minutes / 180s officially)
    if platform == "YouTube Shorts" and duration > 180.0:
        plat_fit_score = max(0.0, 40.0 - (duration - 180.0) * 12.0)
    elif platform == "TikTok" and duration > 60.0:
        plat_fit_score = max(10.0, plat_fit_score - (duration - 60.0) * 4.0)

    # 5. Narrative Completeness (0..100)
    narrative_score = 50.0
    if sentences:
        first_s = sentences[0]
        last_s = sentences[-1]

        # Clean beginning
        if not first_s.starts_with_conjunction:
            narrative_score += 15.0
        else:
            narrative_score -= 15.0

        # Clean conclusion
        if last_s.has_terminal_punct:
            narrative_score += 25.0
        if last_s.ends_with_conjunction:
            narrative_score -= 25.0

        # Multi-sentence progression
        if len(sentences) >= 2:
            narrative_score += 10.0
    else:
        # Fallback if no sentences
        narrative_score = 45.0

    narrative_score = max(5.0, min(100.0, narrative_score))

    # 6. Emotional Intensity (0..100)
    emotion_score = 30.0
    # Audio events (laughter, cheer, applause, shout)
    for ae in timeline.get("audio_events", []):
        ae_s = float(ae.get("start", 0))
        if start <= ae_s <= end:
            ae_type = str(ae.get("type", "")).lower()
            conf = float(ae.get("confidence", 0.7))
            if any(k in ae_type for k in ("laugh", "cheer", "applause", "shout", "riso")):
                emotion_score += 30.0 * conf

    # Exclamations and emotional trigger words
    exclamation_count = sum(1 for w in words if "!" in str(w.get("word", "")))
    emotion_score += min(20.0, exclamation_count * 8.0)
    emo_words = sum(1 for tok in unique_tokens if tok in EMOTION_TRIGGER_WORDS)
    emotion_score += min(20.0, emo_words * 7.0)

    # If user request matched emotional reaction (e.g. laughter)
    if criteria.get("reaction") == "riso":
        if any("laugh" in str(ae.get("type", "")).lower() or "riso" in str(ae.get("type", "")).lower()
               for ae in timeline.get("audio_events", []) if start <= float(ae.get("start", 0)) <= end):
            emotion_score += 25.0

    emotion_score = min(100.0, emotion_score)

    # 7. Audio Signals Score (0..100)
    audio_score = 40.0
    for ae in timeline.get("audio_events", []):
        ae_s = float(ae.get("start", 0))
        if start <= ae_s <= end:
            conf = float(ae.get("confidence", 0.6))
            audio_score += 18.0 * conf
    # Speech energy continuity
    speech_ratio = min(1.0, (len(words) * 0.35) / duration) if duration > 0 else 0.5
    audio_score += speech_ratio * 30.0
    audio_score = min(100.0, audio_score)

    # 8. Visual Signals Score (0..100)
    visual_score = 40.0
    # Scene cuts pacing
    scene_cuts_count = sum(1 for sc in timeline.get("scenes", []) if start <= float(sc.get("start", 0)) <= end)
    cuts_per_min = (scene_cuts_count / duration) * 60.0 if duration > 0 else 0.0
    # Optimal for short video: 4 to 12 cuts per minute
    if 4.0 <= cuts_per_min <= 14.0:
        visual_score += 35.0
    elif 1.0 <= cuts_per_min < 4.0:
        visual_score += 20.0
    elif cuts_per_min == 0.0:
        visual_score += 5.0
    else:  # excessively fast cuts
        visual_score += 15.0

    # Visual events (reactions, motion)
    for ve in timeline.get("visual_events", []):
        ve_s = float(ve.get("start", 0))
        if start <= ve_s <= end:
            conf = float(ve.get("confidence", 0.6))
            visual_score += 15.0 * conf

    # Face tracks presence and stability
    tracks = timeline.get("tracks", [])
    in_range_tracks = [tr for tr in tracks if start <= float(tr.get("time", 0)) <= end]
    if in_range_tracks:
        boxes_count = sum(len(tr.get("boxes", [])) for tr in in_range_tracks)
        if boxes_count > 0:
            visual_score += 20.0

    visual_score = min(100.0, visual_score)

    # 9. Shareability Score (0..100)
    shareability_score = (hook_score * 0.30 + emotion_score * 0.40 + value_score * 0.30)
    # Bonus for punchy short sentences
    if any(3 <= len(s.words) <= 10 and s.has_terminal_punct for s in sentences):
        shareability_score = min(100.0, shareability_score + 15.0)

    # 10. Penalties
    # Context Penalty (0..100)
    context_penalty = 0.0
    if sentences:
        if sentences[0].starts_with_conjunction:
            context_penalty += 35.0
        if sentences[-1].ends_with_conjunction:
            context_penalty += 45.0
        if not sentences[-1].has_terminal_punct:
            context_penalty += 20.0
    first_tok = first_tokens[0] if first_tokens else ""
    if first_tok in {"ele", "ela", "eles", "elas", "disso", "daquilo", "nisso", "naquilo"}:
        context_penalty += 20.0
    context_penalty = min(100.0, context_penalty)

    # Silence Penalty (0..100)
    silence_penalty = 0.0
    total_silence_duration = 0.0
    for s_interval in timeline.get("silence", []):
        s_s = max(start, float(s_interval.get("start", 0)))
        s_e = min(end, float(s_interval.get("end", 0)))
        if s_e > s_s:
            s_dur = s_e - s_s
            total_silence_duration += s_dur
            if s_dur >= 1.5:
                silence_penalty += 35.0
            elif s_dur >= 0.9:
                silence_penalty += 15.0

    silence_ratio = (total_silence_duration / duration) if duration > 0 else 0.0
    if silence_ratio >= 0.15:
        silence_penalty += (silence_ratio - 0.15) * 200.0

    # Relaxation of silence penalty for multimodal models with high visual activity
    if clip_model == "Multimodal / Clip Anything" and visual_score >= 65.0:
        silence_penalty = max(0.0, silence_penalty * 0.4)

    silence_penalty = min(100.0, silence_penalty)

    return {
        "hook": round(hook_score, 1),
        "flow": round(flow_score, 1),
        "value": round(value_score, 1),
        "platform_fit": round(plat_fit_score, 1),
        "narrative": round(narrative_score, 1),
        "emotion": round(emotion_score, 1),
        "audio": round(audio_score, 1),
        "visual": round(visual_score, 1),
        "shareability": round(shareability_score, 1),
        "context_penalty": round(context_penalty, 1),
        "silence_penalty": round(silence_penalty, 1),
    }


# ---------------------------------------------------------------------------
# Weight Resolution & Composite Scoring Formula
# ---------------------------------------------------------------------------

def resolve_weights(options: dict, criteria: dict | None = None) -> dict[str, float]:
    """Compute normalized dimension weights applying genre, platform, clip model, and user request criteria."""
    genre = options.get("genre", "Auto")
    platform = options.get("platform", "TikTok")
    clip_model = options.get("clip_model", "Auto")

    base_w = dict(GENRE_WEIGHTS.get(genre, GENRE_WEIGHTS["Auto"]))

    # Apply platform multiplier
    plat_info = PLATFORM_PARAMS.get(platform, PLATFORM_PARAMS["TikTok"])
    base_w["hook"] *= plat_info.get("hook_mult", 1.0)
    base_w["emotion"] *= plat_info.get("emotion_mult", 1.0)
    base_w["flow"] *= plat_info.get("flow_mult", 1.0)
    base_w["value"] *= plat_info.get("value_mult", 1.0)
    base_w["visual"] *= plat_info.get("visual_mult", 1.0)
    base_w["shareability"] *= plat_info.get("shareability_mult", 1.0)

    # Apply clip model multiplier
    if clip_model == "Conversa / Talking Head":
        base_w["flow"] *= 1.20
        base_w["narrative"] *= 1.20
        base_w["visual"] *= 0.75
    elif clip_model == "Multimodal / Clip Anything":
        base_w["visual"] *= 1.35
        base_w["audio"] *= 1.30
        base_w["flow"] *= 0.80
        base_w["narrative"] *= 0.80

    # Longer requested clips need development; short clips prioritize the opening.
    raw_durations = options.get("durations")
    if raw_durations and isinstance(raw_durations, list):
        targets_list = [
            ((float(options.get("custom_min", 15)) + float(options.get("custom_max", 60))) / 2)
            if d == "personalizada"
            else DURATION_TARGETS.get(d, DURATION_TARGETS["Auto"])[1]
            for d in raw_durations
        ]
        target = sum(targets_list) / len(targets_list) if targets_list else 40.0
    else:
        duration = options.get("duration", "Auto")
        target = (
            (float(options.get("custom_min", 15)) + float(options.get("custom_max", 60))) / 2
            if duration == "personalizada"
            else DURATION_TARGETS.get(duration, DURATION_TARGETS["Auto"])[1]
        )
    if target < 30:
        base_w["hook"] *= 1.15
        base_w["shareability"] *= 1.10
    elif target >= 90:
        base_w["flow"] *= 1.15
        base_w["narrative"] *= 1.25

    # Adapt weights based on user semantic request criteria if provided
    if criteria and isinstance(criteria, dict):
        crit_reaction = str(criteria.get("reaction", "")).lower()
        crit_modality = str(criteria.get("required_modality", "")).lower()
        crit_emotion = str(criteria.get("emotion", "")).lower()

        if crit_reaction == "riso" or crit_emotion in ("alegria", "humor"):
            base_w["emotion"] *= 1.25
            base_w["audio"] *= 1.15
        elif crit_reaction == "reação" or crit_emotion in ("surpresa", "choque"):
            base_w["emotion"] *= 1.20
            base_w["hook"] *= 1.15
        elif crit_modality == "visual" or criteria.get("action"):
            base_w["visual"] *= 1.25
            base_w["hook"] *= 1.10
        elif crit_modality == "audio":
            base_w["audio"] *= 1.25
        elif crit_modality == "text" or crit_reaction == "argumento":
            base_w["narrative"] *= 1.20
            base_w["value"] *= 1.15

    # Normalize weights so sum equals 1.0
    total_w = sum(base_w.values())
    if total_w > 0:
        return {k: v / total_w for k, v in base_w.items()}
    return base_w


def compute_final_score(
    scores: dict[str, float],
    weights: dict[str, float],
    request_boost: float = 0.0,
) -> float:
    """Calculate overall clamped potential score: clamp(sum(w_i * d_i) - penalties + boost, 0, 100)."""
    pos_sum = (
        weights["hook"] * scores["hook"]
        + weights["flow"] * scores["flow"]
        + weights["value"] * scores["value"]
        + weights["platform_fit"] * scores["platform_fit"]
        + weights["narrative"] * scores["narrative"]
        + weights["emotion"] * scores["emotion"]
        + weights["audio"] * scores["audio"]
        + weights["visual"] * scores["visual"]
        + weights["shareability"] * scores["shareability"]
    )

    # Explicit penalties
    w_ctx = 0.20
    w_sil = 0.15
    penalties = w_ctx * scores["context_penalty"] + w_sil * scores["silence_penalty"]

    final_val = pos_sum - penalties + request_boost
    return round(max(0.0, min(100.0, final_val)), 1)


# ---------------------------------------------------------------------------
# Titles, Summaries & Provenance Explanation
# ---------------------------------------------------------------------------

def generate_local_title(cand: dict) -> str:
    """Generate a factual, grounded title from candidate words without hallucinations."""
    words = cand.get("words", [])
    if not words:
        return f"Corte em {cand['start']:.1f}s–{cand['end']:.1f}s"

    raw_tokens = [str(w.get("word", "")).strip() for w in words]

    # Look for question or strong opening sentence
    for s in cand.get("sentences", []):
        if s.has_question and len(s.words) <= 10:
            return s.text[:80].strip()

    # Extract first cohesive phrase up to 7 words
    clean_first = []
    for tok in raw_tokens:
        clean_first.append(tok)
        if len(clean_first) >= 7 or any(tok.endswith(p) for p in (",", ".", "!", "?", ":")):
            break

    title = " ".join(clean_first)
    title = re.sub(r"[,.:;!?]+$", "", title).strip()
    if title:
        # Capitalize first letter
        return title[:1].upper() + title[1:]
    return f"Momento aos {cand['start']:.1f}s"


def generate_local_summary(cand: dict) -> str:
    """Generate a concise, factual summary from candidate text."""
    text = cand.get("text", "").strip()
    if not text:
        return f"Trecho selecionado entre {cand['start']:.1f}s e {cand['end']:.1f}s com atividade na timeline."
    if len(text) > 180:
        return text[:177] + "..."
    return text


def build_provenance_reason(
    mode: str,
    scores: dict[str, float],
    cand: dict,
    genre: str,
    platform: str,
    criteria: dict,
) -> str:
    """Explain exact provenance and evidence supporting the estimated score."""
    start = cand["start"]
    end = cand["end"]
    dur = end - start
    evidence_parts = [
        f"Limites naturais: início aos {start:.1f}s e término aos {end:.1f}s ({dur:.1f}s)",
        f"Gênero '{genre}', plataforma '{platform}'",
    ]

    if scores["hook"] >= 75.0:
        evidence_parts.append("Hook inicial com retenção rápida na timeline")
    if scores["emotion"] >= 70.0:
        evidence_parts.append("Pico acústico/emocional detectado na timeline (estimativa heurística)")
    if scores["context_penalty"] > 25.0:
        evidence_parts.append(f"Penalidade de contexto aplicada ({scores['context_penalty']:.0f} pts)")
    if scores["silence_penalty"] > 20.0:
        evidence_parts.append(f"Penalidade por pausas/silêncio ({scores['silence_penalty']:.0f} pts)")
    if mode == "local":
        mode_note = (
            "Modo local (sem IA semântica externa): pontuação estimada exclusivamente por sinais "
            "acústico-visuais, ritmo e limites naturais da timeline. As dimensões semânticas "
            "(emoção, valor, shareability) são estimativas heurísticas locais baseadas em eventos "
            "e pontuação, não em compreensão de linguagem natural. Análise semântica avançada ausente."
        )
    else:
        mode_note = "Modo híbrido: fusão de sinais locais da timeline com avaliação semântica externa do provedor."

    return f"{mode_note} Detalhes: {'; '.join(evidence_parts)}."


# ---------------------------------------------------------------------------
# Edit Struct Assembly
# ---------------------------------------------------------------------------

def build_candidate_edit(
    cand: dict,
    timeline: dict,
    options: dict,
    title: str,
) -> dict:
    """Construct complete Edit dict conforming strictly to schemas.Edit."""
    cand_start = float(cand["start"])
    cand_end = float(cand["end"])
    cand_dur = cand_end - cand_start

    # Default crop_x must be None to delegate dynamic per-frame tracking to media/visual pipeline.
    # Manual crop_x is only set if explicitly provided in options by the editor.
    crop_x: float | None = options.get("crop_x")
    if crop_x is not None:
        crop_x = round(max(0.0, min(1.0, float(crop_x))), 3)

    # remove_ranges must default strictly to [] so content is never auto-deleted without explicit user intent.
    # Manual removal ranges are only set if explicitly provided in options by the editor.
    candidate_removals: list[dict] = []
    if options.get("remove_ranges"):
        last_removal = cand_start
        for r in sorted(options["remove_ranges"], key=lambda item: float(item.get("start", 0))):
            r_s = round(float(r.get("start", 0)), 2)
            r_e = round(float(r.get("end", 0)), 2)
            if r_s >= last_removal and r_e <= cand_end and r_e > r_s:
                candidate_removals.append({"start": r_s, "end": r_e})
                last_removal = r_e
    # Filter candidate words strictly inside clip boundaries
    cand_words: list[dict] = []
    for w in cand.get("words", []):
        raw_s = float(w.get("start", 0))
        raw_e = float(w.get("end", 0))
        w_s = max(cand_start, round(raw_s, 3))
        w_e = min(cand_end, round(raw_e, 3))
        if w_e > w_s and w_s >= cand_start and w_e <= cand_end:
            cand_words.append({
                "start": w_s,
                "end": w_e,
                "word": str(w.get("word", "")),
            })
    return {
        "start": cand_start,
        "end": cand_end,
        "title": title[:240],
        "format": options.get("format", "9:16"),
        "reframe": True,
        "subtitles": True,
        "subtitle_style": options.get("subtitle_style", "highlight"),
        "subtitle_size": int(options.get("subtitle_size", 48)),
        "subtitle_position": options.get("subtitle_position", "bottom"),
        "crop_x": crop_x,
        "remove_ranges": candidate_removals,
        "words": cand_words,
    }


# ---------------------------------------------------------------------------
# Candidate Thumbnail Sampling & Ranking API
# ---------------------------------------------------------------------------

def sample_candidate_thumbnails(
    start: float,
    end: float,
    timeline: dict,
    options: dict,
) -> list[dict]:
    """Select up to 2 representative image thumbnails for the candidate interval."""
    if not options.get("allow_images"):
        return []

    # 1. Select from timeline pre-extracted thumbnails (from media.analyze)
    tl_thumbs = timeline.get("thumbnails", [])
    in_range = [
        t for t in tl_thumbs
        if isinstance(t, dict) and start <= float(t.get("time", -1)) <= end
    ]
    if in_range:
        if len(in_range) <= 2:
            return in_range
        return [in_range[0], in_range[-1]]

    # If none strictly in range but timeline has thumbnails, pick closest to interval
    if tl_thumbs:
        closest = min(
            tl_thumbs,
            key=lambda t: min(abs(float(t.get("time", 0)) - start), abs(float(t.get("time", 0)) - end)),
        )
        if abs(float(closest.get("time", 0)) - start) <= 3.0:
            return [closest]

    # 2. On-demand sampling fallback if media/visual module and video file are present
    v_path = options.get("video_path") or timeline.get("video_path") or timeline.get("source_path")
    if v_path:
        p = Path(v_path)
        if p.exists():
            extractor = None
            try:
                from localclip.media import extract_thumbnail_base64
                extractor = extract_thumbnail_base64
            except ImportError:
                try:
                    from localclip.visual import extract_thumbnail_base64
                    extractor = extract_thumbnail_base64
                except ImportError:
                    extractor = None

            if extractor is not None:
                sampled: list[dict] = []
                try:
                    t_hook = round(start + min(1.0, (end - start) * 0.15), 2)
                    b64_hook = extractor(p, t_hook)
                    if b64_hook:
                        sampled.append({"time": t_hook, "image_b64": b64_hook, "mime_type": "image/jpeg"})

                    t_mid = round(start + (end - start) * 0.5, 2)
                    b64_mid = extractor(p, t_mid)
                    if b64_mid:
                        sampled.append({"time": t_mid, "image_b64": b64_mid, "mime_type": "image/jpeg"})
                except Exception:
                    pass
                if sampled:
                    return sampled[:2]

    return []


def select_diverse_top_candidates(
    candidates: list[dict],
    requested_results: int | None = None,
    *,
    min_score: float = 40.0,
) -> list[dict]:
    """Selects top candidates maximizing score while enforcing temporal and semantic diversity.

    When requested_results is None (or <= 0), automatically determines the count of quality
    candidates spanning distinct natural moments without repetition.
    Guarantees that results are not redundant slices of the same moment.
    Does not arbitrarily cut speech or force duplicate selections when source
    video length genuinely yields fewer distinct natural moments.
    """
    if not candidates:
        return []

    sorted_cands = sorted(candidates, key=lambda c: c["score"], reverse=True)
    if len(sorted_cands) <= 1:
        return [c for c in sorted_cands if requested_results is not None or c["score"] >= min_score]

    # Automatic mode: generate all quality non-overlapping candidates
    if requested_results is None or requested_results <= 0:
        selected: list[dict] = []
        for cand in sorted_cands:
            if cand["score"] < min_score:
                continue
            overlap = False
            for s in selected:
                iou, containment = _temporal_overlap(cand["start"], cand["end"], s["start"], s["end"])
                intersection = max(0.0, min(cand["end"], s["end"]) - max(cand["start"], s["start"]))
                # Strict temporal dedup: never repeat video moments
                if intersection > 2.0 or iou >= 0.15 or containment >= 0.20:
                    overlap = True
                    break
                # Semantic dedup: never repeat same topic / speech content
                if _semantic_similarity(cand, s) >= 0.55:
                    overlap = True
                    break
            if not overlap:
                selected.append(cand)


        return sorted(selected, key=lambda candidate: candidate["score"], reverse=True)

    # Explicit / legacy requested count:
    selected = [sorted_cands[0]]

    # Stage 1: Strict diversity (low IoU and low containment, no semantic duplicates)
    for cand in sorted_cands[1:]:
        if len(selected) >= requested_results:
            break
        overlap = False
        for s in selected:
            iou, containment = _temporal_overlap(cand["start"], cand["end"], s["start"], s["end"])
            if iou >= 0.35 or containment >= 0.45 or _semantic_similarity(cand, s) >= 0.70:
                overlap = True
                break
        if not overlap:
            selected.append(cand)

    # Stage 2: Relaxed diversity if slots remain and distinct candidates exist
    # Admits candidates with moderate overlap only if they are not near-duplicates (< 0.65 containment)
    if len(selected) < requested_results:
        remaining = [c for c in sorted_cands if c not in selected]
        while len(selected) < requested_results and remaining:
            best_cand = None
            best_eff_score = -1.0
            for c in remaining:
                max_cont = 0.0
                for s in selected:
                    _, cont = _temporal_overlap(c["start"], c["end"], s["start"], s["end"])
                    max_cont = max(max_cont, cont)
                # Disallow near-duplicates (> 65% overlap with an already selected moment)
                if max_cont < 0.65:
                    eff_score = c["score"] - (max_cont * 25.0)
                    if eff_score > best_eff_score:
                        best_eff_score = eff_score
                        best_cand = c
            if best_cand is not None:
                selected.append(best_cand)
                remaining.remove(best_cand)
            else:
                break

    return sorted(selected, key=lambda candidate: candidate["score"], reverse=True)


def rank(
    timeline: dict,
    options: dict | None = None,
    providers: dict | None = None,
    usage: Callable[[dict], None] | None = None,
    cache_dir: Path | str | None = None,
) -> list[dict]:
    """Execute complete natural boundary candidate generation and explainable ranking.

    Args:
        timeline: Structured video analysis dict (words, scenes, audio_events, etc.).
        options: User configuration dict (genre, platform, duration, request, results).
        providers: Provider configs dict {'primary': ..., 'fallback': ...}.
        usage: Optional callback for token and latency tracking.
        cache_dir: Path for persistent caching of provider responses.

    Returns:
        List of Candidate dicts sorted by potential score descending, respecting
        the requested number of results.
    """
    opts = dict(options or {})
    if opts.get("clip_model", "Auto") == "Auto":
        start, end = float(timeline["start"]), float(timeline["end"])
        intervals = timeline.get("segments") or timeline.get("words", [])
        covered, previous_end = 0.0, start
        for interval in sorted(intervals, key=lambda item: item["start"]):
            left = max(start, previous_end, float(interval["start"]))
            right = min(end, float(interval["end"]))
            covered += max(0.0, right - left)
            previous_end = max(previous_end, right)
        opts["clip_model"] = (
            "Conversa / Talking Head" if end > start and covered / (end - start) > .6
            else "Multimodal / Clip Anything"
        )
    provs = dict(providers or {"primary": None, "fallback": None})
    usage_cb = usage or (lambda x: None)
    c_dir = Path(cache_dir) if cache_dir is not None else None

    # Step 1: Understand user request into structured criteria
    user_request = str(opts.get("request", "")).strip()
    criteria = providers_module.understand_request(
        request=user_request, options=opts, providers=provs,
        usage=usage_cb, cache_dir=c_dir,
    )

    # Step 2: Generate natural boundary candidate proposals (10–20 if source permits)
    candidate_windows = generate_candidate_windows(timeline, opts, criteria)

    if not candidate_windows:
        return []

    # Assign persistent candidate IDs and baseline local scoring
    weights = resolve_weights(opts, criteria)
    preliminary_candidates: list[dict] = []

    # Deterministic source content signature to prevent cross-project cache collisions
    # while ensuring identical sources produce identical candidate IDs for provider caching
    words_prefix = " ".join(str(w.get("word", "")) for w in timeline.get("words", [])[:200])
    raw_sig = f"{timeline.get('start', 0)}:{timeline.get('end', 0)}:{words_prefix}"
    content_sig = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()[:16]

    for win in candidate_windows:
        # Deterministic UUIDv5 based on source content hash and temporal boundaries
        cand_key = f"{content_sig}:{win['start']:.2f}:{win['end']:.2f}:{win['text'][:64]}"
        c_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:localclip:cand:{cand_key}"))

        # Sample or retrieve candidate thumbnails if allowed
        c_thumbs = sample_candidate_thumbnails(win["start"], win["end"], timeline, opts)

        local_scores = calculate_local_scores(win, timeline, opts, criteria)

        # Compute request relevance boost
        req_boost = 0.0
        if user_request:
            req_kws = set(criteria.get("keywords", []))
            cand_tokens = set(_clean_word_token(str(w.get("word", ""))) for w in win.get("words", []))
            kw_matches = sum(1 for k in req_kws if k in cand_tokens)
            if kw_matches > 0:
                req_boost += min(20.0, kw_matches * 10.0)

            # Match requested reaction
            if criteria.get("reaction") == "riso":
                for ae in timeline.get("audio_events", []):
                    if win["start"] <= float(ae.get("start", 0)) <= win["end"]:
                        if any(k in str(ae.get("type", "")).lower() for k in ("laugh", "riso")):
                            req_boost += 15.0
                            break

        req_boost = min(25.0, req_boost)
        local_final_score = compute_final_score(local_scores, weights, request_boost=req_boost)

        preliminary_candidates.append({
            "id": c_id,
            "start": win["start"],
            "end": win["end"],
            "duration": win["duration"],
            "text": win["text"],
            "words": win["words"],
            "thumbnails": c_thumbs,
            "sentences": win.get("sentences", []),
            "local_scores": local_scores,
            "req_boost": req_boost,
            "score": local_final_score,
            "anchor_type": win.get("anchor_type", "sentence"),
        })

    # Step 3: Optional Batch Semantic Assessment via Provider
    evaluated_semantic: dict[str, dict] = {}

    has_active_provider = bool(
        provs.get("primary") or provs.get("fallback")
    )

    if has_active_provider:
        # Format payload for evaluate_candidates
        eval_payload = [
            {
                "id": c["id"],
                "start": c["start"],
                "end": c["end"],
                "text": c["text"],
                "transcript": c["text"],
                "duration": c["duration"],
                "preview_words": [w.get("word", "") for w in c["words"][:20]],
                "thumbnails": c.get("thumbnails", []),
            }
            for c in preliminary_candidates
        ]
        # Bounded semantic batches limit context size without imposing a result cap.
        for start in range(0, len(eval_payload), 20):
            eval_results = providers_module.evaluate_candidates(
                candidates=eval_payload[start:start + 20], timeline=timeline, options=opts,
                criteria=criteria, providers=provs, usage=usage_cb, cache_dir=c_dir,
            )
            evaluated_semantic.update((item["id"], item) for item in eval_results)
    # Step 4: Hybrid Fusion and Final Assembly
    final_candidates: list[dict] = []

    for item in preliminary_candidates:
        cid = item["id"]
        loc_scores = item["local_scores"]
        sem_data = evaluated_semantic.get(cid)

        if sem_data and isinstance(sem_data.get("scores"), dict):
            # Hybrid Mode
            mode = "hybrid"
            s_scores = sem_data["scores"]
            alpha = 0.60  # Semantic weight for evaluated dimensions

            merged_scores = {
                "hook": round(alpha * float(s_scores.get("hook", loc_scores["hook"])) + (1 - alpha) * loc_scores["hook"], 1),
                "flow": round(alpha * float(s_scores.get("flow", loc_scores["flow"])) + (1 - alpha) * loc_scores["flow"], 1),
                "value": round(alpha * float(s_scores.get("value", loc_scores["value"])) + (1 - alpha) * loc_scores["value"], 1),
                "platform_fit": loc_scores["platform_fit"],
                "narrative": round(alpha * float(s_scores.get("narrative", loc_scores["narrative"])) + (1 - alpha) * loc_scores["narrative"], 1),
                "emotion": round(alpha * float(s_scores.get("emotion", loc_scores["emotion"])) + (1 - alpha) * loc_scores["emotion"], 1),
                "audio": loc_scores["audio"],
                "visual": loc_scores["visual"],
                "shareability": round(alpha * float(s_scores.get("shareability", loc_scores["shareability"])) + (1 - alpha) * loc_scores["shareability"], 1),
                "context_penalty": round(alpha * float(s_scores.get("context_penalty", loc_scores["context_penalty"])) + (1 - alpha) * loc_scores["context_penalty"], 1),
                "silence_penalty": loc_scores["silence_penalty"],
            }
            final_score = compute_final_score(merged_scores, weights, request_boost=item["req_boost"])
            title = str(sem_data.get("title") or generate_local_title(item)).strip()
            summary = str(sem_data.get("summary") or generate_local_summary(item)).strip()
            ai_reason = str(sem_data.get("reason", "")).strip()
            reason = f"Avaliação da IA: {ai_reason}. " if ai_reason else ""
            reason += build_provenance_reason(mode, merged_scores, item, opts.get("genre", "Auto"), opts.get("platform", "TikTok"), criteria)
        else:
            # Local Mode
            mode = "local"
            merged_scores = dict(loc_scores)
            final_score = item["score"]
            title = generate_local_title(item)
            summary = generate_local_summary(item)
            reason = build_provenance_reason(mode, merged_scores, item, opts.get("genre", "Auto"), opts.get("platform", "TikTok"), criteria)

        if not opts.get("auto_title", True):
            title = f"Corte {item['start']:.1f}s–{item['end']:.1f}s"

        # Build complete scores dictionary conforming strictly to UI and API contracts
        scores_dict = {
            "overall": final_score,
            "hook": merged_scores["hook"],
            "flow": merged_scores["flow"],
            "value": merged_scores["value"],
            "platform_fit": merged_scores["platform_fit"],
            "narrative": merged_scores["narrative"],
            "emotion": merged_scores["emotion"],
            "audio": merged_scores["audio"],
            "visual": merged_scores["visual"],
            "shareability": merged_scores["shareability"],
            "context_penalty": merged_scores["context_penalty"],
            "silence_penalty": merged_scores["silence_penalty"],
        }

        # Filter candidate words
        cand_words = [
            {
                "start": max(item["start"], round(float(w.get("start", 0)), 3)),
                "end": min(item["end"], round(float(w.get("end", 0)), 3)),
                "word": str(w.get("word", "")),
            }
            for w in item["words"]
            if float(w.get("start", 0)) >= item["start"]
            and float(w.get("end", 0)) <= item["end"]
            and float(w.get("end", 0)) > float(w.get("start", 0))
        ]

        # Build Edit struct
        edit_dict = build_candidate_edit(item, timeline, opts, title)

        final_candidates.append({
            "id": cid,
            "start": item["start"],
            "end": item["end"],
            "title": title,
            "summary": summary,
            "score": final_score,
            "scores": scores_dict,
            "reason": reason,
            "mode": mode,
            "weights": weights,
            "request_boost": item["req_boost"],
            "resolved_clip_model": opts["clip_model"],
            "words": cand_words,
            "edit": edit_dict,
            "thumbnails": item.get("thumbnails", []),
            "render_path": None,
        })

    # Respect requested results count with diversity-aware selection (automatic when None)
    raw_results = opts.get("results")
    requested_results = None
    if raw_results is not None:
        try:
            requested_results = int(raw_results)
        except (ValueError, TypeError):
            requested_results = None
    return select_diverse_top_candidates(final_candidates, requested_results)
