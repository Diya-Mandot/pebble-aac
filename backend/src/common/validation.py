"""Shared request validation. Returns an error string, or None if the request is valid."""
import json

from jsonschema import Draft202012Validator

from .icons import ICON_IDS
from ..expand.prompt import EXPAND_OUTPUT_SCHEMA


_EXPAND_OUTPUT_VALIDATOR = Draft202012Validator(EXPAND_OUTPUT_SCHEMA)


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


def validate_expand_output(payload: object) -> str | None:
    """Return the first schema or candidate-identity error, if any."""
    errors = sorted(
        _EXPAND_OUTPUT_VALIDATOR.iter_errors(payload), key=lambda error: list(error.path)
    )
    if errors:
        return errors[0].message

    candidates = payload["candidates"]
    candidate_ids = [candidate["id"] for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        return "Candidate ids must be unique"
    return None
