# -*- coding: utf-8 -*-
"""
===================================
Value Network Mermaid Validator (Phase 18A PoC, tightened in Phase 18E)
===================================

Validates an LLM-generated "value network" Mermaid flowchart before it is
embedded into a report appendix. The LLM output is untrusted free text, so
this module enforces a narrow allowlist (flowchart/graph only, bounded size,
bounded node/subgraph/edge counts, safe ASCII node ids, no active-content
payloads) and returns None on any violation so callers can silently omit
the appendix.

Phase 18E tightened the size limits from a loose PoC backstop (40 nodes, 8
subgraphs) to an actual compact-appendix quality gate (18 nodes, 5
subgraphs, 12 edges), and added two structural checks the prompt alone
cannot guarantee: node ids must be ASCII and must not start with a digit
(both are invalid/unreliable Mermaid identifiers), and CJK text must not be
used directly as an edge endpoint instead of inside a node label.
"""

import re
from typing import Optional

_MAX_LENGTH = 4000
_MAX_DISTINCT_NODES = 18
_MAX_SUBGRAPHS = 5
_MAX_EDGES = 12

_TRIPLE_BACKTICK_RE = re.compile(r"```")
_DIRECTION_HEADER_RE = re.compile(r"^(flowchart|graph)\s+(TB|TD|BT|RL|LR)\b", re.IGNORECASE)
_FORBIDDEN_DIAGRAM_TYPES_RE = re.compile(
    r"(sequenceDiagram|classDiagram|erDiagram|gitGraph|stateDiagram|journey|pie|gantt)",
    re.IGNORECASE,
)
_DANGEROUS_PATTERN_RE = re.compile(
    r"(<script|<iframe|javascript:|\bon[a-z]+\s*=|https?://)",
    re.IGNORECASE,
)
_NODE_ID_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*[\[\(\{]")
_SUBGRAPH_LINE_RE = re.compile(r"^\s*subgraph\b", re.IGNORECASE | re.MULTILINE)

# Matches the arrow forms our prompts ask for: "-->", "-.->", and the dotted
# inline-label form "-.label.->".
_ARROW = r"(?:-{1,3}>|-\.[^\n]{0,60}?\.->|-\.->)"
_EDGE_RE = re.compile(_ARROW)

# A node definition ("id[...]"/"id(...)"/"id{...}") whose id starts with a
# digit, e.g. "5G_SoC[...]" — invalid/unreliable as a Mermaid identifier.
_DIGIT_LEADING_NODE_ID_RE = re.compile(r"^[ \t]*\d[A-Za-z0-9_]*\s*[\[\(\{]", re.MULTILINE)

# CJK text used directly as an edge endpoint (e.g. "聯發科 --> TSMC" or
# "A --> 台積電") instead of only ever appearing inside a node label.
_CJK_AS_EDGE_ENDPOINT_RE = re.compile(
    rf"[一-鿿][一-鿿\w]*(?:\([^)]{{0,30}}\))?\s*{_ARROW}"
    rf"|{_ARROW}\s*(?:\|[^|]*\|\s*)?[一-鿿]"
)


def validate_value_network_mermaid(raw: Optional[str]) -> Optional[str]:
    """Validate an LLM-generated value-network Mermaid block.

    Returns the trimmed Mermaid body when it passes all checks, otherwise
    None so the caller can omit the appendix without failing the report.
    """
    if not raw or not isinstance(raw, str):
        return None

    text = raw.strip()
    if not text:
        return None

    if len(text) > _MAX_LENGTH:
        return None

    if _TRIPLE_BACKTICK_RE.search(text):
        return None

    first_line = text.splitlines()[0].strip()
    if not _DIRECTION_HEADER_RE.match(first_line):
        return None

    if _FORBIDDEN_DIAGRAM_TYPES_RE.search(text):
        return None

    if _DANGEROUS_PATTERN_RE.search(text):
        return None

    distinct_nodes = {match.group(1) for match in _NODE_ID_RE.finditer(text)}
    if len(distinct_nodes) > _MAX_DISTINCT_NODES:
        return None

    subgraph_count = len(_SUBGRAPH_LINE_RE.findall(text))
    if subgraph_count > _MAX_SUBGRAPHS:
        return None

    if len(_EDGE_RE.findall(text)) > _MAX_EDGES:
        return None

    if _DIGIT_LEADING_NODE_ID_RE.search(text):
        return None

    if _CJK_AS_EDGE_ENDPOINT_RE.search(text):
        return None

    return text
