"""Baseline target — auto-discovered by the engine."""
from azure.ai.evaluation._engine.decorators import target, BaseTarget


@target(name="baseline")
class BaselineTarget(BaseTarget):
    """Example target that echoes input."""

    def __init__(self, connection_name: str = "default", **kwargs):
        super().__init__(kwargs.get("context"))
        self.connection_name = connection_name

    def infer(self, input_data: dict) -> dict:
        # TODO: Replace with actual model inference
        return {"response": f"Echo: {input_data.get('question', '')}"}
