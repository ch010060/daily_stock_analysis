# -*- coding: utf-8 -*-
"""
===================================
Value Network Mermaid Validator (Phase 18A PoC)
===================================

Validates an LLM-generated "value network" Mermaid flowchart before it is
embedded into a report appendix. The LLM output is untrusted free text, so
this module enforces a narrow allowlist (flowchart/graph only, bounded size,
bounded node/subgraph counts, no active-content payloads) and returns None
on any violation so callers can silently omit the appendix.
"""

import re
from typing import Optional

_MAX_LENGTH = 4000
_MAX_DISTINCT_NODES = 40
_MAX_SUBGRAPHS = 8

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

    return text
