"""Custom evaluator example — auto-discovered by the engine via @metric decorator.

Demonstrates how to create your own evaluation metric that runs alongside
built-in evaluators like f1_score and relevance.
"""
from azure.ai.evaluation._engine.decorators import metric, BaseMetric


@metric(name="answer_length")
class AnswerLengthMetric(BaseMetric):
    """Scores answers by length — prefers concise responses (50-200 chars)."""

    def compute(self, response: str = "", **kwargs):
        length = len(response)
        if length == 0:
            score = 0.0
        elif length < 50:
            score = 0.5
        elif length <= 200:
            score = 1.0
        else:
            score = max(0.3, 1.0 - (length - 200) / 500)

        return {
            "answer_length_score": round(score, 3),
            "answer_length_chars": length,
        }

    def aggregate(self, scores):
        score_vals = [s["answer_length_score"] for s in scores]
        char_vals = [s["answer_length_chars"] for s in scores]
        return {
            "answer_length_score_mean": round(sum(score_vals) / len(score_vals), 3),
            "answer_length_chars_mean": round(sum(char_vals) / len(char_vals), 1),
            "answer_length_chars_max": max(char_vals),
            "answer_length_chars_min": min(char_vals),
        }
