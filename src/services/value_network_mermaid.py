# -*- coding: utf-8 -*-
"""
===================================
Value Network Mermaid Validator (Phase 18A PoC; tightened in Phase 18E,
re-tuned in Phase 18E v3 for the dagre-constrained 4-section A4 layout)
===================================

Validates an LLM-generated "value network" Mermaid flowchart before it is
embedded into a report appendix. The LLM output is untrusted free text, so
this module enforces a narrow allowlist (flowchart/graph only, bounded size,
bounded node/subgraph/edge counts, safe ASCII node/subgraph ids, no nested
subgraphs, no active-content payloads) and returns None on any violation so
callers can silently omit the appendix.

Phase 18E v3 re-tuned the limits for a fixed 4-section (供應商/客戶/競爭者/
互補者) x 3-card + 1-center layout (13 visible nodes nominal, up to 17 if a
strategic card is folded into a section): 22 nodes, 4 top-level subgraphs,
16 visible edges. It also added nested-subgraph rejection and subgraph-id
safety checks, since those are exactly the kind of malformed input the
dagre-layout topology depends on the LLM getting right.

Note on `~~~` (invisible layout-only links): these are intentionally NOT
counted by `_EDGE_RE`/`_MAX_EDGES`. They exist purely to force dagre to
rank same-section cards into a vertical column instead of spreading them
horizontally (see docs/phase-18e-value-network-2x2-handover.md section 2.3)
and carry no "business relationship" semantics, so counting them against
the visible-edge budget would only push real card counts down for no
safety benefit. Do not "fix" this by making `_EDGE_RE` match `~~~`.

The `%%{init...}%%` styling directive is intentionally never produced by
the LLM (it is prepended deterministically by history_service.py after
validation passes) — this module rejects it outright wherever it appears,
both because the existing first-line direction check already fails closed
if it appears as line 1, and explicitly via `_INIT_DIRECTIVE_RE` if it
appears anywhere else in the body.
"""

import re
from typing import Optional

_MAX_LENGTH = 4000
_MAX_DISTINCT_NODES = 22
_MAX_SUBGRAPHS = 4
_MAX_EDGES = 16

_TRIPLE_BACKTICK_RE = re.compile(r"```")
# Phase 18E v3: the A4-portrait 4-section layout only works top-to-bottom —
# LR (and the other direction synonyms TD/BT/RL) would lay the sections out
# horizontally, defeating the whole point of this appendix. TB is the only
# accepted direction now (was TB/TD/BT/RL/LR).
_DIRECTION_HEADER_RE = re.compile(r"^(flowchart|graph)\s+TB\b", re.IGNORECASE)
_FORBIDDEN_DIAGRAM_TYPES_RE = re.compile(
    r"(sequenceDiagram|classDiagram|erDiagram|gitGraph|stateDiagram|journey|pie|gantt)",
    re.IGNORECASE,
)
_DANGEROUS_PATTERN_RE = re.compile(
    r"(<script|<iframe|javascript:|\bon[a-z]+\s*=|https?://)",
    re.IGNORECASE,
)
_INIT_DIRECTIVE_RE = re.compile(r"%%\s*\{\s*init\b", re.IGNORECASE)
_NODE_ID_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*[\[\(\{]")
_SUBGRAPH_LINE_RE = re.compile(r"^\s*subgraph\b", re.IGNORECASE | re.MULTILINE)
_SUBGRAPH_ID_RE = re.compile(r"^\s*subgraph\s+(\S+)", re.IGNORECASE | re.MULTILINE)
_SAFE_SUBGRAPH_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_END_LINE_RE = re.compile(r"^\s*end\s*$", re.IGNORECASE | re.MULTILINE)

# An unquoted "[...]" label containing "(" — e.g. "S1[Intel (INTC.US)]"
# instead of 'S1["Intel (INTC.US)"]'. This is not a style nit: mermaid's
# real flowchart parser fails outright on this (confirmed against the
# installed mermaid package — the "(" mid-label is read as the start of a
# round-node shape token, not label text), so the LLM-favored "Company
# (TICKER)" card format *requires* quoted labels whenever it contains a
# parenthesis. Reject early rather than let it reach the renderer as a
# silent fallback.
_UNQUOTED_LABEL_WITH_PAREN_RE = re.compile(r'\[(?!")[^\[\]"]*\([^\[\]]*\]')

# Matches the arrow forms our prompts ask for: "-->", "-.->", and the dotted
# inline-label form "-.label.->". Deliberately does not match "~~~"
# (invisible layout-only links) — see module docstring.
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


def _strip_bracket_label_content(text: str) -> str:
    """Strip the inside of node/subgraph label brackets (quoted or not).

    Card labels routinely contain "Company (TICKER.US)"-style parentheses
    and CJK text (e.g. `S1[Intel (INTC.US)<br/>CPU供應商]`), which would
    otherwise be misread by the structural regexes below as a bogus node id
    ("Intel" before "(") or a CJK-as-edge-endpoint false positive. Mermaid
    labels do not nest the same bracket type, so a single non-nesting pass
    per bracket type is sufficient for this validator's purposes (it does
    not need to be a full parser).
    """
    masked = re.sub(r"\[[^\[\]]*\]", "[]", text)
    masked = re.sub(r"\([^()]*\)", "()", masked)
    masked = re.sub(r"\{[^{}]*\}", "{}", masked)
    return masked


def _has_nested_subgraph(text: str) -> bool:
    """Return True if a `subgraph` line appears while already inside one.

    Walks lines in order tracking depth via `subgraph`/`end` markers — a
    simple stack-depth counter, not just a raw count of `subgraph` lines,
    so two *sibling* subgraphs (depth goes 0->1->0->1) are not mistaken for
    nesting (depth 0->1->2).
    """
    depth = 0
    for line in text.splitlines():
        if _SUBGRAPH_LINE_RE.match(line):
            if depth > 0:
                return True
            depth += 1
        elif _END_LINE_RE.match(line):
            depth = max(0, depth - 1)
    return False


def _has_unsafe_subgraph_id(text: str) -> bool:
    """Return True if any `subgraph <id>` id is not a safe ASCII identifier."""
    for match in _SUBGRAPH_ID_RE.finditer(text):
        subgraph_id = match.group(1).split("[", 1)[0].split("(", 1)[0]
        if not _SAFE_SUBGRAPH_ID_RE.match(subgraph_id):
            return True
    return False


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

    if _INIT_DIRECTIVE_RE.search(text):
        return None

    first_line = text.splitlines()[0].strip()
    if not _DIRECTION_HEADER_RE.match(first_line):
        return None

    if _FORBIDDEN_DIAGRAM_TYPES_RE.search(text):
        return None

    if _DANGEROUS_PATTERN_RE.search(text):
        return None

    if _UNQUOTED_LABEL_WITH_PAREN_RE.search(text):
        return None

    # Structural checks (node/edge/subgraph counting, id safety) must not be
    # confused by label content — see _strip_bracket_label_content. Keep
    # using the *original* `text` for the security checks above, which must
    # still see inside labels for things like a literal <script> string.
    masked = _strip_bracket_label_content(text)

    distinct_nodes = {match.group(1) for match in _NODE_ID_RE.finditer(masked)}
    if len(distinct_nodes) > _MAX_DISTINCT_NODES:
        return None

    subgraph_count = len(_SUBGRAPH_LINE_RE.findall(masked))
    if subgraph_count > _MAX_SUBGRAPHS:
        return None

    if len(_EDGE_RE.findall(masked)) > _MAX_EDGES:
        return None

    if _DIGIT_LEADING_NODE_ID_RE.search(masked):
        return None

    if _CJK_AS_EDGE_ENDPOINT_RE.search(masked):
        return None

    if _has_nested_subgraph(masked):
        return None

    if _has_unsafe_subgraph_id(masked):
        return None

    return text
