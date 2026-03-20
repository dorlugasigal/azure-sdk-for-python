"""Custom metric for remote evaluation — must use only sandbox-available packages."""
from azure.ai.evaluation._engine.decorators import metric, BaseMetric


@metric(name="conciseness")
class ConcisenessMetric(BaseMetric):
    """Scores response conciseness — prefers 50-200 character answers."""

    def compute(self, response: str = ""):
        length = len(response)
        if length == 0:
            score = 0.0
        elif length < 50:
            score = 0.5
        elif length <= 200:
            score = 1.0
        else:
            score = max(0.3, 1.0 - (length - 200) / 500)
        return {"conciseness_score": round(score, 3)}

    def aggregate(self, scores):
        vals = [s["conciseness_score"] for s in scores]
        return {"conciseness_score_mean": round(sum(vals) / len(vals), 3)}
