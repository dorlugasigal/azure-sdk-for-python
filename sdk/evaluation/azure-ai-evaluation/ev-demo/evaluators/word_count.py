"""Word count evaluator (custom) — auto-discovered by the engine.

This is an example of a custom evaluator. It counts words in the model response.
Create your own evaluators by following this pattern with the @evaluator decorator.
"""
from azure.ai.evaluation._engine.decorators import evaluator, BaseEvaluator


@evaluator(name="word_count")
class WordCountEvaluator(BaseEvaluator):
    """Counts the number of words in the target's response."""

    def compute(self, response: str = "", **kwargs):
        word_count = len(response.split())
        return {"word_count": word_count}

    def aggregate(self, scores):
        values = [s["word_count"] for s in scores]
        return {
            "word_count_mean": round(sum(values) / len(values), 1) if values else 0,
            "word_count_max": max(values) if values else 0,
            "word_count_min": min(values) if values else 0,
        }
