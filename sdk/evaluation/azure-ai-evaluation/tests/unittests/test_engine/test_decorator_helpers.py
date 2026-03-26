# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Unit tests for decorator_helpers.py — shared helper functions.

Adapted from evee's test_decorator_helpers.py with function names
updated to match the engine API (get_missing_params, get_params_from_config).
"""

from __future__ import annotations

import inspect

import pytest

from azure.ai.evaluation._engine.decorator_helpers import (
    get_missing_params,
    get_params_from_config,
    validate_required_methods,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_function_signature():
    """Signature with required, optional, and **kwargs parameters."""

    def sample_func(self, param1: str, param2: int, param3: float = 0.5, **kwargs): ...

    return inspect.signature(sample_func)


@pytest.fixture()
def sample_function_no_defaults():
    """Signature where all parameters are required."""

    def sample_func(self, required1: str, required2: int, required3: bool): ...

    return inspect.signature(sample_func)


@pytest.fixture()
def sample_function_with_connections():
    """Signature containing connections_registry (auto-ignored)."""

    def sample_func(self, param1: str, connections_registry: dict, param2: int = 10): ...

    return inspect.signature(sample_func)


# ===========================================================================
# get_missing_params
# ===========================================================================


class TestGetMissingParams:
    """Tests for get_missing_params()."""

    def test_all_present(self, sample_function_signature):
        # given
        config = {"param1": "value1", "param2": 42, "extra_param": "extra"}

        # when
        missing = get_missing_params(sample_function_signature, config)

        # then
        assert missing == set()

    def test_some_missing(self, sample_function_signature):
        # given — param2 is required but missing
        config = {"param1": "value1"}

        # when
        missing = get_missing_params(sample_function_signature, config)

        # then
        assert missing == {"param2"}

    def test_all_missing(self, sample_function_no_defaults):
        # given
        config: dict = {}

        # when
        missing = get_missing_params(sample_function_no_defaults, config)

        # then
        assert missing == {"required1", "required2", "required3"}

    def test_ignores_defaults(self, sample_function_signature):
        """Parameters with default values are never considered missing."""
        # given — param3 has a default, should not be required
        config = {"param1": "value1", "param2": 42}

        # when
        missing = get_missing_params(sample_function_signature, config)

        # then
        assert missing == set()
        assert "param3" not in missing

    def test_ignores_self(self):
        """'self' is never reported as missing."""
        # given
        def sample_method(self, required_param: str): ...

        signature = inspect.signature(sample_method)
        config: dict = {}

        # when
        missing = get_missing_params(signature, config)

        # then
        assert "self" not in missing
        assert missing == {"required_param"}

    def test_ignores_kwargs(self, sample_function_signature):
        """**kwargs is never reported as missing."""
        # given
        config = {"param1": "value1", "param2": 42}

        # when
        missing = get_missing_params(sample_function_signature, config)

        # then
        assert "kwargs" not in missing
        assert missing == set()

    def test_ignores_connections_registry_by_default(
        self, sample_function_with_connections
    ):
        """connections_registry is ignored by the default ignore list."""
        # given
        config = {"param1": "value1"}

        # when
        missing = get_missing_params(sample_function_with_connections, config)

        # then
        assert "connections_registry" not in missing
        assert missing == set()

    def test_ignores_context_by_default(self):
        """context is ignored by the default ignore list."""
        # given
        def sample_func(self, param1: str, context: object): ...

        signature = inspect.signature(sample_func)
        config = {"param1": "value1"}

        # when
        missing = get_missing_params(signature, config)

        # then
        assert "context" not in missing
        assert missing == set()

    def test_custom_ignore(self):
        """Custom ignore list is respected."""
        # given
        def sample_func(self, param1: str, param2: int, special_param: str): ...

        signature = inspect.signature(sample_func)
        config = {"param1": "value1", "param2": 42}

        # when
        missing = get_missing_params(signature, config, ignore=["special_param"])

        # then
        assert "special_param" not in missing
        assert missing == set()

    def test_empty_ignore_list(self):
        """With ignore=[], connections_registry IS reported as missing."""
        # given
        def sample_func(self, connections_registry: dict, param1: str): ...

        signature = inspect.signature(sample_func)
        config = {"param1": "value1"}

        # when
        missing = get_missing_params(signature, config, ignore=[])

        # then
        assert missing == {"connections_registry"}

    def test_classmethod(self):
        """cls parameter is skipped for classmethods."""
        # given
        class Sample:
            @classmethod
            def method(cls, param1: str, param2: int, param3: float = 0.5): ...

        signature = inspect.signature(Sample.method)
        config = {"param1": "value1"}

        # when
        missing = get_missing_params(signature, config)

        # then
        assert "cls" not in missing
        assert missing == {"param2"}

    def test_staticmethod(self):
        """Static methods work without self/cls issues."""
        # given
        class Sample:
            @staticmethod
            def method(param1: str, param2: int, param3: float = 0.5): ...

        signature = inspect.signature(Sample.method)
        config = {"param1": "value1"}

        # when
        missing = get_missing_params(signature, config)

        # then
        assert missing == {"param2"}


# ===========================================================================
# get_params_from_config
# ===========================================================================


class TestGetParamsFromConfig:
    """Tests for get_params_from_config()."""

    def test_intersection(self, sample_function_signature):
        """Returns only params present in both signature and config."""
        # given
        config = {
            "param1": "value1",
            "param2": 42,
            "param3": 0.8,
            "extra_param": "not_in_signature",
        }

        # when
        params = get_params_from_config(sample_function_signature, config)

        # then
        assert params == {"param1": "value1", "param2": 42, "param3": 0.8}
        assert "extra_param" not in params

    def test_partial_match(self, sample_function_signature):
        """Works when config only partially matches the signature."""
        # given
        config = {"param1": "value1", "unknown_param": "unknown"}

        # when
        params = get_params_from_config(sample_function_signature, config)

        # then
        assert params == {"param1": "value1"}
        assert "unknown_param" not in params

    def test_empty_config(self, sample_function_signature):
        """Returns empty dict for empty config."""
        # when
        params = get_params_from_config(sample_function_signature, {})

        # then
        assert params == {}

    def test_staticmethod(self):
        """Works with static method signatures."""
        # given
        class Sample:
            @staticmethod
            def method(param1: str, param2: int): ...

        signature = inspect.signature(Sample.method)
        config = {"param1": "value1", "param2": 42, "extra": "skip"}

        # when
        params = get_params_from_config(signature, config)

        # then
        assert params == {"param1": "value1", "param2": 42}
        assert "extra" not in params

    def test_classmethod(self):
        """Works with classmethod signatures; cls is excluded from config."""
        # given
        class Sample:
            @classmethod
            def method(cls, param1: str, param2: int, extra: str = "default"): ...

        signature = inspect.signature(Sample.method)
        config = {"param1": "value1", "param2": 42, "extra": "custom", "unknown": "x"}

        # when
        params = get_params_from_config(signature, config)

        # then
        assert params == {"param1": "value1", "param2": 42, "extra": "custom"}
        assert "cls" not in params
        assert "unknown" not in params


# ===========================================================================
# validate_required_methods
# ===========================================================================


class TestValidateRequiredMethods:
    """Tests for validate_required_methods()."""

    def test_all_implemented(self):
        """No error when all required methods are overridden."""
        # given
        class Base:
            def method1(self): ...
            def method2(self): ...

        class Impl(Base):
            def method1(self):
                return "impl1"

            def method2(self):
                return "impl2"

        # when / then — should not raise
        validate_required_methods(Impl, Base, ["method1", "method2"])

    def test_missing_method(self):
        """NotImplementedError when required method is missing."""
        # given
        class Base:
            def required_method(self): ...

        class Incomplete(Base): ...

        # when / then
        with pytest.raises(
            NotImplementedError,
            match="must implement the 'required_method' method",
        ):
            validate_required_methods(Incomplete, Base, ["required_method"])

    def test_not_overridden(self):
        """NotImplementedError when method exists but is inherited (not overridden)."""
        # given
        class Base:
            def method1(self):
                return "base"

        class Derived(Base): ...

        # when / then
        with pytest.raises(
            NotImplementedError, match="must implement the 'method1' method"
        ):
            validate_required_methods(Derived, Base, ["method1"])

    def test_multiple_missing_reports_first(self):
        """With multiple missing methods, first encountered is reported."""
        # given
        class Base:
            def method1(self): ...
            def method2(self): ...
            def method3(self): ...

        class Incomplete(Base):
            def method1(self):
                return "implemented"

        # when / then — should raise for method2 (first missing)
        with pytest.raises(
            NotImplementedError, match="must implement the 'method2' method"
        ):
            validate_required_methods(
                Incomplete, Base, ["method1", "method2", "method3"]
            )

    def test_empty_required_list(self):
        """No error when required_methods list is empty."""
        # given
        class Base: ...
        class Derived(Base): ...

        # when / then — should not raise
        validate_required_methods(Derived, Base, [])

    def test_nonexistent_method(self):
        """NotImplementedError for a method that doesn't exist anywhere."""
        # given
        class Base: ...
        class Derived(Base): ...

        # when / then
        with pytest.raises(
            NotImplementedError, match="must implement the 'non_existent' method"
        ):
            validate_required_methods(Derived, Base, ["non_existent"])

    def test_classmethod_inherited_passes(self):
        """Classmethods create new bound methods per class, so inheritance
        does not trigger NotImplementedError."""
        # given
        class Base:
            @classmethod
            def required_classmethod(cls): ...

        class Derived(Base): ...

        # when / then — classmethods produce distinct bound-method objects
        validate_required_methods(Derived, Base, ["required_classmethod"])

    def test_staticmethod_inherited_raises(self):
        """Staticmethods share the same function object, so inheritance
        triggers NotImplementedError."""
        # given
        class Base:
            @staticmethod
            def required_staticmethod(): ...

        class Derived(Base): ...

        # when / then
        with pytest.raises(
            NotImplementedError,
            match="must implement the 'required_staticmethod' method",
        ):
            validate_required_methods(Derived, Base, ["required_staticmethod"])
