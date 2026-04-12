# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Unit tests for the engine decorator framework (evaluator, target, dataset).

Adapted from evee's test_base_metric.py, test_base_model.py, and
test_base_dataset.py with naming conventions updated for the engine
(metric → evaluator, model → target).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from azure.ai.evaluation._engine.decorators import (
    BaseDataset,
    BaseEvaluator,
    BaseTarget,
    DATASET_REGISTRY,
    EVALUATOR_REGISTRY,
    TARGET_REGISTRY,
    dataset,
    evaluator,
    target,
)
from azure.ai.evaluation._engine.models import ExecutionContext, InferenceOutput


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_context(mock_connections_registry):
    """ExecutionContext populated with mock connections."""
    return ExecutionContext(connections_registry=mock_connections_registry)


@pytest.fixture()
def valid_evaluator_config():
    return {
        "name": "test_evaluator",
        "mapping": {
            "response": "model.answer",
            "ground_truth": "dataset.expected",
        },
        "threshold": 0.5,
    }


@pytest.fixture()
def valid_target_config():
    return {"temperature": 0.7, "max_tokens": 100}


@pytest.fixture()
def valid_dataset_config():
    return {"data_path": "test_data.jsonl", "version": "1.0"}


@pytest.fixture()
def evaluator_inference_output():
    return InferenceOutput(
        output={"answer": "Paris"},
        model_name="test_target",
        record={"question": "Capital of France?", "expected": "Paris"},
        args={"temperature": 0.7},
    )


# ===========================================================================
# EVALUATOR DECORATOR TESTS
# ===========================================================================


class TestEvaluatorDecorator:
    """Tests for the @evaluator decorator."""

    def test_valid_config_initialization(
        self, valid_evaluator_config, mock_context, mock_connections_registry
    ):
        """EvaluatorWrapper is created with config values injected into inner."""
        # given
        @evaluator(name="eval_init_test")
        class SimpleEvaluator:
            def __init__(self, threshold: float):
                self.threshold = threshold

            def compute(self, response: str, ground_truth: str, **kwargs) -> dict:
                return {"score": 1.0 if response == ground_truth else 0.0}

            def aggregate(self, scores: list) -> dict:
                return {"mean": sum(s["score"] for s in scores) / len(scores)}

        # when
        instance = SimpleEvaluator(valid_evaluator_config, mock_context)

        # then
        assert instance.name == "test_evaluator"
        assert instance.context.connections_registry == mock_connections_registry
        assert hasattr(instance, "inner")
        assert instance.inner.threshold == 0.5

    def test_display_name_from_config(self, mock_context):
        """display_name is read from config when provided."""
        # given
        config = {
            "name": "coherence_eval",
            "display_name": "Coherence",
            "mapping": {},
        }

        @evaluator(name="eval_display_test")
        class DisplayNameEval:
            def __init__(self): ...
            def compute(self, **kwargs): return {}
            def aggregate(self, scores): return {}

        # when
        instance = DisplayNameEval(config, mock_context)

        # then
        assert instance.name == "coherence_eval"
        assert instance.display_name == "Coherence"

    def test_display_name_falls_back_to_name(self, mock_context):
        """display_name defaults to name when not specified."""
        # given
        config = {"name": "f1score_eval", "mapping": {}}

        @evaluator(name="eval_fallback_test")
        class FallbackEval:
            def __init__(self): ...
            def compute(self, **kwargs): return {}
            def aggregate(self, scores): return {}

        # when
        instance = FallbackEval(config, mock_context)

        # then
        assert instance.display_name == "f1score_eval"

    def test_compute_with_valid_mapping(
        self, mock_context, evaluator_inference_output
    ):
        """compute() resolves fields through mapping from InferenceOutput."""
        # given
        config = {
            "name": "mapped_eval",
            "mapping": {
                "response": "model.answer",
                "ground_truth": "dataset.expected",
            },
        }

        @evaluator(name="eval_compute_test")
        class MappedEval:
            def __init__(self): ...

            def compute(self, response: str, ground_truth: str, **kwargs) -> dict:
                return {
                    "score": 1.0 if response == ground_truth else 0.0,
                    "response_value": response,
                    "truth_value": ground_truth,
                }

            def aggregate(self, scores: list) -> dict:
                return {"mean": sum(s["score"] for s in scores) / len(scores)}

        instance = MappedEval(config, mock_context)

        # when
        result = instance.compute(evaluator_inference_output)

        # then
        assert result["response_value"] == "Paris"
        assert result["truth_value"] == "Paris"
        assert result["score"] == 1.0

    def test_compute_with_missing_model_field(
        self, mock_context, evaluator_inference_output
    ):
        """KeyError when mapping references a field missing from output."""
        # given
        config = {
            "name": "missing_field_eval",
            "mapping": {
                "response": "model.non_existent_field",
                "ground_truth": "dataset.expected",
            },
        }

        @evaluator(name="eval_missing_field_test")
        class MissingFieldEval:
            def __init__(self): ...

            def compute(self, response, ground_truth, **kwargs):
                return {"score": 1.0}

            def aggregate(self, scores):
                return {"mean": 1.0}

        instance = MissingFieldEval(config, mock_context)

        # when / then
        with pytest.raises(
            KeyError, match=r"Field 'non_existent_field' not found in 'model'"
        ):
            instance.compute(evaluator_inference_output)

    def test_invalid_mapping_format(self, mock_context):
        """ValueError for mapping values not matching 'model.X' / 'dataset.X'."""
        # given
        config = {
            "name": "bad_mapping_eval",
            "mapping": {
                "response": "invalid_format",
                "ground_truth": "dataset.expected",
            },
        }

        @evaluator(name="eval_bad_mapping_test")
        class BadMappingEval:
            def __init__(self): ...
            def compute(self, **kwargs): return {"score": 1.0}
            def aggregate(self, scores): return {"mean": 1.0}

        # when / then
        with pytest.raises(
            ValueError,
            match=r"Invalid mapping 'invalid_format'.*expected format 'target\.X' or 'dataset\.X'",
        ):
            BadMappingEval(config, mock_context)

    def test_connections_via_context(
        self,
        mock_context,
        mock_connections_registry,
        evaluator_inference_output,
    ):
        """connections_registry is accessible through context, not injected directly."""
        # given
        config = {
            "name": "conn_eval",
            "mapping": {
                "response": "model.answer",
                "ground_truth": "dataset.expected",
            },
        }

        @evaluator(name="eval_conn_test")
        class ConnEval:
            def __init__(self, context):
                self.context = context

            def compute(self, response, ground_truth, **kwargs) -> dict:
                return {
                    "count": len(self.context.connections_registry),
                    "names": list(self.context.connections_registry.keys()),
                }

            def aggregate(self, scores):
                return {"total": len(scores)}

        # when
        instance = ConnEval(config, mock_context)
        result = instance.compute(evaluator_inference_output)

        # then
        assert result["count"] == len(mock_connections_registry)
        assert "default" in result["names"]
        assert "secondary" in result["names"]

    def test_injects_context(self, mock_context, evaluator_inference_output):
        """ExecutionContext is injected when the inner class requests it."""
        # given
        config = {
            "name": "ctx_eval",
            "mapping": {
                "response": "model.answer",
                "ground_truth": "dataset.expected",
            },
        }

        @evaluator(name="eval_ctx_test")
        class CtxEval:
            def __init__(self, context):
                self.context = context

            def compute(self, response, ground_truth, **kwargs) -> dict:
                return {
                    "has_connections": len(self.context.connections_registry) > 0,
                    "experiment": self.context.experiment_name,
                }

            def aggregate(self, scores):
                return {}

        instance = CtxEval(config, mock_context)
        result = instance.compute(evaluator_inference_output)

        # then
        assert result["has_connections"] is True
        assert result["experiment"] == mock_context.experiment_name

    def test_aggregate_with_empty_scores(self, valid_evaluator_config, mock_context):
        """aggregate() works correctly with an empty list."""
        # given
        @evaluator(name="eval_agg_test")
        class AggEval:
            def __init__(self, threshold: float):
                self.threshold = threshold

            def compute(self, **kwargs):
                return {"score": 1.0}

            def aggregate(self, scores):
                if not scores:
                    return {"mean": 0.0, "count": 0}
                return {
                    "mean": sum(s["score"] for s in scores) / len(scores),
                    "count": len(scores),
                }

        instance = AggEval(valid_evaluator_config, mock_context)

        # when
        result = instance.aggregate([])

        # then
        assert result["mean"] == 0.0
        assert result["count"] == 0

    def test_duplicate_registration_returns_existing(self):
        """Registering the same evaluator name twice returns the first class."""
        # given
        @evaluator(name="dup_eval")
        class FirstEval:
            def __init__(self): ...
            def compute(self, **kwargs): return {"source": "first"}
            def aggregate(self, scores): return {}

        # when — same name
        @evaluator(name="dup_eval")
        class SecondEval:
            def __init__(self): ...
            def compute(self, **kwargs): return {"source": "second"}
            def aggregate(self, scores): return {}

        # then — idempotent; second decorator returns the first wrapper
        assert SecondEval is FirstEval
        assert EVALUATOR_REGISTRY["dup_eval"] is FirstEval

    def test_registered_in_evaluator_registry(self):
        """Decorated class is stored in EVALUATOR_REGISTRY."""
        @evaluator(name="registry_eval")
        class RegistryEval:
            def __init__(self): ...
            def compute(self, **kwargs): return {}
            def aggregate(self, scores): return {}

        assert "registry_eval" in EVALUATOR_REGISTRY

    def test_preserves_metadata(self):
        """Decorator preserves __name__ and __doc__ from the original class."""
        @evaluator(name="meta_eval")
        class DocumentedEvaluator:
            """Evaluator with docstring."""
            def __init__(self): ...
            def compute(self, **kwargs): return {}
            def aggregate(self, scores): return {}

        assert DocumentedEvaluator.__name__ == "DocumentedEvaluator"
        assert DocumentedEvaluator.__doc__ == "Evaluator with docstring."


# ===========================================================================
# TARGET DECORATOR TESTS
# ===========================================================================


class TestTargetDecorator:
    """Tests for the @target decorator."""

    def test_valid_config_initialization(
        self, valid_target_config, mock_context, mock_connections_registry
    ):
        """TargetWrapper injects config params and delegates infer()."""
        # given
        @target(name="target_init_test")
        class SimpleTarget:
            def __init__(self, temperature: float, max_tokens: int):
                self.temperature = temperature
                self.max_tokens = max_tokens

            def infer(self, input: dict) -> dict:
                return {"answer": "test", "temp": self.temperature}

        # when
        instance = SimpleTarget(valid_target_config, mock_context)
        result = instance.infer({"question": "test"})

        # then
        assert result["answer"] == "test"
        assert result["temp"] == 0.7
        assert instance.context.connections_registry == mock_connections_registry

    def test_missing_required_parameters(self, mock_context):
        """ValueError when required init params are missing from config."""
        # given
        @target(name="target_missing_test")
        class ParamTarget:
            def __init__(self, required_param: str, optional: str = "default"):
                self.required_param = required_param

            def infer(self, input: dict) -> dict:
                return {}

        config: Dict[str, Any] = {"name": "test"}

        # when / then
        with pytest.raises(
            ValueError, match=r"Missing required parameters.*required_param"
        ):
            ParamTarget(config, mock_context)

    def test_connections_via_context(
        self, mock_context, mock_connections_registry
    ):
        """connections_registry is accessible through context, not injected directly."""
        # given
        @target(name="target_conn_test")
        class ConnTarget:
            def __init__(self, context):
                self.context = context

            def infer(self, input: dict) -> dict:
                return {"connections": list(self.context.connections_registry.keys())}

        # when
        instance = ConnTarget({}, mock_context)
        result = instance.infer({"test": "input"})

        # then
        assert "default" in result["connections"]
        assert "secondary" in result["connections"]

    def test_injects_context(self, mock_context):
        """ExecutionContext is injected when inner class requests it."""
        # given
        @target(name="target_ctx_test")
        class CtxTarget:
            def __init__(self, context):
                self.context = context

            def infer(self, input: dict) -> dict:
                return {"experiment": self.context.experiment_name}

        # when
        instance = CtxTarget({}, mock_context)
        result = instance.infer({})

        # then
        assert result["experiment"] == mock_context.experiment_name

    def test_handles_optional_parameters(self, mock_context):
        """Optional parameters with defaults are correctly handled."""
        # given
        @target(name="target_defaults_test")
        class DefaultsTarget:
            def __init__(self, required: str, optional: str = "default_value", count: int = 42):
                self.required = required
                self.optional = optional
                self.count = count

            def infer(self, input: dict) -> dict:
                return {
                    "required": self.required,
                    "optional": self.optional,
                    "count": self.count,
                }

        config = {"required": "test_value"}

        # when
        instance = DefaultsTarget(config, mock_context)
        result = instance.infer({})

        # then
        assert result["required"] == "test_value"
        assert result["optional"] == "default_value"
        assert result["count"] == 42

    def test_async_infer_detection(self, valid_target_config, mock_context):
        """Async infer method sets _is_async = True."""
        # given
        @target(name="target_async_detect")
        class AsyncTarget:
            def __init__(self, temperature: float, max_tokens: int):
                self.temperature = temperature

            async def infer(self, input: dict) -> dict:
                return {"answer": "async"}

        # when
        instance = AsyncTarget(valid_target_config, mock_context)

        # then
        assert instance._is_async is True

    def test_sync_infer_detection(self, valid_target_config, mock_context):
        """Sync infer method sets _is_async = False."""
        # given
        @target(name="target_sync_detect")
        class SyncTarget:
            def __init__(self, temperature: float, max_tokens: int):
                self.temperature = temperature

            def infer(self, input: dict) -> dict:
                return {"answer": "sync"}

        # when
        instance = SyncTarget(valid_target_config, mock_context)

        # then
        assert instance._is_async is False

    def test_async_target_via_sync_infer(self, valid_target_config, mock_context):
        """Async target called through sync infer() uses asyncio.run()."""
        # given
        @target(name="target_async_sync_bridge")
        class AsyncTarget:
            def __init__(self, temperature: float, max_tokens: int):
                self.temperature = temperature

            async def infer(self, input: dict) -> dict:
                await asyncio.sleep(0.001)
                return {
                    "answer": f"async: {input.get('question')}",
                    "temp": self.temperature,
                }

        instance = AsyncTarget(valid_target_config, mock_context)

        # when
        result = instance.infer({"question": "test"})

        # then
        assert result["answer"] == "async: test"
        assert result["temp"] == 0.7

    @pytest.mark.asyncio
    async def test_async_target_via_infer_async(
        self, valid_target_config, mock_context
    ):
        """Async target called through infer_async() directly awaits."""
        # given
        @target(name="target_async_iface")
        class AsyncTarget:
            def __init__(self, temperature: float, max_tokens: int):
                self.temperature = temperature

            async def infer(self, input: dict) -> dict:
                await asyncio.sleep(0.001)
                return {"answer": f"async: {input.get('question')}"}

        instance = AsyncTarget(valid_target_config, mock_context)

        # when
        result = await instance.infer_async({"question": "test"})

        # then
        assert result["answer"] == "async: test"

    @pytest.mark.asyncio
    async def test_sync_target_via_infer_async(
        self, valid_target_config, mock_context
    ):
        """Sync target called through infer_async() runs in executor."""
        # given
        @target(name="target_sync_async_iface")
        class SyncTarget:
            def __init__(self, temperature: float, max_tokens: int):
                self.temperature = temperature

            def infer(self, input: dict) -> dict:
                return {"answer": f"sync: {input.get('question')}"}

        instance = SyncTarget(valid_target_config, mock_context)

        # when
        result = await instance.infer_async({"question": "test"})

        # then
        assert result["answer"] == "sync: test"

    def test_delegates_infer_to_inner(self, valid_target_config, mock_context):
        """infer() delegates to the inner class method."""
        # given
        call_tracker: list = []

        @target(name="target_delegate_test")
        class TrackingTarget:
            def __init__(self, temperature: float, max_tokens: int):
                self.temperature = temperature

            def infer(self, input: dict) -> dict:
                call_tracker.append(input)
                return {"received": input, "temp": self.temperature}

        sample_input = {"question": "What is AI?"}
        instance = TrackingTarget(valid_target_config, mock_context)

        # when
        result = instance.infer(sample_input)

        # then
        assert len(call_tracker) == 1
        assert call_tracker[0] == sample_input
        assert result["received"] == sample_input

    # -- close() pattern --------------------------------------------------

    def test_sync_close_detection(self):
        """Sync close() method is detected by the wrapper."""
        # given
        @target(name="target_sync_close_detect")
        class SyncCloseTarget:
            def __init__(self):
                self.closed = False

            def infer(self, input: dict) -> dict:
                return {}

            def close(self):
                self.closed = True

        instance = TARGET_REGISTRY["target_sync_close_detect"]({})

        # then
        assert instance._has_close is True
        assert instance._close_is_async is False

    def test_async_close_detection(self):
        """Async close() method is detected by the wrapper."""
        # given
        @target(name="target_async_close_detect")
        class AsyncCloseTarget:
            def __init__(self):
                self.closed = False

            def infer(self, input: dict) -> dict:
                return {}

            async def close(self):
                self.closed = True

        instance = TARGET_REGISTRY["target_async_close_detect"]({})

        # then
        assert instance._has_close is True
        assert instance._close_is_async is True

    def test_sync_close_called(self):
        """Sync close() is delegated to the inner target."""
        # given
        @target(name="target_sync_close_call")
        class SyncCloseTarget:
            def __init__(self):
                self.closed = False

            def infer(self, input: dict) -> dict:
                return {}

            def close(self):
                self.closed = True

        instance = TARGET_REGISTRY["target_sync_close_call"]({})
        assert instance.inner.closed is False

        # when
        instance.close()

        # then
        assert instance.inner.closed is True

    def test_async_close_via_sync_wrapper(self):
        """Async close() is called via sync wrapper using asyncio.run()."""
        # given
        @target(name="target_async_close_sync")
        class AsyncCloseTarget:
            def __init__(self):
                self.closed = False

            def infer(self, input: dict) -> dict:
                return {}

            async def close(self):
                self.closed = True

        instance = TARGET_REGISTRY["target_async_close_sync"]({})
        assert instance.inner.closed is False

        # when
        instance.close()

        # then
        assert instance.inner.closed is True

    def test_close_noop_when_not_implemented(self):
        """close() is a no-op when the inner class doesn't implement it."""
        # given
        @target(name="target_no_close")
        class NoCloseTarget:
            def __init__(self): ...

            def infer(self, input: dict) -> dict:
                return {}

        instance = TARGET_REGISTRY["target_no_close"]({})

        # then — should not raise
        assert instance._has_close is False
        instance.close()

    # -- registration / validation ----------------------------------------

    def test_duplicate_registration_raises(self):
        """ValueError when registering the same target name twice."""
        # given
        @target(name="dup_target")
        class FirstTarget:
            def __init__(self): ...
            def infer(self, input: dict) -> dict: return {}

        # when / then
        with pytest.raises(
            ValueError, match=r"Target 'dup_target' already registered"
        ):

            @target(name="dup_target")
            class SecondTarget:
                def __init__(self): ...
                def infer(self, input: dict) -> dict: return {}

    def test_registered_in_target_registry(self):
        """Decorated class is stored in TARGET_REGISTRY."""
        @target(name="registry_target")
        class RegistryTarget:
            def __init__(self): ...
            def infer(self, input: dict) -> dict: return {}

        assert "registry_target" in TARGET_REGISTRY

    def test_missing_infer_raises_at_decoration(self):
        """AttributeError when decorated class lacks infer method."""
        with pytest.raises(AttributeError):

            @target(name="target_no_infer")
            class NoInferTarget:
                def __init__(self): ...

    def test_preserves_metadata(self):
        """Decorator preserves __name__ and __doc__ from the original class."""
        @target(name="meta_target")
        class DocumentedTarget:
            """Target with docstring."""
            def __init__(self): ...
            def infer(self, input: dict) -> dict: return {}

        assert DocumentedTarget.__name__ == "DocumentedTarget"
        assert DocumentedTarget.__doc__ == "Target with docstring."


# ===========================================================================
# DATASET DECORATOR TESTS
# ===========================================================================


class TestDatasetDecorator:
    """Tests for the @dataset decorator."""

    def test_valid_config_initialization(self, valid_dataset_config, mock_context):
        """DatasetWrapper creates inner with config params; iteration works."""
        # given
        @dataset(name="ds_init_test")
        class SimpleDataset:
            def __init__(self, data_path: str, version: str):
                self.data_path = data_path
                self.version = version
                self.data = [{"id": 1}, {"id": 2}]

            def __iter__(self):
                return iter(self.data)

            def __len__(self):
                return len(self.data)

        # when
        instance = SimpleDataset(valid_dataset_config, mock_context)

        # then
        assert isinstance(instance, BaseDataset)
        assert list(instance) == [{"id": 1}, {"id": 2}]
        assert len(instance) == 2

    def test_missing_required_param(self, mock_context):
        """ValueError when required init params are missing from config."""
        # given
        @dataset(name="ds_missing_test")
        class ParamDataset:
            def __init__(self, data_path: str, required_param: str):
                self.data_path = data_path
                self.required_param = required_param

            def __iter__(self):
                return iter([])

            def __len__(self):
                return 0

        config = {"data_path": "test.jsonl"}

        # when / then
        with pytest.raises(
            ValueError,
            match=r"Missing required parameters for dataset.*required_param",
        ):
            ParamDataset(config, mock_context)

    def test_iter_and_len(self, valid_dataset_config, mock_context):
        """__iter__ and __len__ delegate correctly to inner."""
        # given
        @dataset(name="ds_iter_test")
        class IterDataset:
            def __init__(self, data_path: str):
                self.data = [{"id": i, "value": f"item_{i}"} for i in range(5)]

            def __iter__(self):
                yield from self.data

            def __len__(self):
                return len(self.data)

        instance = IterDataset(valid_dataset_config, mock_context)

        # when
        items = list(instance)

        # then
        assert len(items) == 5
        assert items[0] == {"id": 0, "value": "item_0"}
        assert items[4] == {"id": 4, "value": "item_4"}

    def test_with_default_params(self, mock_context):
        """Optional parameters with defaults are respected."""
        # given
        @dataset(name="ds_defaults_test")
        class DefaultsDataset:
            def __init__(self, data_path: str, optional_param: str = "default_value"):
                self.data_path = data_path
                self.optional_param = optional_param
                self.data = [{"test": "data"}]

            def __iter__(self):
                return iter(self.data)

            def __len__(self):
                return len(self.data)

        config = {"data_path": "test.jsonl"}

        # when
        instance = DefaultsDataset(config, mock_context)

        # then
        assert instance.inner.data_path == "test.jsonl"
        assert instance.inner.optional_param == "default_value"
        assert len(instance) == 1

    def test_connections_via_context(self, mock_context, mock_connections_registry):
        """connections_registry is accessible through context, not injected directly."""
        # given
        @dataset(name="ds_conn_test")
        class ConnDataset:
            def __init__(self, data_path: str, context):
                self.data_path = data_path
                self.context = context
                self.data = [{"connection": list(context.connections_registry.keys())}]

            def __iter__(self):
                return iter(self.data)

            def __len__(self):
                return len(self.data)

        config = {"data_path": "test.jsonl"}

        # when
        instance = ConnDataset(config, mock_context)

        # then
        assert instance.inner.context.connections_registry == mock_connections_registry
        assert len(instance) == 1

    def test_multiple_iterations(self, mock_context):
        """Dataset can be iterated multiple times."""
        # given
        @dataset(name="ds_multi_iter_test")
        class ReiterableDataset:
            def __init__(self, data_path: str):
                self.data = [{"id": 1}, {"id": 2}]

            def __iter__(self):
                return iter(self.data)

            def __len__(self):
                return len(self.data)

        instance = ReiterableDataset({"data_path": "test.jsonl"}, mock_context)

        # when
        first = list(instance)
        second = list(instance)

        # then
        assert first == second
        assert len(first) == 2

    def test_config_parameter_mapping(self, mock_context):
        """Config parameters are correctly mapped to inner __init__."""
        # given
        @dataset(name="ds_cfg_map_test")
        class ConfigurableDataset:
            def __init__(self, data_path: str, batch_size: int, normalize: bool):
                self.data_path = data_path
                self.batch_size = batch_size
                self.normalize = normalize

            def __iter__(self):
                return iter([])

            def __len__(self):
                return 0

        config = {"data_path": "data.jsonl", "batch_size": 32, "normalize": True}

        # when
        instance = ConfigurableDataset(config, mock_context)

        # then
        assert instance.inner.data_path == "data.jsonl"
        assert instance.inner.batch_size == 32
        assert instance.inner.normalize is True

    def test_duplicate_registration_raises(self):
        """ValueError when registering the same dataset name twice."""
        # given
        @dataset(name="dup_dataset")
        class FirstDs:
            def __init__(self, data_path: str):
                self.data_path = data_path

            def __iter__(self):
                return iter([])

            def __len__(self):
                return 0

        # when / then
        with pytest.raises(
            ValueError, match=r"Dataset 'dup_dataset' already registered"
        ):

            @dataset(name="dup_dataset")
            class SecondDs:
                def __init__(self, data_path: str):
                    self.data_path = data_path

                def __iter__(self):
                    return iter([])

                def __len__(self):
                    return 0

    def test_registered_in_dataset_registry(self):
        """Decorated class is stored in DATASET_REGISTRY."""
        @dataset(name="registry_dataset")
        class RegistryDs:
            def __init__(self, data_path: str):
                self.data_path = data_path

            def __iter__(self):
                return iter([])

            def __len__(self):
                return 0

        assert "registry_dataset" in DATASET_REGISTRY

    def test_preserves_metadata(self):
        """Decorator preserves __name__ and __doc__."""
        @dataset(name="ds_meta_test")
        class DocumentedDataset:
            """This is a documented dataset."""

            def __init__(self, data_path: str):
                self.data_path = data_path

            def __iter__(self):
                return iter([])

            def __len__(self):
                return 0

        assert DocumentedDataset.__name__ == "DocumentedDataset"
        assert DocumentedDataset.__doc__ == "This is a documented dataset."
