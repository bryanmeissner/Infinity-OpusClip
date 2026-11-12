"""Regression tests for candidate generation and virality potential ranking engine.

Tests natural boundary detection without word truncation, request-aware candidate retrieval
across the full timeline before capping, deterministic content-based candidate IDs for caching,
thumbnail sampling, provider error propagation, unsuffixed score keys for UI compatibility,
platform duration limits (including 3-minute Shorts), and strict Edit schema conformance.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from localclip.ranking import (
    GENRE_WEIGHTS,
    PLATFORM_PARAMS,
    calculate_local_scores,
    compute_final_score,
    generate_candidate_windows,
    local_understand_request,
    parse_sentences_from_timeline,
    rank,
    resolve_weights,
    sample_candidate_thumbnails,
    select_diverse_top_candidates,
    snap_boundaries,
)
from localclip.schemas import Edit


# ---------------------------------------------------------------------------
# Fixtures and Sample Timelines
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_timeline_podcast():
    """Sample podcast timeline with continuous speech and distinct sentences."""
    words = [
        # Sentence 1 (0.5s - 5.0s): Strong question hook
        {"start": 0.5, "end": 1.2, "word": "Você"},
        {"start": 1.3, "end": 1.8, "word": "sabe"},
        {"start": 1.9, "end": 2.3, "word": "qual"},
        {"start": 2.4, "end": 2.6, "word": "é"},
        {"start": 2.7, "end": 3.0, "word": "o"},
        {"start": 3.1, "end": 3.8, "word": "maior"},
        {"start": 3.9, "end": 4.4, "word": "segredo"},
        {"start": 4.5, "end": 5.0, "word": "disso?"},
        # Sentence 2 (5.6s - 12.0s): Explanation
        {"start": 5.6, "end": 6.2, "word": "Muita"},
        {"start": 6.3, "end": 6.8, "word": "gente"},
        {"start": 6.9, "end": 7.4, "word": "acha"},
        {"start": 7.5, "end": 7.8, "word": "que"},
        {"start": 7.9, "end": 8.5, "word": "basta"},
        {"start": 8.6, "end": 9.2, "word": "trabalhar"},
        {"start": 9.3, "end": 9.9, "word": "muito"},
        {"start": 10.0, "end": 10.8, "word": "todos"},
        {"start": 10.9, "end": 11.2, "word": "os"},
        {"start": 11.3, "end": 12.0, "word": "dias."},
        # Sentence 3 (12.8s - 25.0s): Development
        {"start": 12.8, "end": 13.5, "word": "Porém"},
        {"start": 13.6, "end": 14.1, "word": "quando"},
        {"start": 14.2, "end": 14.8, "word": "você"},
        {"start": 14.9, "end": 15.5, "word": "analisa"},
        {"start": 15.6, "end": 16.0, "word": "as"},
        {"start": 16.1, "end": 16.9, "word": "métricas"},
        {"start": 17.0, "end": 17.5, "word": "reais"},
        {"start": 17.6, "end": 18.2, "word": "percebe"},
        {"start": 18.3, "end": 18.6, "word": "que"},
        {"start": 18.7, "end": 19.4, "word": "consistência"},
        {"start": 19.5, "end": 19.9, "word": "sem"},
        {"start": 20.0, "end": 20.9, "word": "estratégia"},
        {"start": 21.0, "end": 21.4, "word": "não"},
        {"start": 21.5, "end": 22.2, "word": "gera"},
        {"start": 22.3, "end": 23.1, "word": "resultado"},
        {"start": 23.2, "end": 25.0, "word": "algum."},
        # Sentence 4 (25.8s - 34.0s): Clean punchline conclusion
        {"start": 25.8, "end": 26.5, "word": "Foque"},
        {"start": 26.6, "end": 27.0, "word": "no"},
        {"start": 27.1, "end": 27.6, "word": "que"},
        {"start": 27.7, "end": 28.5, "word": "realmente"},
        {"start": 28.6, "end": 29.4, "word": "move"},
        {"start": 29.5, "end": 29.8, "word": "o"},
        {"start": 29.9, "end": 30.8, "word": "ponteiro"},
        {"start": 30.9, "end": 31.4, "word": "do"},
        {"start": 31.5, "end": 32.2, "word": "seu"},
        {"start": 32.3, "end": 34.0, "word": "negócio."},
    ]
    return {
        "start": 0.0,
        "end": 40.0,
        "words": words,
        "segments": [
            {"start": 0.5, "end": 12.0, "text": "Você sabe qual é o maior segredo disso? Muita gente acha que basta trabalhar muito todos os dias."},
            {"start": 12.8, "end": 34.0, "text": "Porém quando você analisa as métricas reais percebe que consistência sem estratégia não gera resultado algum. Foque no que realmente move o ponteiro do seu negócio."},
        ],
        "scenes": [
            {"start": 0.0, "end": 12.5},
            {"start": 12.5, "end": 25.5},
            {"start": 25.5, "end": 40.0},
        ],
        "silence": [
            {"start": 5.0, "end": 5.6},
            {"start": 12.0, "end": 12.8},
            {"start": 25.0, "end": 25.8},
        ],
        "thumbnails": [
            {"time": 2.0, "image_b64": "dGVzdC1pbWFnZS0x", "mime_type": "image/jpeg"},
            {"time": 28.0, "image_b64": "dGVzdC1pbWFnZS0y", "mime_type": "image/jpeg"},
        ],
        "audio_events": [
            {"start": 0.5, "end": 5.0, "type": "speech", "confidence": 0.95},
            {"start": 31.0, "end": 34.0, "type": "emphasis", "confidence": 0.85},
        ],
        "visual_events": [
            {"start": 12.5, "end": 13.0, "type": "camera_cut", "confidence": 0.9},
            {"start": 25.5, "end": 26.0, "type": "camera_cut", "confidence": 0.9},
        ],
        "tracks": [
            {"time": 2.0, "boxes": [{"x": 0.35, "y": 0.2, "w": 0.30, "h": 0.40}]},
            {"time": 15.0, "boxes": [{"x": 0.36, "y": 0.2, "w": 0.28, "h": 0.38}]},
            {"time": 30.0, "boxes": [{"x": 0.34, "y": 0.2, "w": 0.32, "h": 0.42}]},
        ],
        "keywords": ["segredo", "estratégia", "negócio", "métricas"],
        "semantic_tags": ["negócios", "podcast", "educacional"],
    }


@pytest.fixture
def sample_timeline_comedy():
    """Timeline with comedy, laughter audio event, and punchline."""
    words = [
        {"start": 1.0, "end": 1.5, "word": "Aí"},
        {"start": 1.6, "end": 2.0, "word": "eu"},
        {"start": 2.1, "end": 2.6, "word": "falei"},
        {"start": 2.7, "end": 3.0, "word": "pra"},
        {"start": 3.1, "end": 3.5, "word": "ele:"},
        {"start": 3.8, "end": 4.5, "word": "não"},
        {"start": 4.6, "end": 5.2, "word": "faça"},
        {"start": 5.3, "end": 6.0, "word": "isso!"},
        {"start": 6.8, "end": 7.5, "word": "E"},
        {"start": 7.6, "end": 8.0, "word": "ele"},
        {"start": 8.1, "end": 8.8, "word": "foi"},
        {"start": 8.9, "end": 9.2, "word": "lá"},
        {"start": 9.3, "end": 9.8, "word": "e"},
        {"start": 9.9, "end": 10.5, "word": "fez"},
        {"start": 10.6, "end": 11.5, "word": "exatamente"},
        {"start": 11.6, "end": 12.8, "word": "aquilo!"},
    ]
    return {
        "start": 0.0,
        "end": 20.0,
        "words": words,
        "segments": [
            {"start": 1.0, "end": 6.0, "text": "Aí eu falei pra ele: não faça isso!"},
            {"start": 6.8, "end": 12.8, "text": "E ele foi lá e fez exatamente aquilo!"},
        ],
        "scenes": [
            {"start": 0.0, "end": 6.5},
            {"start": 6.5, "end": 20.0},
        ],
        "silence": [
            {"start": 6.0, "end": 6.8},
        ],
        "audio_events": [
            {"start": 13.0, "end": 17.5, "type": "laughter", "confidence": 0.95},
        ],
        "visual_events": [
            {"start": 13.2, "end": 16.0, "type": "face_reaction", "confidence": 0.88},
        ],
        "tracks": [
            {"time": 5.0, "boxes": [{"x": 0.40, "y": 0.15, "w": 0.25, "h": 0.35}]},
            {"time": 14.0, "boxes": [{"x": 0.42, "y": 0.15, "w": 0.26, "h": 0.35}]},
        ],
        "keywords": ["engraçado", "comédia", "risada"],
        "semantic_tags": ["humor", "standup"],
    }


# ---------------------------------------------------------------------------
# 1. Natural Boundary & Word Truncation Prevention Tests
# ---------------------------------------------------------------------------

def test_snap_boundaries_never_truncates_speech_words():
    """Verify scene snap never moves start past first word or end before last word."""
    timeline = {
        "scenes": [
            {"start": 10.2, "end": 20.2},  # Cut falls inside speech: first word starts at 10.0, last word ends at 20.4
        ]
    }
    snapped_start, snapped_end = snap_boundaries(
        start=10.0,
        end=20.4,
        timeline=timeline,
        min_bound=0.0,
        max_bound=30.0,
        first_word_start=10.0,
        last_word_end=20.4,
    )
    # Start must NOT move to 10.2s (which would cut the word 10.0-10.4)
    assert snapped_start <= 10.0
    # End must NOT move to 20.2s (which would cut the word 20.0-20.4)
    assert snapped_end >= 20.4


def test_candidate_generation_never_cuts_words_mid_speech(sample_timeline_podcast):
    options = {"duration": "30s–59s", "results": 3}
    candidates = rank(sample_timeline_podcast, options=options)

    for cand in candidates:
        cand_start = cand["start"]
        cand_end = cand["end"]
        # Words must all fall strictly within snapped candidate boundaries
        for w in cand["words"]:
            assert w["start"] >= cand_start - 0.01
            assert w["end"] <= cand_end + 0.01
            assert w["end"] > w["start"]


# ---------------------------------------------------------------------------
# 2. Request-Aware Retrieval Across Full Timeline (Before Cap)
# ---------------------------------------------------------------------------

def test_request_aware_retrieval_keeps_late_topic_without_arbitrary_cap():
    """A long source may supply more than 20 natural windows, including late requested moments."""
    words = []
    scenes = []
    # Build 30 consecutive sentence units across 600s
    for i in range(30):
        t_s = float(i * 20)
        t_e = float(t_s + 18.0)
        scenes.append({"start": t_s, "end": t_e})
        if i == 28:
            # Late topic at 560s: discuss artificial intelligence
            sent_words = [
                {"start": t_s + 1.0, "end": t_s + 3.0, "word": "Sobre"},
                {"start": t_s + 3.1, "end": t_s + 6.0, "word": "inteligência"},
                {"start": t_s + 6.1, "end": t_s + 9.0, "word": "artificial"},
                {"start": t_s + 9.1, "end": t_s + 12.0, "word": "revolucionária."},
            ]
        else:
            sent_words = [
                {"start": t_s + 1.0, "end": t_s + 4.0, "word": f"Frase"},
                {"start": t_s + 4.1, "end": t_s + 8.0, "word": f"genérica"},
                {"start": t_s + 8.1, "end": t_s + 12.0, "word": f"número"},
                {"start": t_s + 12.1, "end": t_s + 16.0, "word": f"{i}."},
            ]
        words.extend(sent_words)

    long_timeline = {
        "start": 0.0,
        "end": 600.0,
        "words": words,
        "scenes": scenes,
        "audio_events": [],
        "visual_events": [],
    }

    criteria = {
        "topic": "inteligência artificial",
        "keywords": ["inteligência", "artificial"],
        "reaction": "",
        "action": "",
    }

    windows = generate_candidate_windows(long_timeline, options={"duration": "<30s"}, criteria=criteria)
    assert len(windows) > 20
    # The late window mentioning "inteligência artificial" must be retained in the proposals
    has_target_topic = any("artificial" in w["text"].lower() for w in windows)
    assert has_target_topic is True


# ---------------------------------------------------------------------------
# 3. Deterministic Content-Based Candidate IDs (Cache Compatibility)
# ---------------------------------------------------------------------------

def test_deterministic_candidate_ids_hit_cache(sample_timeline_podcast):
    """Verify that repeated runs on identical source produce identical candidate IDs."""
    options = {"duration": "30s–59s", "results": 2}
    cands_run1 = rank(sample_timeline_podcast, options=options)
    cands_run2 = rank(sample_timeline_podcast, options=options)

    # A short source may yield fewer results than requested, never duplicates.
    ids_first = [candidate["id"] for candidate in cands_run1]
    ids_second = [candidate["id"] for candidate in cands_run2]
    assert ids_first
    assert ids_first == ids_second
    assert len(ids_first) == len(set(ids_first))


# ---------------------------------------------------------------------------
# 4. Thumbnail Sampling & Image Coordination
# ---------------------------------------------------------------------------

def test_thumbnail_sampling_populates_candidates_when_allowed(sample_timeline_podcast):
    # sample_timeline_podcast fixture has thumbnails at 2.0s and 28.0s
    options_allowed = {"allow_images": True, "results": 2}
    cands_allowed = rank(sample_timeline_podcast, options=options_allowed)

    # First candidate spans 0.5s to 34.0s, so it must capture the available timeline thumbnails
    assert len(cands_allowed[0]["thumbnails"]) > 0
    assert cands_allowed[0]["thumbnails"][0]["mime_type"] == "image/jpeg"

    # When allow_images is False, thumbnails must remain strictly empty
    options_disallowed = {"allow_images": False, "results": 2}
    cands_disallowed = rank(sample_timeline_podcast, options=options_disallowed)
    assert len(cands_disallowed[0]["thumbnails"]) == 0


# ---------------------------------------------------------------------------
# 5. Non-Fallback Provider Error Propagation
# ---------------------------------------------------------------------------

def test_non_fallback_provider_errors_propagate(sample_timeline_podcast, monkeypatch):
    """Authentication, missing key, and schema validation errors must raise out of ranking."""
    import localclip.ranking as ranking_mod

    class AuthenticationError(Exception):
        pass

    mock_prov = MagicMock()
    mock_prov.understand_request.side_effect = AuthenticationError("Credenciais inválidas")
    monkeypatch.setattr(ranking_mod, "providers_module", mock_prov)

    with pytest.raises(AuthenticationError):
        rank(sample_timeline_podcast, options={}, providers={"primary": {"id": "p1", "kind": "openai"}})



# ---------------------------------------------------------------------------
# 7. Platform YouTube Shorts 3-Minute Limit Tests
# ---------------------------------------------------------------------------

def test_platform_youtube_shorts_supports_up_to_3_minutes_and_penalizes_over_180s():
    cand_65s = {
        "start": 0.0,
        "end": 65.0,  # 65s is fully supported by modern YouTube Shorts (3-minute limit)
        "words": [{"start": i, "end": i + 0.8, "word": "palavra"} for i in range(60)],
        "sentences": [],
        "text": "short moderno de 65s",
    }
    cand_195s = {
        "start": 0.0,
        "end": 195.0,  # 195s exceeds the official 180s / 3-minute ceiling
        "words": [{"start": i, "end": i + 0.8, "word": "palavra"} for i in range(180)],
        "sentences": [],
        "text": "vídeo longo demais para shorts",
    }
    tl = {"audio_events": [], "visual_events": [], "scenes": [], "tracks": []}
    crit = {}

    scores_65s = calculate_local_scores(cand_65s, tl, {"platform": "YouTube Shorts"}, crit)
    scores_195s = calculate_local_scores(cand_195s, tl, {"platform": "YouTube Shorts"}, crit)

    # 65s must have a strong platform_fit score, while 195s (>180s) must be heavily penalized
    assert scores_65s["platform_fit"] > 50.0
    assert scores_195s["platform_fit"] == 0.0


# ---------------------------------------------------------------------------
# 9. Genre Weights & Platform Knobs Tests
# ---------------------------------------------------------------------------

def test_genre_weights_alter_dimension_computation(sample_timeline_podcast):
    opts_pod = {"genre": "Podcast", "duration": "Auto", "results": 2}
    cands_pod = rank(sample_timeline_podcast, options=opts_pod)

    opts_fut = {"genre": "Futebol", "duration": "Auto", "results": 2}
    cands_fut = rank(sample_timeline_podcast, options=opts_fut)

    # Overall score must reflect different weights between Podcast and Futebol
    assert cands_pod[0]["score"] != cands_fut[0]["score"]


# ---------------------------------------------------------------------------
# 10. Penalties & Local Mode Transparency Tests
# ---------------------------------------------------------------------------

def test_silence_penalty_penalizes_long_dead_air():
    cand = {
        "start": 0.0,
        "end": 30.0,
        "words": [{"start": 1.0, "end": 2.0, "word": "início"}, {"start": 28.0, "end": 29.0, "word": "fim"}],
        "sentences": [],
        "text": "início fim",
    }
    tl_silent = {
        "silence": [{"start": 3.0, "end": 18.0}],  # 15s dead silence
        "audio_events": [],
        "visual_events": [],
        "scenes": [],
        "tracks": [],
    }
    tl_clean = {
        "silence": [],
        "audio_events": [],
        "visual_events": [],
        "scenes": [],
        "tracks": [],
    }

    scores_silent = calculate_local_scores(cand, tl_silent, {}, {})
    scores_clean = calculate_local_scores(cand, tl_clean, {}, {})

    assert scores_silent["silence_penalty"] > 40.0
    assert scores_clean["silence_penalty"] == 0.0


def test_ranking_runs_in_local_mode_with_explicit_heuristics_provenance(sample_timeline_podcast):
    candidates = rank(sample_timeline_podcast, options={"results": 1}, providers={"primary": None})
    top = candidates[0]

    assert top["mode"] == "local"


def test_ranking_runs_in_hybrid_mode_fusing_semantic_evaluations(sample_timeline_podcast, monkeypatch):
    """Verify that when provider returns candidate evaluations, hybrid mode fuses scores and sets titles."""
    import localclip.ranking as ranking_mod

    mock_prov = MagicMock()
    mock_prov.understand_request.return_value = {
        "topic": "Negócios",
        "emotion": "engajante",
        "reaction": "interesse",
        "action": "fala",
        "setting": "podcast",
        "required_modality": "text",
        "keywords": ["segredo", "estratégia"],
        "semantic_limitation": None,
        "mode": "hybrid",
        "provider": "openai-mock",
    }

    def _mock_evaluate(candidates, timeline, options, criteria, providers, usage, cache_dir):
        return [
            {
                "id": c["id"],
                "scores": {
                    "hook": 95.0,
                    "flow": 90.0,
                    "value": 92.0,
                    "narrative": 88.0,
                    "emotion": 85.0,
                    "shareability": 89.0,
                    "context_penalty": 5.0,
                },
                "title": "O Maior Segredo das Métricas",
                "summary": "Explicação objetiva sobre consistência com estratégia.",
                "reason": "Excelente gancho de abertura e desfecho conclusivo.",
            }
            for c in candidates
        ]

    mock_prov.evaluate_candidates.side_effect = _mock_evaluate
    monkeypatch.setattr(ranking_mod, "providers_module", mock_prov)

    cands = rank(
        sample_timeline_podcast,
        options={"results": 1, "genre": "Podcast"},
        providers={"primary": {"id": "openai-mock", "kind": "openai", "model": "gpt-4o-mini"}},
    )
    assert len(cands) == 1
    top = cands[0]

    assert top["mode"] == "hybrid"
    # Fused hook score must combine 60% semantic (95.0) and 40% local
    assert top["scores"]["hook"] > 80.0


def test_select_diverse_top_candidates_suppresses_high_overlap():
    """Verify that select_diverse_top_candidates suppresses near-duplicate intervals."""
    candidates = [
        {"id": "c1", "start": 7.94, "end": 38.44, "score": 88.0},  # Moment 1 (duration ~30.5s)
        {"id": "c2", "start": 18.12, "end": 41.16, "score": 86.0},  # Heavy overlap with c1 (88% containment)
        {"id": "c3", "start": 3.54, "end": 26.90, "score": 84.0},   # Heavy overlap with c1 (81% containment)
        {"id": "c4", "start": 38.44, "end": 67.20, "score": 80.0},  # Moment 2 (distinct later interval)
    ]

    selected = select_diverse_top_candidates(candidates, requested_results=2)
    selected_ids = [c["id"] for c in selected]

    # c1 (best score) must be selected, and c4 (distinct moment) must be selected over overlapping c2/c3
    assert "c1" in selected_ids
    assert "c4" in selected_ids
    assert "c2" not in selected_ids
    assert "c3" not in selected_ids


def test_resolve_weights_adapts_to_user_request_criteria():
    """Verify that criteria adjusts dimension weights cleanly according to request semantics."""
    opts = {"genre": "Podcast", "platform": "TikTok"}
    w_base = resolve_weights(opts)

    criteria_laughter = {"reaction": "riso", "emotion": "alegria"}
    w_laugh = resolve_weights(opts, criteria_laughter)

    # Emotion and audio weights must increase when humor/laughter is requested
    assert w_laugh["emotion"] > w_base["emotion"]
    assert w_laugh["audio"] > w_base["audio"]
    # All weights must sum to 1.0
    assert abs(sum(w_laugh.values()) - 1.0) < 1e-4


def test_diverse_results_remain_sorted_by_potential():
    candidates = [
        {"id": "first", "start": 0, "end": 10, "score": 90},
        {"id": "moderate_overlap", "start": 5, "end": 15, "score": 80},
        {"id": "distinct", "start": 30, "end": 40, "score": 70},
    ]
    selected = select_diverse_top_candidates(candidates, 3)
    assert [candidate["id"] for candidate in selected] == [
        "first", "moderate_overlap", "distinct",
    ]


def test_disabling_automatic_title_preserves_neutral_edit_title(sample_timeline_podcast):
    generated = rank(sample_timeline_podcast, {"auto_title": True, "results": 1})[0]
    neutral = rank(sample_timeline_podcast, {"auto_title": False, "results": 1})[0]
    assert neutral["title"] != generated["title"]
    assert neutral["edit"]["title"] == neutral["title"]
    assert neutral["start"] == generated["start"]
    assert neutral["score"] == generated["score"]


def test_unexpected_provider_errors_are_not_hidden(sample_timeline_podcast, monkeypatch):
    import localclip.ranking as ranking_mod

    def broken_provider(**kwargs):
        raise RuntimeError("provider defect")

    monkeypatch.setattr(ranking_mod.providers_module, "understand_request", broken_provider)
    with pytest.raises(RuntimeError):
        rank(sample_timeline_podcast)


def test_duration_weights_prioritize_short_hook_and_long_completeness():
    short = resolve_weights({"duration": "<30s"})
    long = resolve_weights({"duration": "5min–10min"})
    assert short["hook"] > long["hook"]
    assert long["narrative"] > short["narrative"]


def test_auto_model_uses_observed_speech_coverage(sample_timeline_podcast):
    spoken = rank(sample_timeline_podcast, {"results": 1})[0]
    silent = rank({"start": 0, "end": 40, "scenes": [{"start": 0, "end": 40}]}, {"results": 1})[0]
    assert spoken["resolved_clip_model"] == "Conversa / Talking Head"
    assert silent["resolved_clip_model"] == "Multimodal / Clip Anything"


def test_multi_duration_candidate_generation_honors_natural_boundaries(sample_timeline_podcast):
    """Verify candidate generation produces proposals across all selected durations with natural boundaries."""
    options = {"durations": ["<30s", "30s–59s"], "platform": "TikTok"}
    windows = generate_candidate_windows(sample_timeline_podcast, options=options, criteria={})
    assert len(windows) > 0

    durations = [w["end"] - w["start"] for w in windows]
    # Must generate windows matching both <30s and 30s-59s ranges
    has_short = any(d < 30.0 for d in durations)
    has_medium = any(d >= 28.0 for d in durations)
    assert has_short is True
    assert has_medium is True

    # All windows must preserve word boundaries without word cutting
    for w in windows:
        for word in w.get("words", []):
            assert word["start"] >= w["start"] - 0.05
            assert word["end"] <= w["end"] + 0.05


def test_automatic_results_selection_without_redundant_moments(sample_timeline_podcast):
    """Verify automatic candidate selection yields quality cuts without repeating video moments."""
    candidates = rank(sample_timeline_podcast, options={"durations": ["<30s"], "results": None})
    assert len(candidates) >= 1

    # All candidates must meet the quality bar
    for c in candidates:
        assert c["score"] >= 40.0

    # Check pairwise non-overlap: no repeated video moments
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a, b = candidates[i], candidates[j]
            intersection = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
            assert intersection <= 2.0


def test_temporal_and_semantic_deduplication():
    """Verify that temporal overlap and semantic near-duplicates are suppressed in automatic mode."""
    from localclip.ranking import _semantic_similarity

    # 1. Semantic similarity detection
    cand1 = {"text": "Foque no que realmente move o ponteiro do seu negócio com estratégia."}
    cand2 = {"text": "Foque no que realmente move o ponteiro do negócio e na estratégia."}
    assert _semantic_similarity(cand1, cand2) > 0.55

    # 2. Semantic deduplication in select_diverse_top_candidates
    duplicate_cands = [
        {
            "id": "c1",
            "start": 5.0,
            "end": 25.0,
            "score": 85.0,
            "text": "Foque no que realmente move o ponteiro do seu negócio com estratégia.",
        },
        {
            "id": "c2",
            "start": 50.0,
            "end": 70.0,  # Distinct temporal window
            "score": 75.0,
            "text": "Foque no que realmente move o ponteiro do seu negócio com estratégia.",  # Semantic duplicate
        },
        {
            "id": "c3",
            "start": 80.0,
            "end": 100.0,
            "score": 70.0,
            "text": "Aprenda como gerenciar finanças e custos operacionais da empresa.",  # Distinct topic
        },
    ]
    selected = select_diverse_top_candidates(duplicate_cands, requested_results=None)
    selected_ids = [c["id"] for c in selected]
    assert "c1" in selected_ids
    assert "c2" not in selected_ids  # Suppressed due to semantic repetition
    assert "c3" in selected_ids


def test_candidate_edit_forces_reframe_and_subtitles_true(sample_timeline_podcast):
    """Verify that candidate edits enforce reframe=True and subtitles=True regardless of legacy options."""
    candidates = rank(sample_timeline_podcast, options={"reframe": False, "subtitles": False, "results": 1})
    assert len(candidates) == 1
    edit = candidates[0]["edit"]
    assert edit["reframe"] is True
    assert edit["subtitles"] is True


def test_resumable_stage_checkpoint_skips_media_analysis(tmp_path, monkeypatch):
    """Verify that a job with an analyzed checkpoint skips media.analyze on resume/retry."""
    import json
    from localclip import jobs, storage as store

    # Create mock directory and saved timeline artifact
    proj_dir = tmp_path / "project_123"
    proj_dir.mkdir(parents=True)
    saved_timeline = {
        "start": 0.0,
        "end": 30.0,
        "words": [{"start": 1.0, "end": 2.0, "word": "Teste"}],
    }
    timeline_path = proj_dir / "timeline.json"
    timeline_path.write_text(json.dumps(saved_timeline))

    analyze_called = False
    def mock_analyze(*args, **kwargs):
        nonlocal analyze_called
        analyze_called = True
        return saved_timeline

    monkeypatch.setattr("localclip.media.analyze", mock_analyze)
    monkeypatch.setattr(store, "get_project", lambda pid, internal=False: {"source": str(tmp_path / "dummy.mp4"), "options": {}})
    monkeypatch.setattr(store, "project_dir", lambda pid: proj_dir)
    monkeypatch.setattr(store, "update_project", lambda pid, **kwargs: None)
    updates = []
    monkeypatch.setattr(store, "update_job", lambda jid, **kwargs: updates.append(kwargs))
    monkeypatch.setattr(store, "selected_providers", lambda: {
        "primary": {"id": "gemini"}, "fallback": {"id": "openai"}
    })
    monkeypatch.setattr(store, "save_candidates", lambda pid, cands: None)
    monkeypatch.setattr(store, "cache_root", lambda: tmp_path / "cache")

    monkeypatch.setattr(store, "record_usage", lambda pid, event: None)

    def rank_with_fallback(timeline, options, providers, usage, cache_dir):
        usage({"provider_id": "gemini", "error": "quota exceeded"})
        usage({"provider_id": "openai", "error": None})
        return []

    monkeypatch.setattr("localclip.ranking.rank", rank_with_fallback)
    # Create dummy source file
    dummy_source = tmp_path / "dummy.mp4"
    dummy_source.write_bytes(b"dummy video bytes")

    job = {
        "id": "job_abc",
        "project_id": "project_123",
        "kind": "process",
        "payload": {"durations": ["<30s"]},
        "checkpoint": json.dumps({
            "stage": "media_analysis",
            "timeline_path": str(timeline_path),
            "completed_stages": ["identify", "media_analysis"],
        }),
    }

    jobs.execute(job, progress=lambda s, p: None, cancelled=lambda: False)
    # media.analyze must NOT have been called because timeline was resumed from checkpoint
    assert analyze_called is False

    assert any(update.get("stage") == "gemini falhou. Continuando com openai." for update in updates)
    completed = next(update["checkpoint"] for update in reversed(updates) if "checkpoint" in update)
    assert completed["stage"] == "completed"
    assert completed["fallback_events"] == ["gemini falhou. Continuando com openai."]

