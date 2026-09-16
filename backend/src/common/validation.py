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


MAX_CANDIDATE_TEXT_LENGTH = 200


def validate_expand_candidates(candidates) -> str | None:
    """Validates model-produced /expand candidates. Returns an error string, or None if valid.

    Deliberately stricter than the base contract shape: rejects duplicate ids/texts, oversized
    text, and unexpected keys, since this is the last line of defense against a schema-constrained
    Bedrock call still returning something we shouldn't show a student.
    """
    if not isinstance(candidates, list) or len(candidates) != 3:
        return "'candidates' must be an array of exactly 3 items"

    seen_ids = set()
    seen_texts = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate.keys()) != {"id", "text"}:
            return "Each candidate must be an object with exactly 'id' and 'text' keys"
        candidate_id = candidate["id"]
        text = candidate["text"]
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            return "Each candidate 'id' must be a non-empty string"
        if not isinstance(text, str) or not text.strip():
            return "Each candidate 'text' must be a non-empty string"
        if len(text) > MAX_CANDIDATE_TEXT_LENGTH:
            return f"Candidate 'text' exceeds {MAX_CANDIDATE_TEXT_LENGTH} characters"
        if candidate_id in seen_ids:
            return "Candidate 'id' values must be unique"
        if text in seen_texts:
            return "Candidate 'text' values must be unique"
        seen_ids.add(candidate_id)
        seen_texts.add(text)

    return None
