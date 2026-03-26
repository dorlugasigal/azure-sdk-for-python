# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""CLI constants, built-in evaluator lists, and ASCII art."""
from __future__ import annotations

import os
from typing import Optional

# Ordered list of config file names the CLI will search for.
CONFIG_CANDIDATES = ["config.yaml", "evals.yaml", "experiment/config.yaml"]

DEFAULT_CONFIG = "config.yaml"


def resolve_config_path(explicit: Optional[str] = None) -> str:
    """Return the path to the project config file.

    If *explicit* is given (user passed ``--config``), return it as-is.
    Otherwise search :data:`CONFIG_CANDIDATES` in the current directory
    and return the first match, falling back to :data:`DEFAULT_CONFIG`.
    """
    if explicit is not None:
        return explicit
    for candidate in CONFIG_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return DEFAULT_CONFIG

EV_ASCII = (
    '               [#6e6c89]_[/][#655d8f]-[/][#655691]=[/][#695491]=[/][#6f5490]=[/][#75548f]=[/][#784a85]y[/][#70386f]#[/][#754572]m[/]\n'
    '             [#596698],[/][#3446ac]E[/][#3641a9]$[/][#393ea4]$[/][#3e3ca1]$[/][#453ca0]$[/][#4c3c9e]$[/][#553d9d]L[/][#6e2884]$[/][#83146f]N[/][#871470]N[/][#8a2374]N[/]\n'
    '            [#53699f],[/][#254fbf]@[/][#284dbb]@[/][#2b4bb8]@[/][#2e48b3]@[/][#3146af]@[/][#3443ab]@[/][#3740a7]$[/][#3b3da2]$[/][#72288b]N[/][#a21579]N[/][#a5167a]N[/][#a8167c]N[/][#93527f],[/]\n'
    '            [#1c57cb]N[/][#1d56c9]@[/][#1f54c6]@[/][#2252c3]@[/][#2450c0]@[/][#264ebd]@[/][#294cba]@[/][#2c4ab6]@[/][#2f47b2]@[/][#782891]0[/][#ba1782]N[/][#bd1782]N[/][#bf1783]N[/][#c01a84]@[/]         [#364daf];[/][#364daf]########[/][#364daf]W[/]             [#364daf]_[/][#364daf],[/]\n'
    '           [#1a5fcf]@[/][#165dd2]N[/][#185bd0]N[/][#195acf]N[/][#1b58cc]N[/][#1d56ca]N[/][#1e55c8]@[/][#2053c5]@[/][#2351c2]@[/][#254fbf]@[/][#7d2796]@[/][#cc1888]E[/][#c41a8a]@[/][#792997]@[/][#4b329f]@[/][#3744a9]P[/][#354cae]P[/][#354caf]P[/][#354caf]P[/][#364dae]P[/]    [#364daf]\\[[/][#364daf]BB[/][#364daf]B[/][#364daf]MMMMM[/][#364daf]M[/]           [#364daf]z[/][#364daf]0[/][#364daf]B[/][#364daf]R[/]\n'
    '          [#2567c8]$[/][#1161d9]N[/][#1260d7]N[/][#135fd6]N[/][#145ed5]N[/][#155dd3]N[/][#175cd1]N[/][#185bcf]N[/][#1a59ce]N[/][#1b58cb]N[/][#1d56c9]@[/][#802698]E[/][#c81b8d]$[/][#2948b8]@[/][#2550c0]@[/][#2550c0]@[/][#2550c0]@[/][#2550c0]@[/][#2550c0]@[/][#2550c0]@[/][#2550c0]@[/]    [#364daf]\\[[/][#364daf]BB[/][#364daf]L[/]       [#364daf]WW[/][#364daf]m[/]     [#364daf]z[/][#364daf]B[/][#364daf]B[/][#364daf]R[/][#364daf]"[/]\n'
    '         [#3e6fb5]|[/][#0d64dd]N[/][#0e63dc]N[/][#0f62db]N[/][#1062da]N[/][#1061d9]N[/][#1160d8]N[/][#1260d7]N[/][#135fd5]N[/][#155ed4]N[/][#165dd2]N[/][#175cd1]N[/][#7c2698]@[/][#982193]$[/][#1c57ca]@[/][#1c57ca]@[/][#1c57ca]@[/][#1c57ca]@[/][#1c57ca]@[/][#1c57ca]@[/][#1c57ca]@[/]    [#364daf]\\[[/][#364daf]BB[/][#364daf]@[/][#364daf]@@@@[/][#364daf]@[/]  [#364daf]1[/][#364daf]BB[/][#364daf]K[/]   [#364daf]0[/][#364daf]B[/][#364daf]B[/][#364daf]M[/]\n'
    '        [#5c789d]_[/][#0b65e0]N[/][#0c65df]N[/][#0c65df]N[/][#0d64de]N[/][#0d64dd]N[/][#0e63dc]N[/][#0f62db]N[/][#0f62db]N[/][#1061da]N[/][#1161d8]N[/][#1260d7]N[/][#135fd6]N[/][#6e2494]@[/][#85208f]@[/][#165cd2]N[/][#165cd2]N[/][#165cd2]N[/][#165cd2]N[/][#165cd2]N[/][#165cd2]N[/][#165cd2]N[/][#165cd2]N[/]    [#364daf]\\[[/][#364daf]BB[/][#364daf]B[/][#364daf]"""""[/]   [#364daf]T[/][#364daf]B[/][#364daf]B[/][#364daf]N[/][#364daf],[/][#364daf]B[/][#364daf]BB[/][#364daf]"[/]\n'
    '        [#0c68e0]N[/][#0a67e2]N[/][#0b66e1]N[/][#0b66e1]N[/][#0b66e0]N[/][#0c65e0]N[/][#0c65df]N[/][#0c65df]N[/][#0d64de]N[/][#0e63dd]N[/][#0e63dc]N[/][#0f62db]N[/][#1062da]N[/][#5a228d]@[/][#6a1f87]@[/][#1160d9]N[/][#1160d9]N[/][#1160d9]N[/][#1160d9]N[/][#1160d9]N[/][#1160d9]N[/][#1561d6]B[/][#4f71a6]`[/]    [#364daf]\\[[/][#364daf]BB[/][#364daf]L[/]         [#364daf]0[/][#364daf]B[/][#364daf]BBBB[/][#364daf]"[/]\n'
    '       [#196bd6]@[/][#0a68e3]N[/][#0a68e3]N[/][#0a67e2]N[/][#0a67e2]N[/][#0a67e2]N[/][#0a67e2]N[/][#0b66e1]N[/][#0b66e1]N[/][#0b66e0]N[/][#0c65e0]N[/][#0c65df]N[/][#0d64de]N[/][#0d64dd]N[/][#4b4f8f]P[/][#6e5b80]`[/][#5474a3]`[/][#5474a3]`[/][#5474a3]`[/][#5474a3]`[/][#5875a0]`[/]       [#364daf]\\[[/][#364daf]BB[/][#364daf]BBBBBB[/][#364daf]B[/]    [#364daf]0[/][#364daf]B[/][#364daf]B[/][#364daf]B[/][#364daf]"[/]\n'
    '      [#3070c2]][/][#0968e3]N[/][#0968e3]N[/][#0968e3]N[/][#0a68e3]N[/][#0a68e3]N[/][#0a68e3]N[/][#0a68e3]N[/][#0a67e2]N[/][#0a67e2]N[/][#0a67e2]N[/][#0b66e1]N[/][#0b66e1]N[/][#0b66e1]N[/][#0c65e0]N[/]               [#364daf]""""""""[/][#364daf]"[/]     [#364daf]""[/]\n'
    '     [#5176a7],[/][#0968e4]N[/][#0968e4]N[/][#0968e3]N[/][#0968e3]N[/][#0968e3]N[/][#0968e3]N[/][#0968e3]N[/][#0968e3]N[/][#0a68e3]N[/][#0a68e3]N[/][#0a68e3]N[/][#0a67e2]N[/][#0a67e2]N[/][#0a67e2]N[/][#0b67e1]N[/]\n'
    '     [#0969e4]N[/][#0968e4]N[/][#0968e4]N[/][#0968e4]N[/][#0968e4]N[/][#0968e4]N[/][#0968e3]N[/][#0968e3]N[/][#0968e3]N[/][#0968e3]N[/][#0968e3]N[/][#0968e3]N[/][#0a68e3]N[/][#0968e3]N[/][#1e6cd1]P[/]\n'
    '    [#5e799b]`[/][#4374b2]"[/][#4374b2]"[/][#4374b2]"[/][#4374b2]"[/][#4374b2]"[/][#4474b2]"[/][#4473b2]"[/][#4473b2]"[/][#4473b2]"[/][#4473b2]"[/][#4473b2]"[/][#4874ae]"[/][#5777a1]`[/]'
)

BUILTIN_EVALUATORS = [
    ("f1_score", "local", "F1 score (precision/recall)"),
    ("bleu", "local", "BLEU score for translation quality"),
    ("rouge", "local", "ROUGE score for summarization quality"),
    ("meteor", "local", "METEOR score for translation quality"),
    ("gleu", "local", "GLEU score for translation quality"),
    ("relevance", "cloud", "Relevance (LLM-as-Judge, 1-5)"),
    ("coherence", "cloud", "Coherence scoring"),
    ("fluency", "cloud", "Fluency scoring"),
    ("groundedness", "cloud", "Groundedness scoring"),
    ("similarity", "cloud", "Semantic similarity"),
    ("qa", "cloud", "Question-answering quality"),
    ("content_safety", "cloud", "Content safety evaluation"),
    ("protected_material", "cloud", "Protected material detection"),
    ("retrieval", "cloud", "Retrieval quality scoring"),
    ("document_retrieval", "cloud", "Document retrieval evaluation"),
    ("response_completeness", "cloud", "Response completeness scoring"),
    ("intent_resolution", "cloud", "Intent resolution accuracy"),
    ("task_adherence", "cloud", "Task adherence scoring"),
    ("task_completion", "cloud", "Task completion evaluation"),
    ("tool_call_accuracy", "cloud", "Tool call accuracy evaluation"),
    ("tool_call_success", "cloud", "Tool call success rate"),
    ("tool_selection", "cloud", "Tool selection accuracy"),
    ("tool_input_accuracy", "cloud", "Tool input parameter accuracy"),
    ("tool_output_utilization", "cloud", "Tool output utilization"),
    ("code_vulnerability", "cloud", "Code vulnerability detection"),
    ("service_groundedness", "cloud", "Service groundedness scoring"),
    ("eci", "cloud", "ECI scoring"),
    ("xpia", "cloud", "Cross-prompt injection detection"),
    ("ungrounded_attributes", "cloud", "Ungrounded attribute detection"),
]
