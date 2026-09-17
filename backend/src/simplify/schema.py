"""Bedrock tool-use schema for /simplify. Frozen shape per PLAN.md's API contract
(PLAN.md:36-38) — coordinate with Ben before changing; do not diverge unilaterally.

The Lambda passes this as the single tool in a Bedrock tool-use call and forces
tool_choice onto it, so the model can only emit arguments matching this schema.
Lambda-side validation against this same shape gives the "1 retry, then labeled
fallback" behavior described in PLAN.md's design rules.
"""
from ..common.icons import ICON_IDS, QUICK_REPLY_IDS, PLEASE_REPEAT

SIMPLIFY_TOOL_NAME = "emit_simplification"

SIMPLIFY_TOOL_SCHEMA = {
    "name": SIMPLIFY_TOOL_NAME,
    "description": (
        "Emit the simplified icon-sequence representation of a peer's spoken/typed message "
        "for an AAC user. Preserve objects, order, quantities, and negation exactly. If the "
        "input is ambiguous or you are not confident in the meaning, set status to "
        f"'{PLEASE_REPEAT}' and leave steps/warnings empty rather than guessing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["ok", "please_repeat"],
                "description": (
                    "'please_repeat' when the input is too ambiguous, low-confidence, or "
                    "garbled to simplify safely. 'ok' otherwise."
                ),
            },
            "steps": {
                "type": "array",
                "description": (
                    "Ordered, non-negation steps of the instruction/message, one per clause, "
                    "in the same order as the source. Empty when status is 'please_repeat'."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "icons": {
                            "type": "array",
                            "items": {"type": "string", "enum": sorted(ICON_IDS)},
                            "minItems": 1,
                        },
                        "label": {
                            "type": "string",
                            "description": "Short plain-language label for this step, derived only from the source text.",
                        },
                    },
                    "required": ["icons", "label"],
                },
            },
            "warnings": {
                "type": "array",
                "description": (
                    "Mandatory-to-render items: negations, safety cautions, anything the "
                    "speaker framed as 'don't'/'make sure not'/'off'/'stop'. Always include "
                    "STOP and/or CHECK among the icons for a warning. Empty when status is "
                    "'please_repeat'."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "icons": {
                            "type": "array",
                            "items": {"type": "string", "enum": sorted(ICON_IDS)},
                            "minItems": 1,
                        },
                        "label": {"type": "string"},
                    },
                    "required": ["icons", "label"],
                },
            },
            "quickReplies": {
                "type": "array",
                "description": "Zero or more quick-reply options the AAC user might want to send back.",
                "items": {"type": "string", "enum": sorted(QUICK_REPLY_IDS)},
            },
        },
        "required": ["status", "steps", "warnings", "quickReplies"],
    },
}


def _valid_icon_group(items) -> bool:
    if not isinstance(items, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("label"), str)
        and isinstance(item.get("icons"), list)
        and len(item["icons"]) > 0
        and all(icon in ICON_IDS for icon in item["icons"])
        for item in items
    ):
        return False
    return True


def validate_simplify_tool_output(candidate: dict) -> str | None:
    """Validate a Bedrock tool-use response against SIMPLIFY_TOOL_SCHEMA's shape.

    Returns an error string, or None if valid. Used for the "1 retry, then labeled
    fallback" behavior described in PLAN.md's design rules.
    """
    if not isinstance(candidate, dict):
        return "Tool output must be a JSON object"

    status = candidate.get("status")
    if status not in ("ok", "please_repeat"):
        return "'status' must be 'ok' or 'please_repeat'"

    if not _valid_icon_group(candidate.get("steps")):
        return "'steps' must be a list of {icons, label} with only known icon ids"
    if not _valid_icon_group(candidate.get("warnings")):
        return "'warnings' must be a list of {icons, label} with only known icon ids"

    quick_replies = candidate.get("quickReplies")
    if not isinstance(quick_replies, list) or not all(
        reply in QUICK_REPLY_IDS for reply in quick_replies
    ):
        return "'quickReplies' must contain only known quick-reply ids"

    if status == "please_repeat" and (candidate.get("steps") or candidate.get("warnings")):
        return "'please_repeat' responses must have empty steps and warnings"

    return None
