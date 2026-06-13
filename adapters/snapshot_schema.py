from typing import Any, Dict, Optional

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore[assignment]


class SnapshotContext(TypedDict, total=False):
    """
    Context dict accepted by GeminiAnalyzer.analyze() via prebuilt injection mode.

    All fields are optional so callers can pass partial snapshots.  The
    pipeline merges whatever is present; missing fields degrade gracefully
    the same way the normal data-fetch path degrades on partial data.
    """
    code: str
    name: str
    market: str
    history: Dict[str, Any]
    today: Dict[str, Any]
    yesterday: Dict[str, Any]
    realtime: Dict[str, Any]
    chip: Dict[str, Any]
    trend: Dict[str, Any]
    fundamental: Dict[str, Any]
    market_phase_context: Dict[str, Any]
    news_context: Optional[str]


def make_minimal_snapshot(code: str, name: str = "") -> SnapshotContext:
    """Return an empty-but-valid snapshot for dry-run / unit-test use."""
    return {  # type: ignore[return-value]
        "code": code,
        "name": name or code,
        "market": "",
        "history": {},
        "today": {},
        "yesterday": {},
        "realtime": {},
        "chip": {},
        "trend": {},
        "fundamental": {},
        "market_phase_context": {},
        "news_context": None,
    }
