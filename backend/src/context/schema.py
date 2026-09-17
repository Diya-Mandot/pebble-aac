"""Bedrock tool-use schema for POST /context/update (CONTEXT_PIPELINE_PLAN.md Track D).

The model always emits a `flaggedMoment` object with an explicit `present` boolean rather than an
omittable key -- Bedrock tool-use forces a fixed shape, so "no flagged moment" is represented as
`{present: false, label: "", icons: []}` here and only collapsed to an absent key at the wiring
layer (see common/bedrock.py's _transform_context_tool_output), right before the response leaves
the Lambda. Fixtures are stored in this same raw, `present`-explicit shape so they can be validated
against this schema directly (mirrors simplify/schema.py's validate_simplify_tool_output).

Each `dynamicIcons` item's `symbol` field uses the same sentinel pattern: the model always emits a
bank id or the literal string "none" (see ./symbols.py), and "none" is collapsed to an absent key
at the same wiring-layer step, right before the response leaves the Lambda.
"""
from ..common.icons import ICON_IDS
from .symbols import SYMBOL_ENUM

CONTEXT_TOOL_NAME = "emit_context_update"

CONTEXT_TOOL_SCHEMA = {
    "name": CONTEXT_TOOL_NAME,
    "description": (
        "Emit an updated rolling summary, a small set of topic words for a dynamic AAC icon row, "
        "and (rarely) a flagged moment -- a safety warning or a question directly addressed to "
        "the student. Never fabricate content not present in the supplied raw window; when "
        "unsure whether something is a flagged moment, set flaggedMoment.present to false."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "Updated 1-3 sentence rolling summary folding the raw window into the prior "
                    "summary. Only what was actually said -- no invented people, events, or plans."
                ),
            },
            "dynamicIcons": {
                "type": "array",
                "description": (
                    "At most 6 concrete nouns/verbs actually present in the raw window, most "
                    "topic-relevant first. Empty is fine if nothing concrete came up."
                ),
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "word": {"type": "string", "minLength": 1},
                        "symbol": {
                            "type": "string",
                            "enum": SYMBOL_ENUM,
                            "description": (
                                "Bank id that literally depicts the word in this context, or "
                                "'none' when nothing fits well."
                            ),
                        },
                    },
                    "required": ["word", "symbol"],
                },
            },
            "flaggedMoment": {
                "type": "object",
                "description": (
                    "present=true only for high-confidence safety/warning content or a direct "
                    "question addressed to the student. Default to present=false when ambiguous."
                ),
                "properties": {
                    "present": {"type": "boolean"},
                    "label": {
                        "type": "string",
                        "description": "Short plain-language description. '' when present is false.",
                    },
                    "icons": {
                        "type": "array",
                        "items": {"type": "string", "enum": sorted(ICON_IDS)},
                        "description": "[] when present is false.",
                    },
                },
                "required": ["present", "label", "icons"],
            },
        },
        "required": ["summary", "dynamicIcons", "flaggedMoment"],
    },
}


def _valid_dynamic_icons(items) -> bool:
    if not isinstance(items, list) or len(items) > 6:
        return False
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item.keys()) != {"word", "symbol"}:
            return False
        word = item["word"]
        symbol = item["symbol"]
        if not isinstance(word, str) or not word.strip():
            return False
        if not isinstance(symbol, str) or symbol not in SYMBOL_ENUM:
            return False
        normalized = word.strip().lower()
        if normalized in seen:
            return False
        seen.add(normalized)
    return True


def _valid_flagged_moment(candidate) -> bool:
    if not isinstance(candidate, dict) or set(candidate.keys()) != {"present", "label", "icons"}:
        return False
    present, label, icons = candidate["present"], candidate["label"], candidate["icons"]
    if not isinstance(present, bool) or not isinstance(label, str) or not isinstance(icons, list):
        return False
    if not all(isinstance(icon, str) and icon in ICON_IDS for icon in icons):
        return False
    if present:
        return bool(label.strip()) and len(icons) > 0
    return label == "" and icons == []


def validate_context_tool_output(candidate: dict) -> str | None:
    """Validate a Bedrock tool-use response against CONTEXT_TOOL_SCHEMA's shape.

    Returns an error string, or None if valid. Used for the "1 retry, then labeled fallback"
    behavior described in PLAN.md's design rules, and to check context_fixtures.json stays
    self-consistent with this schema.
    """
    if not isinstance(candidate, dict):
        return "Tool output must be a JSON object"

    if set(candidate.keys()) != {"summary", "dynamicIcons", "flaggedMoment"}:
        return "Tool output must contain exactly: ['dynamicIcons', 'flaggedMoment', 'summary']"

    if not isinstance(candidate.get("summary"), str):
        return "'summary' must be a string"

    if not _valid_dynamic_icons(candidate.get("dynamicIcons")):
        return "'dynamicIcons' must be at most 6 unique {word, symbol} objects"

    if not _valid_flagged_moment(candidate.get("flaggedMoment")):
        return "'flaggedMoment' must be {present, label, icons}, with label/icons empty iff present is false"

    return None
