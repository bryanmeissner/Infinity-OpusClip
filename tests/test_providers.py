"""Unit and contract tests for LocalClip provider adapters and secret management.

Tests cover:
- Secret Service key storage, retrieval, deletion, and unavailability handling
- Strict enforcement of keyring.backends.SecretService.Keyring backend
- Prevention of saving empty keys via stdin in secret-tool fallback
- Explicit SecretServiceUnavailableError on daemon communication failures
- API key masking and sanitization in error logs and traces
- Health check endpoints for OpenAI, Gemini, Anthropic, and Compatible runtimes
- Structured request understanding (local heuristic mode and provider-backed)
- Strict validation of understand_request output (rejecting empty or invalid fields)
- Batched candidate evaluation in {"candidates": [...]} object format
- Strict rejection of missing/duplicate/unknown candidate IDs (no fabrication/remapping)
- Strict rejection of non-finite or out-of-range scores (no default 50 fabrication)
- Sequential fallback on eligible temporary errors (429, 5xx, timeouts)
- Strict non-fallback on invalid credentials (401/403) and schema errors
- Deterministic caching with provider provenance envelopes
- Usage callback telemetry without credential leakage
- Multimodal image sampling only when explicitly authorized by allow_images
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from localclip.providers import (
    AuthenticationError,
    CompatibleAdapter,
    GeminiAdapter,
    OpenAIAdapter,
    AnthropicAdapter,
    OpenRouterAdapter,
    ProviderKeyNotFoundError,
    RateLimitError,
    SchemaValidationError,
    SecretServiceUnavailableError,
    ServiceUnavailableError,
    _compute_cache_key,
    _extract_candidate_images,
    delete_key,
    evaluate_candidates,
    get_key,
    has_key,
    health_check,
    sanitize_text,
    save_key,
    understand_request,
    get_curated_catalog,
    list_provider_models,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_keys(monkeypatch):
    """Clean test key store that monkeypatches module-level get_key and save_key."""
    store: dict[str, str] = {}

    def _mock_save(provider_id: str, key: str) -> None:
        if not provider_id or not provider_id.strip():
            raise ValueError("provider_id must not be empty")
        if not key or not key.strip():
            raise ValueError("key must not be empty")
        store[provider_id.strip()] = key.strip()

    def _mock_get(provider_id: str) -> str | None:
        if not provider_id:
            return None
        return store.get(provider_id.strip())

    def _mock_delete(provider_id: str) -> bool:
        if not provider_id:
            return False
        return store.pop(provider_id.strip(), None) is not None

    def _mock_has(provider_id: str) -> bool:
        k = _mock_get(provider_id)
        return bool(k and k.strip())

    monkeypatch.setattr("localclip.providers.save_key", _mock_save)
    monkeypatch.setattr("localclip.providers.get_key", _mock_get)
    monkeypatch.setattr("localclip.providers.delete_key", _mock_delete)
    monkeypatch.setattr("localclip.providers.has_key", _mock_has)
    return store


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def mock_usage():
    records = []

    def _callback(record: dict):
        records.append(record)

    _callback.records = records
    return _callback


# ---------------------------------------------------------------------------
# Secret Service Security & Backend Enforcement Tests
# ---------------------------------------------------------------------------

def test_save_key_validation():
    with pytest.raises(ValueError):
        save_key("", "valid-key")
    with pytest.raises(ValueError):
        save_key("valid-id", "   ")


def test_save_key_uses_secret_service_backend_explicitly():
    """Verifies that save_key uses keyring.backends.SecretService.Keyring explicitly."""
    mock_backend = MagicMock()
    mock_backend.priority = 1

    with patch("localclip.providers._get_secret_service_keyring", return_value=mock_backend):
        save_key("prov-test", "sk-secret-key-123456789")
        mock_backend.set_password.assert_called_once_with(
            "localclip", "provider:prov-test", "sk-secret-key-123456789"
        )


def test_save_key_secret_tool_fallback_strictly_uses_stdin():
    """Verifies that secret-tool fallback provides clean_key via stdin and never without stdin."""
    with patch("localclip.providers._get_secret_service_keyring", return_value=None):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            save_key("prov-tool", "secret-val-999")

            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert args[0][:2] == ["secret-tool", "store"]
            assert kwargs.get("input") == "secret-val-999"


def test_save_key_raises_secret_service_unavailable_error():
    """Verifies that failure of SecretService and secret-tool raises explicit error and never plaintext."""
    with patch("localclip.providers._get_secret_service_keyring", return_value=None):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SecretServiceUnavailableError):
                save_key("prov-fail", "sk-cannot-save")


def test_get_key_raises_error_on_backend_communication_failure():
    """Verifies that get_key does NOT swallow Secret Service communication failures as missing key."""
    mock_backend = MagicMock()
    mock_backend.get_password.side_effect = Exception("DBus Secret Service daemon crashed")

    with patch("localclip.providers._get_secret_service_keyring", return_value=mock_backend):
        with patch("localclip.providers._run_secret_tool_lookup", return_value=(-1, "")):
            with pytest.raises(SecretServiceUnavailableError):
                get_key("prov-crashed")


def test_get_key_returns_none_when_genuinely_not_found():
    """When Secret Service is operational and key is absent, get_key returns None."""
    mock_backend = MagicMock()
    mock_backend.get_password.return_value = None

    with patch("localclip.providers._get_secret_service_keyring", return_value=mock_backend):
        with patch("localclip.providers._run_secret_tool_lookup", return_value=(1, "")):
            assert get_key("prov-not-found") is None


def test_sanitize_text_strips_api_keys():
    raw_error = (
        "Failed with 401 using Authorization: Bearer sk-proj-1234567890abcdef "
        "and x-goog-api-key: AIzaSyD987654321 and https://api.endpoint.com?key=AIzaSySecretParam"
    )
    cleaned = sanitize_text(raw_error)

    assert "sk-proj-1234567890abcdef" not in cleaned
    assert "AIzaSyD987654321" not in cleaned
    assert "AIzaSySecretParam" not in cleaned
    assert "[REDACTED_API_KEY]" in cleaned


def test_sanitize_text_with_custom_secret_list():
    secret = "my-custom-super-secret-passphrase"
    text = f"Connection failed with token: {secret} at endpoint"
    cleaned = sanitize_text(text, extra_secrets=[secret])

    assert secret not in cleaned
    assert "[REDACTED]" in cleaned


# ---------------------------------------------------------------------------
# Health Check Tests
# ---------------------------------------------------------------------------

def test_health_check_missing_key_returns_safe_failure(mock_keys):
    config = {
        "id": "openai-unset",
        "kind": "openai",
        "model": "gpt-4o-mini",
        "enabled": True,
    }
    result = health_check(config)
    assert result["ok"] is False
    assert result["details"]["error_type"] == "ProviderKeyNotFoundError"


def test_health_check_openai_success(mock_keys):
    mock_keys["openai-p1"] = "sk-test-valid-key-123456789"
    config = {
        "id": "openai-p1",
        "kind": "openai",
        "model": "gpt-4o-mini",
        "enabled": True,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}]}

    with patch("httpx.Client.get", return_value=mock_resp) as mock_get:
        res = health_check(config)
        assert res["ok"] is True
        assert res["provider_id"] == "openai-p1"
        assert res["details"]["models_available"] == 2
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert "Authorization" in kwargs["headers"]
        assert kwargs["headers"]["Authorization"] == "Bearer sk-test-valid-key-123456789"


def test_health_check_gemini_auth_failure(mock_keys):
    mock_keys["gemini-p1"] = "AIzaSyInvalidKey999"
    config = {
        "id": "gemini-p1",
        "kind": "gemini",
        "model": "gemini-1.5-flash",
        "enabled": True,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "API key not valid."

    with patch("httpx.Client.get", return_value=mock_resp):
        res = health_check(config)
        assert res["ok"] is False
        assert res["details"]["status_code"] == 403


def test_health_check_anthropic_headers(mock_keys):
    mock_keys["anthropic-p1"] = "sk-ant-test-key-12345678"
    config = {
        "id": "anthropic-p1",
        "kind": "anthropic",
        "model": "claude-3-5-sonnet",
        "enabled": True,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "claude-3-5-sonnet"}]}

    with patch("httpx.Client.get", return_value=mock_resp) as mock_get:
        res = health_check(config)
        assert res["ok"] is True
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["x-api-key"] == "sk-ant-test-key-12345678"
        assert kwargs["headers"]["anthropic-version"] == "2023-06-01"


def test_health_check_compatible_runtime():
    config = {
        "id": "ollama-local",
        "kind": "compatible",
        "model": "llama3.2",
        "base_url": "http://127.0.0.1:11434/v1",
        "enabled": True,
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "llama3.2"}]}

    with patch("httpx.Client.get", return_value=mock_resp):
        res = health_check(config)
        assert res["ok"] is True
        assert res["details"]["models_available"] == 1


# ---------------------------------------------------------------------------
# Understand Request Tests
# ---------------------------------------------------------------------------

def test_understand_request_no_provider_returns_local_mode(temp_cache_dir, mock_usage):
    providers = {"primary": None, "fallback": None}
    options = {
        "clip_model": "Conversa / Talking Head",
        "genre": "Podcast",
        "duration": "30s–59s",
        "platform": "TikTok",
    }
    criteria = understand_request(
        "quero os momentos mais engraçados da entrevista",
        options,
        providers,
        mock_usage,
        temp_cache_dir,
    )

    assert criteria["mode"] == "local"
    assert criteria["provider"] is None
    assert criteria["semantic_limitation"] is not None
    assert criteria["required_modality"] == "text"
    assert "engraçados" in criteria["keywords"] or "momentos" in criteria["keywords"]
    assert len(mock_usage.records) == 0


def test_understand_request_with_provider_success(mock_keys, temp_cache_dir, mock_usage):
    mock_keys["openai-p1"] = "sk-test-valid-key"
    providers = {
        "primary": {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini", "enabled": True},
        "fallback": None,
    }
    options = {"clip_model": "Auto", "genre": "Cortes", "duration": "Auto", "platform": "Instagram Reels"}

    mock_json = {
        "topic": "Histórias engraçadas sobre viagens",
        "emotion": "humor e surpresa",
        "reaction": "risada e compartilhamento",
        "action": "relato de perrengue",
        "setting": "conversa descontraída",
        "required_modality": "multimodal",
        "keywords": ["viagem", "perrengue", "aeroporto"],
        "target_duration_bias": "Auto",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_json)}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        criteria = understand_request("perrengues de viagem", options, providers, mock_usage, temp_cache_dir)

    assert criteria["mode"] == "hybrid"
    assert criteria["provider"] == "openai-p1"
    assert criteria["semantic_limitation"] is None
    assert criteria["topic"] == "Histórias engraçadas sobre viagens"
    assert len(mock_usage.records) == 1
    assert mock_usage.records[0]["total_tokens"] == 180


def test_understand_request_strict_validation_rejects_empty_fields(mock_keys, temp_cache_dir, mock_usage):
    """Verifies that understand_request does not invent defaults when LLM returns invalid/empty fields."""
    mock_keys["openai-p1"] = "sk-test-valid-key"
    providers = {
        "primary": {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini", "enabled": True},
        "fallback": None,
    }
    options = {"clip_model": "Auto", "genre": "Cortes", "duration": "Auto", "platform": "TikTok"}

    # Missing topic and invalid required_modality
    bad_json = {
        "emotion": "humor",
        "reaction": "risada",
        "action": "conversa",
        "setting": "geral",
        "required_modality": "invalid_modality_type",
        "keywords": [],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(bad_json)}}],
        "usage": {"total_tokens": 50},
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(SchemaValidationError):
            understand_request("perrengues", options, providers, mock_usage, temp_cache_dir)


# ---------------------------------------------------------------------------
# Candidate Evaluation & Batching Tests
# ---------------------------------------------------------------------------

def test_evaluate_candidates_no_provider_returns_empty_list(temp_cache_dir, mock_usage):
    candidates = [{"id": "c1", "start": 0.0, "end": 25.0, "words": []}]
    timeline = {"segments": []}
    options = {"platform": "TikTok", "genre": "Humor"}
    criteria = {"topic": "Humor"}
    providers = {"primary": None, "fallback": None}

    res = evaluate_candidates(candidates, timeline, options, criteria, providers, mock_usage, temp_cache_dir)
    assert res == []
    assert len(mock_usage.records) == 0


def test_evaluate_candidates_batched_success(mock_keys, temp_cache_dir, mock_usage):
    mock_keys["openai-p1"] = "sk-test-valid-key"
    providers = {
        "primary": {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini", "enabled": True},
        "fallback": None,
    }
    candidates = [
        {"id": "c1", "start": 10.0, "end": 40.0, "words": [{"word": "olá", "start": 10.0, "end": 10.5}]},
        {"id": "c2", "start": 50.0, "end": 85.0, "words": [{"word": "mundo", "start": 50.0, "end": 50.5}]},
    ]
    timeline = {"segments": []}
    options = {"platform": "YouTube Shorts", "genre": "Educativo", "allow_images": False}
    criteria = {"topic": "Dicas de Estudo"}

    mock_eval = {
        "candidates": [
            {
                "id": "c1",
                "scores": {
                    "hook": 95.0,
                    "flow": 85.0,
                    "value": 90.0,
                    "narrative": 75.0,
                    "emotion": 80.0,
                    "shareability": 80.0,
                    "context_penalty": 5.0,
                },
                "title": "A melhor técnica para focar",
                "summary": "Explicação objetiva sobre o método pomodoro.",
                "reason": "Gancho claro e ritmo didático.",
            },
            {
                "id": "c2",
                "scores": {
                    "hook": 70.0,
                    "flow": 75.0,
                    "value": 80.0,
                    "narrative": 85.0,
                    "emotion": 60.0,
                    "shareability": 65.0,
                    "context_penalty": 0.0,
                },
                "title": "Dica extra sobre pausas",
                "summary": "Importância dos intervalos regulares.",
                "reason": "Bom fechamento de raciocínio.",
            },
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_eval)}}],
        "usage": {"prompt_tokens": 300, "completion_tokens": 150, "total_tokens": 450},
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        evals = evaluate_candidates(candidates, timeline, options, criteria, providers, mock_usage, temp_cache_dir)

    assert len(evals) == 2
    c1_eval = next(e for e in evals if e["id"] == "c1")
    assert c1_eval["scores"]["hook"] == 95.0
    assert c1_eval["title"] == "A melhor técnica para focar"

    assert len(mock_usage.records) == 1
    assert mock_usage.records[0]["total_tokens"] == 450


def test_evaluate_candidates_rejects_out_of_range_score(mock_keys, temp_cache_dir, mock_usage):
    """Verifies that out-of-range scores (>100 or <0) raise SchemaValidationError rather than faking 50."""
    mock_keys["openai-p1"] = "sk-test-valid-key"
    providers = {
        "primary": {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini", "enabled": True},
        "fallback": None,
    }
    candidates = [{"id": "c1", "start": 0.0, "end": 20.0}]

    bad_eval = {
        "candidates": [
            {
                "id": "c1",
                "scores": {
                    "hook": 115.0,  # Invalid: > 100
                    "flow": 80.0,
                    "value": 80.0,
                    "narrative": 80.0,
                    "emotion": 80.0,
                    "shareability": 80.0,
                    "context_penalty": 0.0,
                },
                "title": "Título",
                "summary": "Resumo",
                "reason": "Razão",
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(bad_eval)}}],
        "usage": {"total_tokens": 100},
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(SchemaValidationError):
            evaluate_candidates(candidates, {}, {}, {}, providers, mock_usage, temp_cache_dir)


def test_evaluate_candidates_rejects_missing_candidate_id(mock_keys, temp_cache_dir, mock_usage):
    """Verifies that missing candidates raise SchemaValidationError rather than fabricating scores."""
    mock_keys["openai-p1"] = "sk-test-valid-key"
    providers = {
        "primary": {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini", "enabled": True},
        "fallback": None,
    }
    candidates = [
        {"id": "cand-alpha", "start": 0.0, "end": 15.0},
        {"id": "cand-beta", "start": 20.0, "end": 35.0},
    ]

    # Only returns one candidate
    bad_eval = {
        "candidates": [
            {
                "id": "cand-alpha",
                "scores": {dim: 80.0 for dim in ("hook", "flow", "value", "narrative", "emotion", "shareability", "context_penalty")},
                "title": "Título",
                "summary": "Resumo",
                "reason": "Razão",
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(bad_eval)}}],
        "usage": {"total_tokens": 100},
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(SchemaValidationError):
            evaluate_candidates(candidates, {}, {}, {}, providers, mock_usage, temp_cache_dir)


def test_evaluate_candidates_rejects_unknown_candidate_id(mock_keys, temp_cache_dir, mock_usage):
    """Verifies that hallucinated candidate IDs are rejected rather than silently remapped."""
    mock_keys["openai-p1"] = "sk-test-valid-key"
    providers = {
        "primary": {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini", "enabled": True},
        "fallback": None,
    }
    candidates = [{"id": "cand-alpha", "start": 0.0, "end": 15.0}]

    bad_eval = {
        "candidates": [
            {
                "id": "cand-unknown-hallucinated",
                "scores": {dim: 80.0 for dim in ("hook", "flow", "value", "narrative", "emotion", "shareability", "context_penalty")},
                "title": "Título",
                "summary": "Resumo",
                "reason": "Razão",
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(bad_eval)}}],
        "usage": {"total_tokens": 100},
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(SchemaValidationError):
            evaluate_candidates(candidates, {}, {}, {}, providers, mock_usage, temp_cache_dir)


# ---------------------------------------------------------------------------
# Sequential Fallback Contracts
# ---------------------------------------------------------------------------

def test_sequential_fallback_on_429_rate_limit(mock_keys, temp_cache_dir, mock_usage):
    mock_keys["p-primary"] = "sk-primary-key"
    mock_keys["p-fallback"] = "AIzaSyFallbackKey"

    providers = {
        "primary": {"id": "p-primary", "kind": "openai", "model": "gpt-4o", "enabled": True},
        "fallback": {"id": "p-fallback", "kind": "gemini", "model": "gemini-flash", "enabled": True},
    }
    candidates = [{"id": "c1", "start": 0.0, "end": 30.0, "words": []}]
    timeline = {"segments": []}
    options = {"platform": "TikTok", "genre": "Auto"}
    criteria = {"topic": "Viral"}

    resp_primary = MagicMock()
    resp_primary.status_code = 429
    resp_primary.text = "Rate limit exceeded"

    resp_fallback = MagicMock()
    resp_fallback.status_code = 200
    mock_eval = {
        "candidates": [
            {
                "id": "c1",
                "scores": {"hook": 80.0, "flow": 80.0, "value": 80.0, "narrative": 80.0, "emotion": 80.0, "shareability": 80.0, "context_penalty": 0.0},
                "title": "Fallback Succeeded Title",
                "summary": "Resumo do clipe pelo provedor secundário",
                "reason": "Avaliado após fallback",
            }
        ]
    }
    resp_fallback.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(mock_eval)}]}}],
        "usageMetadata": {"promptTokenCount": 200, "candidatesTokenCount": 100, "totalTokenCount": 300},
    }

    def side_effect(url, **kwargs):
        if "api.openai.com" in url:
            return resp_primary
        return resp_fallback

    with patch("httpx.Client.post", side_effect=side_effect):
        evals = evaluate_candidates(candidates, timeline, options, criteria, providers, mock_usage, temp_cache_dir)

    assert len(evals) == 1
    assert evals[0]["title"] == "Fallback Succeeded Title"

    assert len(mock_usage.records) == 2
    assert mock_usage.records[0]["provider_id"] == "p-primary"
    assert mock_usage.records[0]["error"] is not None
    assert mock_usage.records[1]["provider_id"] == "p-fallback"
    assert mock_usage.records[1]["error"] is None


def test_sequential_fallback_on_invalid_credentials_401(mock_keys, temp_cache_dir, mock_usage):
    """When primary provider fails with 401/auth, sequential fallback must succeed on secondary provider."""
    mock_keys["p-primary"] = "sk-invalid-credentials"
    mock_keys["p-fallback"] = "sk-valid-fallback"

    providers = {
        "primary": {"id": "p-primary", "kind": "openai", "model": "gpt-4o", "enabled": True},
        "fallback": {"id": "p-fallback", "kind": "compatible", "model": "llama3", "enabled": True},
    }
    candidates = [{"id": "c1", "start": 0.0, "end": 30.0, "words": []}]
    timeline = {"segments": []}
    options = {"platform": "TikTok", "genre": "Auto"}
    criteria = {"topic": "Viral"}

    resp_primary = MagicMock()
    resp_primary.status_code = 401
    resp_primary.text = "Incorrect API key provided"

    resp_fallback = MagicMock()
    resp_fallback.status_code = 200
    mock_eval = {
        "candidates": [
            {
                "id": "c1",
                "scores": {"hook": 85.0, "flow": 85.0, "value": 85.0, "narrative": 85.0, "emotion": 85.0, "shareability": 85.0, "context_penalty": 0.0},
                "title": "Fallback Succeeded Title",
                "summary": "Resumo do clipe pelo provedor secundário",
                "reason": "Avaliado após fallback de credencial",
            }
        ]
    }
    resp_fallback.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_eval)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }

    def side_effect(url, **kwargs):
        if "api.openai.com" in str(url):
            return resp_primary
        return resp_fallback

    with patch("httpx.Client.post", side_effect=side_effect):
        evals = evaluate_candidates(candidates, timeline, options, criteria, providers, mock_usage, temp_cache_dir)

    assert len(evals) == 1
    assert evals[0]["title"] == "Fallback Succeeded Title"
    assert len(mock_usage.records) == 2
    assert mock_usage.records[0]["provider_id"] == "p-primary"
    assert mock_usage.records[0]["error"] is not None
    assert mock_usage.records[1]["provider_id"] == "p-fallback"
    assert mock_usage.records[1]["error"] is None


def test_all_providers_auth_failure_raises_authentication_error(mock_keys, temp_cache_dir, mock_usage):
    """When all providers fail with 401/auth, AuthenticationError must be raised."""
    mock_keys["p-primary"] = "sk-invalid-credentials"
    mock_keys["p-fallback"] = "sk-invalid-fallback"

    providers = {
        "primary": {"id": "p-primary", "kind": "openai", "model": "gpt-4o", "enabled": True},
        "fallback": {"id": "p-fallback", "kind": "compatible", "model": "llama3", "enabled": True},
    }
    candidates = [{"id": "c1", "start": 0.0, "end": 30.0, "words": []}]
    timeline = {"segments": []}
    options = {"platform": "TikTok", "genre": "Auto"}
    criteria = {"topic": "Viral"}

    resp_401 = MagicMock()
    resp_401.status_code = 401
    resp_401.text = "Incorrect API key provided"

    with patch("httpx.Client.post", return_value=resp_401) as mock_post:
        with pytest.raises(AuthenticationError):
            evaluate_candidates(candidates, timeline, options, criteria, providers, mock_usage, temp_cache_dir)
        assert mock_post.call_count == 2

def test_no_fallback_on_schema_validation_error(mock_keys, temp_cache_dir, mock_usage):
    mock_keys["p-primary"] = "sk-valid-primary"
    mock_keys["p-fallback"] = "sk-valid-fallback"

    providers = {
        "primary": {"id": "p-primary", "kind": "openai", "model": "gpt-4o", "enabled": True},
        "fallback": {"id": "p-fallback", "kind": "gemini", "model": "gemini-flash", "enabled": True},
    }
    candidates = [{"id": "c1", "start": 0.0, "end": 30.0, "words": []}]
    timeline = {"segments": []}
    options = {"platform": "TikTok", "genre": "Auto"}
    criteria = {"topic": "Viral"}

    resp_primary = MagicMock()
    resp_primary.status_code = 200
    resp_primary.json.return_value = {
        "choices": [{"message": {"content": "Não sou JSON válido."}}],
        "usage": {"total_tokens": 50},
    }

    with patch("httpx.Client.post", return_value=resp_primary) as mock_post:
        with pytest.raises(SchemaValidationError):
            evaluate_candidates(candidates, timeline, options, criteria, providers, mock_usage, temp_cache_dir)

        assert mock_post.call_count == 1


def test_temporary_error_exhaustion_preserves_job_for_retry(mock_keys, temp_cache_dir, mock_usage):
    from localclip.providers import TemporaryProviderError
    mock_keys["p-primary"] = "sk-key-1"
    mock_keys["p-fallback"] = "sk-key-2"

    providers = {
        "primary": {"id": "p-primary", "kind": "openai", "model": "gpt-4o", "enabled": True},
        "fallback": {"id": "p-fallback", "kind": "compatible", "model": "mistral", "enabled": True},
    }
    candidates = [{"id": "c1", "start": 0.0, "end": 30.0, "words": []}]

    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.text = "Service Temporarily Unavailable"

    with patch("httpx.Client.post", return_value=resp_503):
        with pytest.raises(TemporaryProviderError):
            evaluate_candidates(candidates, {}, {}, {}, providers, mock_usage, temp_cache_dir)
    assert [record["provider_id"] for record in mock_usage.records] == ["p-primary", "p-fallback"]

def test_multiple_duration_constraints_reach_remote_prompt_and_local_criteria():
    from localclip.providers import _build_understand_prompt_text, _build_local_request_criteria

    options = {"duration": "Auto", "durations": ["<30s", "90s-3min"]}
    prompt = _build_understand_prompt_text("história completa", options)
    criteria = _build_local_request_criteria("história completa", options)
    assert "Duração pretendida: <30s, 90s-3min" in prompt
    assert criteria["target_duration_bias"] == "<30s, 90s-3min"


# ---------------------------------------------------------------------------
# Multimodal Image Evidence Consent Tests
# ---------------------------------------------------------------------------

def test_image_sampling_when_allow_images_false():
    candidate = {
        "id": "c1",
        "thumbnails": [{"time": 5.0, "image_b64": "A" * 100, "mime_type": "image/jpeg"}],
    }
    images = _extract_candidate_images(candidate)
    assert len(images) == 1

    from localclip.providers import _build_evaluate_messages_openai

    messages = _build_evaluate_messages_openai([candidate], {}, {"allow_images": False}, {})
    user_msg = messages[1]["content"]
    assert isinstance(user_msg, str)
    assert "image_url" not in user_msg


def test_image_sampling_when_allow_images_true():
    sample_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    candidate = {
        "id": "c1",
        "thumbnails": [
            {"time": 2.0, "image_b64": sample_b64, "mime_type": "image/jpeg"},
            {"time": 10.0, "image_b64": sample_b64, "mime_type": "image/jpeg"},
            {"time": 15.0, "image_b64": sample_b64, "mime_type": "image/jpeg"},
        ],
    }
    extracted = _extract_candidate_images(candidate)
    assert len(extracted) == 2

    from localclip.providers import (
        _build_evaluate_contents_gemini,
        _build_evaluate_items_anthropic,
        _build_evaluate_messages_openai,
    )

    oai_msgs = _build_evaluate_messages_openai([candidate], {}, {"allow_images": True}, {})
    user_parts = oai_msgs[1]["content"]
    assert isinstance(user_parts, list)
    assert any(p.get("type") == "image_url" for p in user_parts)

    gem_parts = _build_evaluate_contents_gemini([candidate], {}, {"allow_images": True}, {})
    gem_user_parts = gem_parts[0]["parts"]
    assert any("inline_data" in p for p in gem_user_parts)

    ant_items = _build_evaluate_items_anthropic([candidate], {}, {"allow_images": True}, {})
    assert any(i.get("type") == "image" for i in ant_items)


# ---------------------------------------------------------------------------
# Caching Tests
# ---------------------------------------------------------------------------

def test_cache_avoids_repeated_api_calls(mock_keys, temp_cache_dir, mock_usage):
    mock_keys["openai-p1"] = "sk-test-cache-key"
    providers = {
        "primary": {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini", "enabled": True},
        "fallback": None,
    }
    options = {"clip_model": "Auto", "genre": "Tech", "duration": "Auto", "platform": "TikTok"}

    mock_json = {
        "topic": "Inteligência Artificial Local",
        "emotion": "curiosidade",
        "reaction": "interesse",
        "action": "demonstração",
        "setting": "computador",
        "required_modality": "text",
        "keywords": ["ia", "local"],
        "target_duration_bias": "Auto",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_json)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res1 = understand_request("ia local no linux", options, providers, mock_usage, temp_cache_dir)
        assert mock_post.call_count == 1
        assert len(mock_usage.records) == 1
        assert mock_usage.records[0]["calls"] == 1

        res2 = understand_request("ia local no linux", options, providers, mock_usage, temp_cache_dir)
        assert mock_post.call_count == 1
        assert res1 == res2
        assert len(mock_usage.records) == 2
        assert mock_usage.records[1]["calls"] == 0


def test_cache_fallback_provenance(mock_keys, temp_cache_dir, mock_usage):
    """Verifies that results executed via fallback provider are cached under fallback identity."""
    mock_keys["p-pri"] = "sk-primary"
    mock_keys["p-fb"] = "AIzaSyFallback"

    providers = {
        "primary": {"id": "p-pri", "kind": "openai", "model": "gpt-4o", "enabled": True},
        "fallback": {"id": "p-fb", "kind": "gemini", "model": "gemini-flash", "enabled": True},
    }
    options = {"genre": "Humor"}

    resp_pri_429 = MagicMock(status_code=429, text="Rate limit")

    fb_json = {
        "topic": "Humor",
        "emotion": "alegria",
        "reaction": "risos",
        "action": "piada",
        "setting": "palco",
        "required_modality": "text",
        "keywords": ["show"],
        "target_duration_bias": "Auto",
    }
    resp_fb_200 = MagicMock()
    resp_fb_200.status_code = 200
    resp_fb_200.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(fb_json)}]}}],
        "usageMetadata": {"totalTokenCount": 80},
    }

    def side_effect(url, **kwargs):
        if "api.openai.com" in url:
            return resp_pri_429
        return resp_fb_200

    with patch("httpx.Client.post", side_effect=side_effect):
        res1 = understand_request("pedido com fallback", options, providers, mock_usage, temp_cache_dir)
        assert res1["provider"] == "p-fb"

    # Second call should find cache for fallback
    # Simulate primary continuing to fail 429
    with patch("httpx.Client.post", return_value=resp_pri_429) as mock_post:
        res2 = understand_request("pedido com fallback", options, providers, mock_usage, temp_cache_dir)
        assert res2["topic"] == "Humor"
        # Network post for fallback should NOT have occurred because cache hit for p-fb
        assert mock_post.call_count == 1  # only primary 429 attempted

def test_evaluate_candidates_cache_hit_and_order_preservation(mock_keys, temp_cache_dir, mock_usage):
    """Verifies that evaluations are returned in canonical candidate order and cached deterministically."""
    mock_keys["openai-p1"] = "sk-test-cache-stable"
    providers = {
        "primary": {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini", "enabled": True},
        "fallback": None,
    }
    candidates = [
        {"id": "cand-first", "start": 10.0, "end": 40.0, "words": [{"word": "olá"}]},
        {"id": "cand-second", "start": 50.0, "end": 80.0, "words": [{"word": "mundo"}]},
    ]
    options = {"platform": "TikTok", "genre": "Tech"}
    criteria = {"topic": "Coding"}

    # Provider returns candidate evaluations in reversed order
    mock_eval = {
        "candidates": [
            {
                "id": "cand-second",
                "scores": {dim: 75.0 for dim in ("hook", "flow", "value", "narrative", "emotion", "shareability", "context_penalty")},
                "title": "Segundo Título",
                "summary": "Segundo Resumo",
                "reason": "Segunda Razão",
            },
            {
                "id": "cand-first",
                "scores": {dim: 80.0 for dim in ("hook", "flow", "value", "narrative", "emotion", "shareability", "context_penalty")},
                "title": "Primeiro Título",
                "summary": "Primeiro Resumo",
                "reason": "Primeira Razão",
            },
        ]
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_eval)}}],
        "usage": {"total_tokens": 200},
    }

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res1 = evaluate_candidates(candidates, {}, options, criteria, providers, mock_usage, temp_cache_dir)
        assert mock_post.call_count == 1
        # Order is canonicalized to requested candidate order
        assert res1[0]["id"] == "cand-first"
        assert res1[0]["title"] == "Primeiro Título"
        assert res1[1]["id"] == "cand-second"
        assert res1[1]["title"] == "Segundo Título"

        # Second call hits deterministic cache with zero network calls
        res2 = evaluate_candidates(candidates, {}, options, criteria, providers, mock_usage, temp_cache_dir)
        assert mock_post.call_count == 1  # Cache HIT! No additional network post
        assert res2[0]["id"] == "cand-first"
        assert res2[0]["title"] == "Primeiro Título"
        assert res2[1]["id"] == "cand-second"
        assert res2[1]["title"] == "Segundo Título"


def test_fallback_on_gemini_400_invalid_api_key(mock_keys, temp_cache_dir, mock_usage):
    """Verifies that Gemini HTTP 400 invalid API key triggers sequential fallback to secondary provider."""
    mock_keys["p-primary"] = "AIzaSyInvalidKey"
    mock_keys["p-fallback"] = "sk-valid-fallback"

    providers = {
        "primary": {"id": "p-primary", "kind": "gemini", "model": "gemini-1.5-flash", "enabled": True},
        "fallback": {"id": "p-fallback", "kind": "compatible", "model": "llama3", "enabled": True},
    }
    candidates = [{"id": "c1", "start": 0.0, "end": 30.0, "words": []}]

    resp_gemini_400 = MagicMock()
    resp_gemini_400.status_code = 400
    resp_gemini_400.text = json.dumps({
        "error": {
            "code": 400,
            "message": "API key not valid. Please pass a valid API key.",
            "status": "INVALID_ARGUMENT",
            "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}],
        }
    })

    resp_fallback = MagicMock()
    resp_fallback.status_code = 200
    mock_eval = {
        "candidates": [
            {
                "id": "c1",
                "scores": {"hook": 80.0, "flow": 80.0, "value": 80.0, "narrative": 80.0, "emotion": 80.0, "shareability": 80.0, "context_penalty": 0.0},
                "title": "Fallback Recovered Title",
                "summary": "Resumo recuperado",
                "reason": "Recuperado após falha Gemini",
            }
        ]
    }
    resp_fallback.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_eval)}}],
        "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
    }

    def side_effect(url, **kwargs):
        if "generativelanguage.googleapis.com" in str(url):
            return resp_gemini_400
        return resp_fallback

    with patch("httpx.Client.post", side_effect=side_effect):
        evals = evaluate_candidates(candidates, {}, {}, {}, providers, mock_usage, temp_cache_dir)

    assert len(evals) == 1
    assert evals[0]["title"] == "Fallback Recovered Title"
    assert len(mock_usage.records) == 2
    assert mock_usage.records[0]["provider_id"] == "p-primary"
    assert mock_usage.records[0]["error"] is not None
    assert mock_usage.records[1]["provider_id"] == "p-fallback"
    assert mock_usage.records[1]["error"] is None

def test_auto_title_false_instructs_neutral_titles(mock_keys, temp_cache_dir, mock_usage):
    """Verifies that auto_title=False generates neutral title instructions and is tracked in cache payload."""
    mock_keys["openai-p1"] = "sk-test-valid-key"
    providers = {
        "primary": {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini", "enabled": True},
        "fallback": None,
    }
    candidates = [{"id": "c1", "start": 0.0, "end": 20.0, "words": []}]
    options = {"platform": "TikTok", "genre": "Tech", "auto_title": False}

    mock_eval = {
        "candidates": [
            {
                "id": "c1",
                "scores": {dim: 80.0 for dim in ("hook", "flow", "value", "narrative", "emotion", "shareability", "context_penalty")},
                "title": "Corte c1",
                "summary": "Resumo",
                "reason": "Razão",
            }
        ]
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(mock_eval)}}],
        "usage": {"total_tokens": 100},
    }

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = evaluate_candidates(candidates, {}, options, {}, providers, mock_usage, temp_cache_dir)
        assert len(res) == 1
        assert res[0]["title"] == "Corte c1"
        _, kwargs = mock_post.call_args
        prompt_text = kwargs["json"]["messages"][1]["content"]
        assert "auto_title desativado" in prompt_text

def test_understand_request_local_mode_detects_semantic_intents_and_duration_bias(temp_cache_dir, mock_usage):
    """Verify that local heuristic criteria extraction detects emotional cues, reactions, and duration bias."""
    providers = {"primary": None, "fallback": None}
    options_humor = {"clip_model": "Auto", "genre": "Entretenimento", "duration": "<30s", "platform": "TikTok"}

    crit_humor = understand_request(
        "pegue as partes em que todos começam a rir",
        options_humor,
        providers,
        mock_usage,
        temp_cache_dir,
    )
    assert crit_humor["mode"] == "local"
    assert crit_humor["reaction"] == "riso"
    assert crit_humor["emotion"] == "alegria"
    assert crit_humor["required_modality"] == "audio"
    assert crit_humor["target_duration_bias"] == "<30s>" or crit_humor["target_duration_bias"] == "<30s"

    options_action = {"clip_model": "Auto", "genre": "Esportes", "duration": "30s–59s", "platform": "TikTok"}
    crit_action = understand_request(
        "pegue os melhores gols e jogadas",
        options_action,
        providers,
        mock_usage,
        temp_cache_dir,
    )
    assert crit_action["reaction"] == "ação"
    assert crit_action["emotion"] == "entusiasmo"
    assert crit_action["required_modality"] == "visual"
    assert crit_action["target_duration_bias"] == "30s–59s"


# ---------------------------------------------------------------------------
# Model Catalog & Discovery Tests
# ---------------------------------------------------------------------------

def test_get_curated_catalog_contains_all_providers():
    """Verify that get_curated_catalog returns curated models for all supported providers."""
    catalog = get_curated_catalog()
    for kind in ("openai", "gemini", "anthropic", "compatible"):
        assert kind in catalog
        models = catalog[kind]
        assert len(models) >= 3
        for m in models:
            assert "id" in m and len(m["id"]) > 0
            assert "name" in m and len(m["name"]) > 0
            assert "description" in m
            assert isinstance(m["recommended"], bool)


def test_list_provider_models_unauthenticated_returns_curated_fallback():
    """When no API key is available in Secret Service, list_provider_models returns curated fallback safely."""
    config = {"id": "openai-no-key", "kind": "openai", "model": "gpt-4o-mini"}
    result = list_provider_models(config)
    assert result["provider"] == "openai-no-key"
    assert result["kind"] == "openai"
    assert result["source"] == "unauthenticated"
    assert len(result["curated"]) > 0
    assert result["discovered"] == []
    assert "Chave de API não configurada" in result["error"]


def test_list_provider_models_openai_live_success(mock_keys):
    """OpenAI live discovery filters out non-chat models and marks source as api."""
    mock_keys["openai-p1"] = "sk-test-valid-key-999"
    config = {"id": "openai-p1", "kind": "openai", "model": "gpt-4o-mini"}

    fake_openai_resp = MagicMock()
    fake_openai_resp.status_code = 200
    fake_openai_resp.json.return_value = {
        "data": [
            {"id": "text-embedding-3-small"},
            {"id": "gpt-4o-mini"},
            {"id": "whisper-1"},
            {"id": "gpt-4o"},
            {"id": "dall-e-3"},
            {"id": "o1-mini"},
        ]
    }

    with patch("httpx.Client.get", return_value=fake_openai_resp):
        res = list_provider_models(config)

    assert res["source"] == "api"
    assert res["error"] is None
    discovered_ids = [m["id"] for m in res["discovered"]]
    assert "gpt-4o-mini" in discovered_ids
    assert "gpt-4o" in discovered_ids
    assert "o1-mini" in discovered_ids
    # Non-chat models must be filtered out
    assert "text-embedding-3-small" not in discovered_ids
    assert "whisper-1" not in discovered_ids
    assert "dall-e-3" not in discovered_ids


def test_list_provider_models_gemini_live_success(mock_keys):
    """Gemini live discovery filters by generateContent capability and strips models/ prefix."""
    mock_keys["gemini-p1"] = "AIzaSyValidGeminiKey"
    config = {"id": "gemini-p1", "kind": "gemini", "model": "gemini-2.5-flash"}

    fake_gemini_resp = MagicMock()
    fake_gemini_resp.status_code = 200
    fake_gemini_resp.json.return_value = {
        "models": [
            {
                "name": "models/gemini-2.5-flash",
                "displayName": "Gemini 2.5 Flash",
                "description": "Fast generation",
                "supportedGenerationMethods": ["generateContent", "countTokens"],
                "inputTokenLimit": 1048576,
            },
            {
                "name": "models/text-embedding-004",
                "displayName": "Text Embedding",
                "supportedGenerationMethods": ["embedContent"],
            },
            {
                "name": "models/gemini-2.5-pro",
                "displayName": "Gemini 2.5 Pro",
                "supportedGenerationMethods": ["generateContent"],
                "inputTokenLimit": 2097152,
            },
        ]
    }

    with patch("httpx.Client.get", return_value=fake_gemini_resp):
        res = list_provider_models(config)

    assert res["source"] == "api"
    assert res["error"] is None
    ids = [m["id"] for m in res["discovered"]]
    assert "gemini-2.5-flash" in ids
    assert "gemini-2.5-pro" in ids
    assert "text-embedding-004" not in ids


def test_list_provider_models_anthropic_live_success(mock_keys):
    """Anthropic live discovery lists available models via official models endpoint."""
    mock_keys["anthropic-p1"] = "sk-ant-test-key-valid"
    config = {"id": "anthropic-p1", "kind": "anthropic", "model": "claude-3-5-haiku-20241022"}

    fake_ant_resp = MagicMock()
    fake_ant_resp.status_code = 200
    fake_ant_resp.json.return_value = {
        "data": [
            {
                "type": "model",
                "id": "claude-3-5-haiku-20241022",
                "display_name": "Claude 3.5 Haiku",
                "created_at": "2024-10-22T00:00:00Z",
            },
            {
                "type": "model",
                "id": "claude-3-7-sonnet-20250219",
                "display_name": "Claude 3.7 Sonnet",
                "created_at": "2025-02-19T00:00:00Z",
            },
        ]
    }

    with patch("httpx.Client.get", return_value=fake_ant_resp):
        res = list_provider_models(config)

    assert res["source"] == "api"
    assert res["error"] is None
    ids = [m["id"] for m in res["discovered"]]
    assert "claude-3-5-haiku-20241022" in ids
    assert "claude-3-7-sonnet-20250219" in ids


def test_list_provider_models_compatible_ollama_fallback():
    """Compatible provider falls back from /v1/models to Ollama /api/tags if standard endpoint fails."""
    config = {
        "id": "compatible",
        "kind": "compatible",
        "model": "llama3.2",
        "base_url": "http://localhost:11434/v1",
    }

    resp_404 = MagicMock()
    resp_404.status_code = 404

    resp_ollama = MagicMock()
    resp_ollama.status_code = 200
    resp_ollama.json.return_value = {
        "models": [
            {
                "name": "llama3.2:latest",
                "model": "llama3.2:latest",
                "details": {"family": "llama", "parameter_size": "3.2B"},
            },
            {
                "name": "deepseek-r1:7b",
                "model": "deepseek-r1:7b",
                "details": {"family": "qwen2", "parameter_size": "7B"},
            },
        ]
    }

    def mock_get(url, **kwargs):
        if url.endswith("/models"):
            return resp_404
        elif url.endswith("/api/tags"):
            return resp_ollama
        return resp_404

    with patch("httpx.Client.get", side_effect=mock_get):
        res = list_provider_models(config)

    assert res["source"] == "api"
    assert res["error"] is None
    ids = [m["id"] for m in res["discovered"]]
    assert "llama3.2:latest" in ids
    assert "deepseek-r1:7b" in ids


def test_list_provider_models_sanitizes_errors_never_leaks_key(mock_keys):
    """When an error occurs during model discovery, any secret key in trace is sanitized."""
    mock_keys["openai-leak"] = "sk-super-secret-api-token-should-not-leak"
    config = {"id": "openai-leak", "kind": "openai", "model": "gpt-4o"}

    with patch("httpx.Client.get", side_effect=RuntimeError("Connection failed with Bearer sk-super-secret-api-token-should-not-leak")):
        res = list_provider_models(config)

    assert res["source"] == "curated_fallback"
    assert "sk-super-secret-api-token-should-not-leak" not in res["error"]
    assert "[REDACTED]" in res["error"]
    assert len(res["curated"]) > 0


def test_list_provider_models_auth_error_not_masked_as_fallback(mock_keys):
    """When API returns 401/403, list_provider_models surfaces source='auth_error' and does not hide it as generic fallback."""
    mock_keys["openai-bad-auth"] = "sk-invalid-key"
    config = {"id": "openai-bad-auth", "kind": "openai", "model": "gpt-4o-mini"}

    fake_resp = MagicMock()
    fake_resp.status_code = 401

    with patch("httpx.Client.get", return_value=fake_resp):
        res = list_provider_models(config)

    assert res["source"] == "auth_error"
    assert "Autenticação rejeitada" in res["error"]


@pytest.mark.parametrize("model,sends_temperature", [
    ("o3-mini", False),
    ("gpt-5.6-luna", False),
    ("gpt-6-luna", False),
    ("gpt-4o-mini", True),
])
def test_call_chat_omits_temperature_for_reasoning_models(model, sends_temperature):
    """Reasoning families reject a custom temperature with HTTP 400; older chat models keep 0.2."""
    adapter = OpenAIAdapter({"id": "p", "kind": "openai", "model": model}, api_key="sk-test")
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "choices": [{"message": {"content": "{\"candidates\": []}"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }
    with patch("httpx.Client.post", return_value=fake_resp) as mock_post:
        adapter._call_chat([{"role": "user", "content": "hi"}])
    sent_payload = mock_post.call_args.kwargs["json"]
    assert ("temperature" in sent_payload) is sends_temperature


def test_anthropic_bare_host_and_no_sampling_parameters():
    """A bare Anthropic host must still hit /v1/messages, and Claude 5.x rejects non-default temperature."""
    adapter = AnthropicAdapter(
        {"id": "a", "kind": "anthropic", "model": "claude-sonnet-5-5", "base_url": "https://api.anthropic.com"},
        api_key="sk-ant-test",
    )
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"content": [{"type": "text", "text": "{}"}], "usage": {}}
    with patch("httpx.Client.post", return_value=fake_resp) as mock_post:
        adapter._call_messages("sys", [{"type": "text", "text": "hi"}])
    assert mock_post.call_args.args[0] == "https://api.anthropic.com/v1/messages"
    assert "temperature" not in mock_post.call_args.kwargs["json"]


def test_sanitize_oauth_tokens():
    """sanitize_text masks Google ya29 OAuth tokens."""
    raw = "Token is ya29.a0AX07CmvSTestToken12345678901234567890 and is secret"
    sanitized = sanitize_text(raw)
    assert "ya29." not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized


# ---------------------------------------------------------------------------
# OMP bridge (account logins without API keys)
# ---------------------------------------------------------------------------

def _fake_omp(tmp_path: Path, assistant: dict, record: Path) -> str:
    """Writes an executable that mimics `omp -p --mode json` and records argv/stdin."""
    script = tmp_path / "omp"
    end_event = json.dumps({"type": "agent_end", "messages": [{"role": "user"}, {"role": "assistant", **assistant}]})
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"open({str(record)!r}, 'w').write(json.dumps({{'argv': sys.argv[1:], 'stdin': sys.stdin.read()}}))\n"
        "print(json.dumps({'type': 'agent_start'}))\n"
        f"print({end_event!r})\n"
        f"sys.exit({1 if assistant.get('stopReason') == 'error' else 0})\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script)


def test_omp_adapter_runs_prompt_without_touching_keyring(tmp_path, monkeypatch):
    from localclip import providers

    record = tmp_path / "call.json"
    answer = {"candidates": []}
    omp = _fake_omp(tmp_path, {
        "stopReason": "stop",
        "content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "```json\n" + json.dumps(answer) + "\n```"}],
        "usage": {"input": 11, "output": 7, "totalTokens": 18},
    }, record)
    monkeypatch.setattr(providers, "get_omp_path", lambda: omp)
    monkeypatch.setattr(providers, "get_key", MagicMock(side_effect=AssertionError("keyring must not be read")))

    adapter = providers._create_adapter({"id": "omp", "kind": "omp", "model": "google-antigravity/gemini-3.8-flash"})
    text, tokens = adapter._run("system", "pedido do usuário")

    assert json.loads(providers._extract_json_substring(text)) == answer
    assert tokens == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    call = json.loads(record.read_text())
    assert call["stdin"] == "pedido do usuário"
    assert call["argv"][call["argv"].index("--model") + 1] == "google-antigravity/gemini-3.8-flash"
    assert "--no-tools" in call["argv"]


@pytest.mark.parametrize("message,expected", [
    ("Cloud Code Assist API error (429): Individual quota reached", RateLimitError),
    ("Codex error event: The usage limit has been reached (code=usage_limit_reached)", RateLimitError),
    ('No active credential found for provider "anthropic".', AuthenticationError),
    ("Cloud Code Assist stream ended without a finish reason (connection dropped)", ServiceUnavailableError),
])
def test_omp_errors_map_to_fallback_policy(tmp_path, monkeypatch, message, expected):
    """Quota/outage errors must stay fallback-eligible; missing login must not silently fall back."""
    from localclip import providers

    omp = _fake_omp(tmp_path, {"stopReason": "error", "errorMessage": message, "content": []}, tmp_path / "c.json")
    monkeypatch.setattr(providers, "get_omp_path", lambda: omp)
    adapter = providers.OmpAdapter({"id": "omp", "kind": "omp", "model": "google-antigravity/gemini-3.8-flash"})
    with pytest.raises(expected):
        adapter._run("system", "x")


def test_omp_quota_error_falls_back_to_next_provider(tmp_path, monkeypatch, mock_keys):
    from localclip import providers

    omp = _fake_omp(tmp_path, {"stopReason": "error", "errorMessage": "429 quota", "content": []}, tmp_path / "c.json")
    monkeypatch.setattr(providers, "get_omp_path", lambda: omp)
    mock_keys["openai"] = "sk-test"
    understood = {
        "topic": "humor", "emotion": "alegria", "reaction": "riso", "action": "conversa",
        "setting": "estúdio", "required_modality": "text", "keywords": ["piada"],
    }
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"choices": [{"message": {"content": json.dumps(understood)}}], "usage": {}}
    with patch("httpx.Client.post", return_value=fake_resp):
        result = understand_request(
            "momentos engraçados",
            {},
            {
                "primary": {"id": "omp", "kind": "omp", "model": "google-antigravity/gemini-3.8-flash"},
                "fallback": {"id": "openai", "kind": "openai", "model": "gpt-4o-mini"},
            },
            None,
            tmp_path / "cache",
        )
    assert result["topic"] == "humor"


def test_omp_login_rejects_unknown_provider():
    from localclip.providers import start_omp_login

    with pytest.raises(ValueError):
        start_omp_login("--help")

def test_curated_catalog_includes_omp_and_official_models():
    catalog = get_curated_catalog()
    assert "omp" in catalog
    assert "openai" in catalog
    assert "gemini" in catalog
    assert "openrouter" in catalog
    openrouter_ids = [m["id"] for m in catalog["openrouter"]]
    assert "openai/gpt-4o-mini" in openrouter_ids
    assert "anthropic" in catalog
    assert "glm" in catalog
    assert "compatible" in catalog

    omp_ids = [m["id"] for m in catalog["omp"]]
    assert "google-antigravity/gemini-3.8-flash" in omp_ids
    assert "openai-codex/gpt-6-luna" in omp_ids
    assert "zai/glm-5.3" in omp_ids

    openai_ids = [m["id"] for m in catalog["openai"]]
    assert "gpt-4o" in openai_ids
    assert "o3-mini" in openai_ids
    assert "gpt-6-luna" in openai_ids


def test_omp_adapter_list_models_annotates_logged_in_and_sorts():
    from localclip import providers

    mock_catalog = json.dumps({
        "models": [
            {"kind": "chat", "selector": "deepseek/deepseek-v4-flash", "name": "DeepSeek V4", "provider": "deepseek"},
            {"kind": "chat", "selector": "google-antigravity/gemini-3.8-flash", "name": "Gemini 3.8", "provider": "google-antigravity"},
            {"kind": "embedding", "selector": "openai/text-embed", "name": "Embed"},
        ]
    })

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = mock_catalog

    with patch("subprocess.run", return_value=fake_proc), \
         patch("localclip.providers.get_omp_path", return_value="/usr/bin/omp"), \
         patch("localclip.providers._omp_has_credential", side_effect=lambda omp, p: p == "google-antigravity"):
        adapter = providers.OmpAdapter({"id": "omp", "kind": "omp", "model": "google-antigravity/gemini-3.8-flash"})
        discovered = adapter.list_models()

    assert len(discovered) == 2
    assert discovered[0]["id"] == "google-antigravity/gemini-3.8-flash"
    assert discovered[0]["logged_in"] is True
    assert "Conta conectada" in discovered[0]["description"]
    assert discovered[1]["id"] == "deepseek/deepseek-v4-flash"
    assert discovered[1]["logged_in"] is False


def test_watch_omp_login_strips_ansi_and_sanitizes_error():
    import io
    from localclip import providers

    stdout_text = (
        "\x1b[32mOpen this URL in your browser:\x1b[0m\n"
        "\x1b[34mhttps://accounts.google.com/o/oauth2/auth?client_id=123\x1b[0m\n"
        "OAuth callback failed: https://127.0.0.1:8085/callback?code=secret_auth_code_12345 access_denied\n"
    )
    proc = MagicMock()
    proc.stdout = io.StringIO(stdout_text)
    proc.returncode = 1
    proc.poll.return_value = 1
    proc.stdin = MagicMock()

    with providers._OMP_LOGIN_LOCK:
        providers._OMP_LOGIN.clear()
        providers._OMP_LOGIN.update(proc=proc, provider="google-antigravity", auth_url=None, error=None)

    providers._watch_omp_login(proc)

    snapshot = providers._omp_login_snapshot()
    assert snapshot is not None
    assert snapshot["auth_url"] == "https://accounts.google.com/o/oauth2/auth?client_id=123"
    # Sensitive URL containing code must be sanitized to [URL]
    assert "secret_auth_code" not in str(snapshot["error"])
    assert "access_denied" in str(snapshot["error"])


def test_openrouter_adapter_health_check_valid_key():
    config = {"id": "or-p1", "kind": "openrouter", "model": "openai/gpt-4o-mini"}
    adapter = OpenRouterAdapter(config, api_key="sk-or-test-key-1234567890")
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"data": {"label": "My Key", "usage": 1.25, "limit": 10.0}}

    with patch("httpx.Client.get", return_value=fake_resp):
        health = adapter.health_check()

    assert health["ok"] is True
    assert health["kind"] == "openrouter"
    assert health["details"]["key_valid"] is True


def test_openrouter_adapter_health_check_402_credits():
    config = {"id": "or-p1", "kind": "openrouter", "model": "openai/gpt-4o-mini"}
    adapter = OpenRouterAdapter(config, api_key="sk-or-test-key-1234567890")
    fake_resp = MagicMock()
    fake_resp.status_code = 402

    with patch("httpx.Client.get", return_value=fake_resp):
        health = adapter.health_check()

    assert health["ok"] is False
    assert "Créditos esgotados" in health["message"]


def test_openrouter_adapter_list_models_filters_non_chat():
    config = {"id": "or-p1", "kind": "openrouter", "model": "openai/gpt-4o-mini"}
    adapter = OpenRouterAdapter(config, api_key="sk-or-test-key-1234567890")
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "data": [
            {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "description": "Rápido", "context_length": 128000},
            {"id": "openai/text-embedding-3-small", "name": "Embedding", "description": "Embeddings"},
            {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "description": "Flagship"},
        ]
    }

    with patch("httpx.Client.get", return_value=fake_resp):
        models = adapter.list_models()

    ids = [m["id"] for m in models]
    assert "openai/gpt-4o-mini" in ids
    assert "anthropic/claude-3.5-sonnet" in ids
    assert "openai/text-embedding-3-small" not in ids


def test_openrouter_adapter_call_chat_unsupported_format_raises_schema_validation_error():
    config = {"id": "or-p1", "kind": "openrouter", "model": "deepseek/deepseek-chat"}
    adapter = OpenRouterAdapter(config, api_key="sk-or-test-key-1234567890")

    resp_err = MagicMock()
    resp_err.status_code = 400
    resp_err.text = '{"error": {"message": "response_format is not supported by this model"}}'

    with patch("httpx.Client.post", return_value=resp_err):
        with pytest.raises(SchemaValidationError) as excinfo:
            adapter._call_chat([{"role": "user", "content": "hi"}])

    assert "formato não suportado" in str(excinfo.value)

def test_omp_login_passes_google_cloud_project_to_env():
    from localclip import providers

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    with patch("localclip.providers.get_omp_path", return_value="/usr/bin/omp"), \
         patch("subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("threading.Thread"):
        providers.start_omp_login("google-gemini-cli", google_cloud_project="my-valid-gcp-project-123")

    assert mock_popen.called
    env_used = mock_popen.call_args[1].get("env", {})
    assert env_used.get("GOOGLE_CLOUD_PROJECT") == "my-valid-gcp-project-123"
    assert env_used.get("GOOGLE_CLOUD_PROJECT_ID") == "my-valid-gcp-project-123"


def test_omp_login_invalid_google_cloud_project_raises_value_error():
    from localclip.providers import start_omp_login

    with patch("localclip.providers.get_omp_path", return_value="/usr/bin/omp"):
        with pytest.raises(ValueError) as excinfo:
            start_omp_login("google-gemini-cli", google_cloud_project="INVALID_PROJECT_NAME!!!")

    assert "ID de projeto Google Cloud inválido" in str(excinfo.value)


def test_omp_login_error_missing_project_message():
    import io
    from localclip import providers

    stdout_text = (
        "Login failed: This account requires setting the GOOGLE_CLOUD_PROJECT or GOOGLE_CLOUD_PROJECT_ID environment variable. See https://cloud.google.com\n"
    )
    proc = MagicMock()
    proc.stdout = io.StringIO(stdout_text)
    proc.returncode = 1
    proc.poll.return_value = 1
    proc.stdin = MagicMock()

    with providers._OMP_LOGIN_LOCK:
        providers._OMP_LOGIN.clear()
        providers._OMP_LOGIN.update(proc=proc, provider="google-gemini-cli", auth_url=None, error=None)

    providers._watch_omp_login(proc)

    snapshot = providers._omp_login_snapshot()
    assert snapshot is not None
    assert "requer definir o Google Cloud Project" in str(snapshot["error"])


def test_omp_google_cloud_project_persists_across_worker_restarts(tmp_path, monkeypatch):
    """Verifies that non-secret GCP project persists in SQLite settings and survives memory reset."""
    from localclip import providers, storage

    monkeypatch.setenv("LOCALCLIP_DATA_DIR", str(tmp_path))
    storage.initialize()

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    with patch("localclip.providers.get_omp_path", return_value="/usr/bin/omp"), \
         patch("subprocess.Popen", return_value=mock_proc), \
         patch("threading.Thread"):
        providers.start_omp_login("google-gemini-cli", google_cloud_project="persisted-gcp-project-101")

    # Verify directly in SQLite
    with storage.connection() as db:
        row = db.execute("SELECT data FROM settings WHERE key='omp_google_cloud_project'").fetchone()
        assert row is not None
        assert json.loads(row["data"]) == "persisted-gcp-project-101"

    # Simulate fresh worker process: reading helper returns the persisted project
    read_project = providers._get_persistent_omp_project()
    assert read_project == "persisted-gcp-project-101"

    # Clear process memory to simulate separate worker process start
    mock_proc.poll.return_value = 0
    with providers._OMP_LOGIN_LOCK:
        providers._OMP_LOGIN.clear()

    # Blank login (no project supplied) must not overwrite the existing saved project
    new_proc = MagicMock()
    new_proc.poll.return_value = None
    with patch("localclip.providers.get_omp_path", return_value="/usr/bin/omp"), \
         patch("subprocess.Popen", return_value=new_proc) as mock_popen, \
         patch("threading.Thread"):
        providers.start_omp_login("google-gemini-cli")

    assert mock_popen.called
    env_used = mock_popen.call_args[1].get("env", {})
    assert env_used.get("GOOGLE_CLOUD_PROJECT") == "persisted-gcp-project-101"
    assert env_used.get("GOOGLE_CLOUD_PROJECT_ID") == "persisted-gcp-project-101"


def test_omp_login_explicit_empty_project_clears_saved_setting(tmp_path, monkeypatch):
    from localclip import providers, storage

    monkeypatch.setenv("LOCALCLIP_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT_ID", raising=False)
    storage.initialize()
    providers._set_persistent_omp_project("old-gcp-project-123")
    proc = MagicMock()
    proc.poll.return_value = None
    with patch("localclip.providers.get_omp_path", return_value="/usr/bin/omp"), \
         patch("subprocess.Popen", return_value=proc) as popen, \
         patch("threading.Thread"):
        providers.start_omp_login("google-gemini-cli", google_cloud_project="")

    assert providers._get_persistent_omp_project() is None
    assert "GOOGLE_CLOUD_PROJECT" not in popen.call_args.kwargs["env"]
    with storage.connection() as db:
        assert db.execute("SELECT 1 FROM settings WHERE key='omp_google_cloud_project'").fetchone() is None


def test_openrouter_reasoning_model_omits_temperature():
    adapter = OpenRouterAdapter({"id": "or-p1", "kind": "openrouter", "model": "openai/o3"}, "sk-or-test-key")
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "choices": [{"message": {"content": "{}"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    with patch("httpx.Client.post", return_value=response) as post:
        adapter._call_chat([{"role": "user", "content": "ok"}])
    assert "temperature" not in post.call_args.kwargs["json"]
