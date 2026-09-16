"""Shared request validation. Returns an error string, or None if the request is valid."""
import json

from .icons import ICON_IDS


def parse_json_body(raw_body):
    if raw_body is None or raw_body == "":
        return None, "Request body is required"
    try:
        return json.loads(raw_body), None
    except (json.JSONDecodeError, TypeError):
        return None, "Request body must be valid JSON"


def validate_expand_request(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return "Request body must be a JSON object"
    icons = payload.get("icons")
    if not isinstance(icons, list) or len(icons) == 0:
        return "'icons' is required and must be a non-empty array"
    if not all(isinstance(icon, str) for icon in icons):
        return "'icons' must contain only strings"
    unknown = [icon for icon in icons if icon not in ICON_IDS]
    if unknown:
        return f"Unknown icon id(s): {unknown}"
    profile_id = payload.get("profileId")
    if not isinstance(profile_id, str) or not profile_id.strip():
        return "'profileId' is required and must be a non-empty string"
    if not isinstance(payload.get("context"), str):
        return "'context' is required and must be a string (may be empty)"
    return None


def validate_simplify_request(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return "Request body must be a JSON object"
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return "'text' is required and must be a non-empty string"
    return None
