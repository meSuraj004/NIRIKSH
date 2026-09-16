"""Field extraction: aggregated LLM output -> normalized declarations.

Every detected value is attributed to the source image whose OCR transcript
actually contains it. Values that cannot be located in any transcript are kept
but marked UNCERTAIN (possible LLM invention or heavy normalization); they are
never silently confirmed and never dropped. Missing fields stay NOT_DETECTED.
"""

import json
import re

DETECTED = "DETECTED"
NOT_DETECTED = "NOT_DETECTED"
UNCERTAIN = "UNCERTAIN"

EXCLUDED_SECTIONS = {"compliance_summary"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _value_in_transcript(value: str, transcript: str) -> bool:
    v = _normalize(value)
    if v and v in _normalize(transcript):
        return True
    d = _digits(value)
    if len(d) >= 3 and d in _digits(transcript):
        return True
    return False


def _find_source_view(value: str, evidence: list[dict]) -> int | None:
    for item in evidence:
        if _value_in_transcript(value, item["text"]):
            return item["view_index"]
    return None


def _to_stored(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False) if value else None
    if isinstance(value, bool):
        return json.dumps(value)
    return str(value)


def _list_supported(value: list, transcript: str) -> bool:
    elements = [e for e in value if isinstance(e, str) and e.strip()]
    if not elements:
        return False
    matched = sum(1 for e in elements if _value_in_transcript(e, transcript))
    return matched >= max(1, len(elements) // 2)


def _find_source_view_for_list(value: list, evidence: list[dict]) -> int | None:
    for item in evidence:
        if _list_supported(value, item["text"]):
            return item["view_index"]
    return None


def build_declarations(aggregated: dict, evidence: list[dict]) -> list[dict]:
    """Builds normalized declaration rows from aggregated data.

    Args:
        aggregated: structured output of the LLM aggregator (sections -> fields).
        evidence: per-image OCR evidence, entries {"view_index": int, "text": str}.

    Returns:
        Rows with field_name, value, status, source_view, extraction_method.
        No confidence is assigned: the vision/aggregation stack does not expose
        per-field confidence scores, so fabricating one is not allowed.
    """
    if not isinstance(aggregated, dict):
        return []

    rows: list[dict] = []
    for section, fields in aggregated.items():
        if not isinstance(fields, dict) or section in EXCLUDED_SECTIONS:
            continue
        for name, raw in fields.items():
            if isinstance(raw, dict):
                continue

            stored = _to_stored(raw)
            row = {
                "field_name": f"{section}.{name}",
                "value": stored,
                "status": NOT_DETECTED,
                "source_view": None,
                "extraction_method": "groq_vlm_aggregation",
            }

            if stored is not None:
                if isinstance(raw, list):
                    source_view = _find_source_view_for_list(raw, evidence)
                else:
                    source_view = _find_source_view(stored, evidence)
                if source_view is not None:
                    row["status"] = DETECTED
                    row["source_view"] = source_view
                else:
                    row["status"] = UNCERTAIN

            rows.append(row)
    return rows
