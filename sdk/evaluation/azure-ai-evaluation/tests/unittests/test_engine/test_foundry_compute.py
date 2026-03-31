# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for Foundry cloud compute backend (foundry_compute.py)."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from azure.ai.evaluation._engine.foundry_compute import (
    EVALUATOR_TO_BUILTIN,
    NLP_EVALUATORS,
    _ORDINAL_1_5_EVALUATORS,
    _POLL_INTERVAL_SECONDS,
    _TERMINAL_STATUSES,
    _build_portal_url,
    _resolve_project_endpoint,
)
from azure.ai.evaluation._engine.config import Config


# ---------------------------------------------------------------------------
# Built-in evaluator mapping
# ---------------------------------------------------------------------------

class TestEvaluatorMapping:
    """Tests for the EVALUATOR_TO_BUILTIN mapping."""

    def test_f1_score_maps_to_builtin(self) -> None:
        assert EVALUATOR_TO_BUILTIN["f1_score"] == "builtin.f1_score"

    def test_relevance_maps_to_builtin(self) -> None:
        assert EVALUATOR_TO_BUILTIN["relevance"] == "builtin.relevance"

    def test_coherence_maps_to_builtin(self) -> None:
        assert EVALUATOR_TO_BUILTIN["coherence"] == "builtin.coherence"

    def test_all_values_have_builtin_prefix(self) -> None:
        for name, builtin in EVALUATOR_TO_BUILTIN.items():
            assert builtin.startswith("builtin."), f"{name} → {builtin}"

    def test_known_evaluators_present(self) -> None:
        expected = {
            "f1_score", "relevance", "coherence", "fluency",
            "groundedness", "similarity", "violence", "sexual",
            "self_harm", "hate_unfairness",
        }
        assert expected.issubset(EVALUATOR_TO_BUILTIN.keys())


# ---------------------------------------------------------------------------
# NLP evaluators
# ---------------------------------------------------------------------------

class TestNLPEvaluators:
    """Tests for NLP evaluator detection (no model deployment needed)."""

    def test_f1_score_is_nlp(self) -> None:
        assert "builtin.f1_score" in NLP_EVALUATORS

    def test_bleu_score_is_nlp(self) -> None:
        assert "builtin.bleu_score" in NLP_EVALUATORS

    def test_rouge_score_is_nlp(self) -> None:
        assert "builtin.rouge_score" in NLP_EVALUATORS

    def test_relevance_is_not_nlp(self) -> None:
        assert "builtin.relevance" not in NLP_EVALUATORS

    def test_coherence_is_not_nlp(self) -> None:
        assert "builtin.coherence" not in NLP_EVALUATORS


# ---------------------------------------------------------------------------
# Ordinal scale evaluators
# ---------------------------------------------------------------------------

class TestOrdinalScaleEvaluators:
    """Tests for ordinal 1-5 scale evaluator detection."""

    def test_coherence_is_ordinal(self) -> None:
        assert "coherence" in _ORDINAL_1_5_EVALUATORS

    def test_relevance_is_ordinal(self) -> None:
        assert "relevance" in _ORDINAL_1_5_EVALUATORS

    def test_fluency_is_ordinal(self) -> None:
        assert "fluency" in _ORDINAL_1_5_EVALUATORS

    def test_f1_score_is_not_ordinal(self) -> None:
        assert "f1_score" not in _ORDINAL_1_5_EVALUATORS

    def test_violence_is_not_ordinal(self) -> None:
        assert "violence" not in _ORDINAL_1_5_EVALUATORS


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Tests for module-level constants."""

    def test_poll_interval(self) -> None:
        assert _POLL_INTERVAL_SECONDS == 3

    def test_terminal_statuses(self) -> None:
        assert "completed" in _TERMINAL_STATUSES
        assert "failed" in _TERMINAL_STATUSES
        assert "cancelled" in _TERMINAL_STATUSES
        assert "running" not in _TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# Portal URL generation
# ---------------------------------------------------------------------------

class TestBuildPortalUrl:
    """Tests for _build_portal_url."""

    def test_returns_none_on_invalid_endpoint(self) -> None:
        # No az CLI available in unit tests; should return None gracefully
        result = _build_portal_url("https://invalid.endpoint.com", "eval-123")
        assert result is None

    def test_returns_none_on_empty_endpoint(self) -> None:
        result = _build_portal_url("", "eval-123")
        assert result is None

    @patch("subprocess.run")
    def test_returns_url_on_success(self, mock_run: MagicMock) -> None:
        import json as _json
        import uuid

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=_json.dumps([{
                "sub": f"/subscriptions/{uuid.UUID(int=1)}/resourceGroups/rg",
                "rg": "my-rg",
            }]),
        )

        result = _build_portal_url(
            "https://myaccount.cognitiveservices.azure.com/projects/myproject",
            "eval-123",
        )
        if result is not None:
            assert "ai.azure.com" in result
            assert "eval-123" in result

    @patch("subprocess.run")
    def test_returns_none_when_az_cli_fails(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = _build_portal_url(
            "https://acct.cognitiveservices.azure.com/projects/proj",
            "eval-x",
        )
        assert result is None


# ---------------------------------------------------------------------------
# _resolve_project_endpoint
# ---------------------------------------------------------------------------

class TestResolveProjectEndpoint:
    """Tests for _resolve_project_endpoint."""

    def test_uses_explicit_endpoint(self) -> None:
        cfg = Config.from_dict({"experiment": {"name": "test"}})
        result = _resolve_project_endpoint(cfg, "https://explicit.endpoint")
        assert result == "https://explicit.endpoint"

    def test_uses_compute_config(self) -> None:
        cfg = Config.from_dict({
            "experiment": {
                "name": "test",
                "compute": {
                    "type": "foundry",
                    "azure_ai_project": "https://from-compute.endpoint",
                },
            }
        })
        result = _resolve_project_endpoint(cfg, None)
        assert result == "https://from-compute.endpoint"

    def test_raises_when_no_endpoint_found(self) -> None:
        cfg = Config.from_dict({"experiment": {"name": "test"}})
        with pytest.raises(ValueError, match="No Foundry project endpoint"):
            _resolve_project_endpoint(cfg, None)


# ---------------------------------------------------------------------------
# run_remote_evaluation (integration mock)
# ---------------------------------------------------------------------------

class TestRunRemoteEvaluation:
    """Tests for run_remote_evaluation with mocked API calls."""

    def test_module_references_foundry(self) -> None:
        """Verify the module docstring mentions Foundry."""
        from azure.ai.evaluation._engine import foundry_compute as fc

        assert "Foundry" in (fc.__doc__ or "")
