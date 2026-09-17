"""Shared request validation. Returns an error string, or None if the request is valid."""
import json
import re

from jsonschema import Draft202012Validator

from .icons import ICON_IDS, QUICK_REPLY_IDS
from ..context.symbols import SYMBOL_IDS
from ..expand.prompt import EXPAND_OUTPUT_SCHEMA

_EXPAND_OUTPUT_VALIDATOR = Draft202012Validator(EXPAND_OUTPUT_SCHEMA)


def parse_json_body(raw_body):
    if raw_body is None or raw_body == "":
        return None, "Request body is required"
    try:
        return json.loads(raw_body), None
    except (json.JSONDecodeError, TypeError):
        return None, "Request body must be valid JSON"


MAX_EXPAND_TOKENS = 16
MAX_EXPAND_WORDS = 6


def validate_expand_request(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return "Request body must be a JSON object"

    tokens = payload.get("tokens")
    if not isinstance(tokens, list) or len(tokens) == 0:
        return "'tokens' is required and must be a non-empty array"
    if len(tokens) > MAX_EXPAND_TOKENS:
        return f"'tokens' exceeds {MAX_EXPAND_TOKENS} items"

    seen_words = set()
    word_count = 0
    for token in tokens:
        if not isinstance(token, dict) or "kind" not in token:
            return "Each 'tokens' item must be an object with a 'kind'"
        kind = token["kind"]
        if kind == "icon":
            if set(token.keys()) != {"kind", "id"}:
                return "Each icon token must have exactly 'kind' and 'id' keys"
            if token["id"] not in ICON_IDS:
                return f"Unknown icon id: {token['id']}"
        elif kind == "word":
            if set(token.keys()) != {"kind", "word"}:
                return "Each word token must have exactly 'kind' and 'word' keys"
            word = token["word"]
            if not isinstance(word, str) or not word.strip():
                return "Each word token's 'word' must be a non-empty string"
            if len(word) > MAX_WORD_LENGTH:
                return f"Word token exceeds {MAX_WORD_LENGTH} characters"
            normalized = word.strip().lower()
            if normalized in seen_words:
                return "Word tokens must be unique"
            seen_words.add(normalized)
            word_count += 1
            if word_count > MAX_EXPAND_WORDS:
                return f"'tokens' must contain at most {MAX_EXPAND_WORDS} word tokens"
        else:
            return f"Unknown token kind: {kind}"

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


MAX_SPEAK_TEXT_LENGTH = 500


def validate_speak_request(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return "Request body must be a JSON object"
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return "'text' is required and must be a non-empty string"
    if len(text) > MAX_SPEAK_TEXT_LENGTH:
        return f"'text' exceeds {MAX_SPEAK_TEXT_LENGTH} characters"
    return None


MAX_PROFILE_FIELD_LENGTH = 100
MAX_INTERESTS_COUNT = 10
MAX_INTEREST_LENGTH = 50


PROFILE_FIELDS = {"vocabLevel", "sentenceLength", "tone", "interests"}


def validate_profile_request(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return "Request body must be a JSON object"
    if set(payload.keys()) != PROFILE_FIELDS:
        # Matches the exact-key-set strictness validate_simplify_response/validate_expand_candidates
        # already use elsewhere -- an accidental/unexpected extra key (e.g. a stray "studentName")
        # must not be stored or echoed back as if it were part of the frozen 4-field contract.
        return f"Request body must contain exactly: {sorted(PROFILE_FIELDS)}"
    for field in ("vocabLevel", "sentenceLength", "tone"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"'{field}' is required and must be a non-empty string"
        if len(value) > MAX_PROFILE_FIELD_LENGTH:
            return f"'{field}' exceeds {MAX_PROFILE_FIELD_LENGTH} characters"
    interests = payload.get("interests")
    if not isinstance(interests, list) or len(interests) == 0:
        return "'interests' is required and must be a non-empty array"
    if len(interests) > MAX_INTERESTS_COUNT:
        return f"'interests' exceeds {MAX_INTERESTS_COUNT} items"
    for interest in interests:
        if not isinstance(interest, str) or not interest.strip():
            return "'interests' must contain only non-empty strings"
        if len(interest) > MAX_INTEREST_LENGTH:
            return f"'interests' item exceeds {MAX_INTEREST_LENGTH} characters"
    return None


MAX_CANDIDATE_TEXT_LENGTH = 200


def validate_expand_candidates(candidates, words=()) -> str | None:
    """Validates model-produced /expand candidates. Returns an error string, or None if valid.

    Deliberately stricter than the base contract shape: rejects duplicate ids/texts, oversized
    text, and unexpected keys, since this is the last line of defense against a schema-constrained
    Bedrock call still returning something we shouldn't show a student. `words` are the conversation
    words the student explicitly selected (in addition to any icons) -- every candidate must
    include each one verbatim (case-insensitive, whole word), so a live response that silently
    drops a word the student chose is treated exactly like malformed output: 1 retry, then fallback.
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
        for word in words:
            if not re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE):
                return f"Candidate 'text' must include the selected word '{word}'"

    return None


MAX_RAW_WINDOW_TURNS = 8
MAX_TURN_TEXT_LENGTH = 500
MAX_SUMMARY_LENGTH = 1000
MAX_ACTIVITY_ANCHOR_LENGTH = 200


def validate_context_request(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return "Request body must be a JSON object"

    summary = payload.get("summary")
    if not isinstance(summary, str):
        return "'summary' is required and must be a string (may be empty)"
    if len(summary) > MAX_SUMMARY_LENGTH:
        return f"'summary' exceeds {MAX_SUMMARY_LENGTH} characters"

    raw_window = payload.get("rawWindow")
    if not isinstance(raw_window, list) or len(raw_window) == 0:
        return "'rawWindow' is required and must be a non-empty array"
    if len(raw_window) > MAX_RAW_WINDOW_TURNS:
        return f"'rawWindow' exceeds {MAX_RAW_WINDOW_TURNS} turns"
    for turn in raw_window:
        if not isinstance(turn, dict) or set(turn.keys()) != {"text", "timestamp"}:
            return "Each 'rawWindow' item must be an object with exactly 'text' and 'timestamp' keys"
        text = turn["text"]
        if not isinstance(text, str) or not text.strip():
            return "Each 'rawWindow' item's 'text' must be a non-empty string"
        if len(text) > MAX_TURN_TEXT_LENGTH:
            return f"'rawWindow' item's 'text' exceeds {MAX_TURN_TEXT_LENGTH} characters"
        if not isinstance(turn["timestamp"], (int, float)) or isinstance(turn["timestamp"], bool):
            return "Each 'rawWindow' item's 'timestamp' must be a number"

    activity_anchor = payload.get("activityAnchor")
    if not isinstance(activity_anchor, str):
        return "'activityAnchor' is required and must be a string (may be empty)"
    if len(activity_anchor) > MAX_ACTIVITY_ANCHOR_LENGTH:
        return f"'activityAnchor' exceeds {MAX_ACTIVITY_ANCHOR_LENGTH} characters"

    return None


MAX_DYNAMIC_ICONS = 6
MAX_WORD_LENGTH = 40
MAX_FLAGGED_LABEL_LENGTH = 200


def validate_context_response(response: dict) -> str | None:
    """Validates the final, already-transformed /context/update response -- flaggedMoment is
    present only when the model actually flagged something (see ../context/schema.py's
    docstring for why the raw tool output carries an explicit `present` boolean instead). Used as
    the runtime "1 retry, then labeled fallback" guard in common/bedrock.py.
    """
    if not isinstance(response, dict):
        return "Response must be a JSON object"

    allowed_keys = {"summary", "dynamicIcons", "flaggedMoment"}
    required_keys = {"summary", "dynamicIcons"}
    if not required_keys.issubset(response.keys()) or not set(response.keys()) <= allowed_keys:
        return "Response must contain 'summary' and 'dynamicIcons', and optionally 'flaggedMoment'"

    if not isinstance(response.get("summary"), str):
        return "'summary' must be a string"

    dynamic_icons = response.get("dynamicIcons")
    if not isinstance(dynamic_icons, list) or len(dynamic_icons) > MAX_DYNAMIC_ICONS:
        return f"'dynamicIcons' must be an array of at most {MAX_DYNAMIC_ICONS} items"
    seen_words = set()
    for item in dynamic_icons:
        if not isinstance(item, dict) or not ({"word"} <= set(item.keys()) <= {"word", "symbol"}):
            return "Each 'dynamicIcons' item must be an object with 'word' and optionally 'symbol'"
        word = item["word"]
        if not isinstance(word, str) or not word.strip():
            return "Each 'dynamicIcons' item's 'word' must be a non-empty string"
        if len(word) > MAX_WORD_LENGTH:
            return f"'dynamicIcons' item's 'word' exceeds {MAX_WORD_LENGTH} characters"
        if "symbol" in item and item["symbol"] not in SYMBOL_IDS:
            return "Each 'dynamicIcons' item's 'symbol' must be a known bank id"
        normalized = word.strip().lower()
        if normalized in seen_words:
            return "'dynamicIcons' words must be unique"
        seen_words.add(normalized)

    if "flaggedMoment" in response:
        flagged = response["flaggedMoment"]
        if not isinstance(flagged, dict) or set(flagged.keys()) != {"label", "icons"}:
            return "'flaggedMoment' must be an object with exactly 'label' and 'icons'"
        label = flagged["label"]
        icons = flagged["icons"]
        if not isinstance(label, str) or not label.strip():
            return "'flaggedMoment.label' must be a non-empty string"
        if len(label) > MAX_FLAGGED_LABEL_LENGTH:
            return f"'flaggedMoment.label' exceeds {MAX_FLAGGED_LABEL_LENGTH} characters"
        if not isinstance(icons, list) or len(icons) == 0:
            return "'flaggedMoment.icons' must be a non-empty array"
        if not all(isinstance(icon, str) and icon in ICON_IDS for icon in icons):
            return "'flaggedMoment.icons' must contain only valid icon IDs"

    return None


def validate_expand_output(payload: object) -> str | None:
    """Validates a payload against EXPAND_OUTPUT_SCHEMA (expand/prompt.py's Bedrock tool-use
    schema) plus candidate-id uniqueness. Used to test that schema/fixtures stay self-consistent;
    the live /expand path's runtime guard is validate_expand_candidates above."""
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


MAX_LABEL_LENGTH = 200


def _validate_icon_labeled_list(items, field_name: str, require_warning_icon: bool = False) -> str | None:
    if not isinstance(items, list):
        return f"'{field_name}' must be an array"
    for item in items:
        if not isinstance(item, dict) or set(item.keys()) != {"icons", "label"}:
            return f"Each '{field_name}' item must be an object with exactly 'icons' and 'label' keys"
        icons = item["icons"]
        label = item["label"]
        if not isinstance(icons, list) or len(icons) == 0:
            return f"Each '{field_name}' item's 'icons' must be a non-empty array"
        if not all(isinstance(icon, str) and icon in ICON_IDS for icon in icons):
            return f"Each '{field_name}' item's 'icons' must contain only valid icon IDs"
        if not isinstance(label, str) or not label.strip():
            return f"Each '{field_name}' item's 'label' must be a non-empty string"
        if len(label) > MAX_LABEL_LENGTH:
            return f"'{field_name}' item's 'label' exceeds {MAX_LABEL_LENGTH} characters"
        if require_warning_icon and not ({"STOP", "CHECK"} & set(icons)):
            return f"Each '{field_name}' item's 'icons' must include STOP and/or CHECK"
    return None


def validate_simplify_response(response: dict) -> str | None:
    """Validates a model-produced /simplify response. Returns an error string, or None if valid.

    Enforces PLAN.md's strict simplification fidelity contract at the code level, not just via the
    prompt: a "please_repeat" response can't smuggle in invented steps, an "ok" response can't be
    a no-op, and a "warning" isn't a warning unless it actually carries a mandatory warning icon.
    """
    if not isinstance(response, dict):
        return "Response must be a JSON object"

    expected_keys = {"status", "steps", "warnings", "quickReplies"}
    if set(response.keys()) != expected_keys:
        return f"Response must contain exactly: {sorted(expected_keys)}"

    status = response.get("status")
    if status not in {"ok", "please_repeat"}:
        return "'status' must be 'ok' or 'please_repeat'"

    steps = response.get("steps")
    error = _validate_icon_labeled_list(steps, "steps")
    if error:
        return error

    warnings = response.get("warnings")
    error = _validate_icon_labeled_list(warnings, "warnings", require_warning_icon=True)
    if error:
        return error

    quick_replies = response.get("quickReplies")
    if not isinstance(quick_replies, list) or len(quick_replies) == 0:
        return "'quickReplies' must be a non-empty array"
    if not all(isinstance(reply, str) and reply in QUICK_REPLY_IDS for reply in quick_replies):
        return "'quickReplies' must contain only valid quick reply IDs"
    if len(set(quick_replies)) != len(quick_replies):
        return "'quickReplies' must not contain duplicates"

    if status == "please_repeat":
        if steps != [] or warnings != [] or quick_replies != ["NEED_HELP"]:
            return "'please_repeat' responses must have empty steps/warnings and quickReplies == ['NEED_HELP']"
    elif not steps and not warnings:
        return "'ok' responses must include at least one step or warning"

    return None
