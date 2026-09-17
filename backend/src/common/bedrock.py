"""Bedrock wiring for POST /expand and POST /simplify — schema-constrained tool-use calls to the
pinned model, with a labeled fallback (the scripted fixture when the exact request was scripted,
otherwise a deterministic generic response built only from the selected icon labels) whenever the
live call can't be trusted.

Prompts and tool schemas live in expand/prompt.py and simplify/prompt.py + simplify/schema.py
(Rishabh's Track A/B deliverables per PLAN.md); this module owns the retry/timeout/fallback
plumbing they run through (Ben's integration-owner responsibility per PLAN.md).

PLAN.md: "All model calls use schema-constrained output (Bedrock tool-use)... Lambda validates every
response against the JSON schema; invalid output gets 1 retry, then a labeled fallback." Also:
"Every AWS call has a hard fallback (canned JSON, labeled on screen)."
"""
import json
import sys
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import (
    AWS_REGION,
    BEDROCK_CONNECT_TIMEOUT_SECONDS,
    BEDROCK_MODEL_ID,
    BEDROCK_READ_TIMEOUT_SECONDS,
    MAX_RETRIES,
)
from .validation import validate_expand_candidates, validate_simplify_response
from ..expand.prompt import EXPAND_SYSTEM_PROMPT, EXPAND_TOOL_CONFIG, EXPAND_TOOL_NAME, build_expand_prompt
from ..simplify.prompt import SIMPLIFY_SYSTEM_PROMPT
from ..simplify.schema import SIMPLIFY_TOOL_NAME, SIMPLIFY_TOOL_SCHEMA

PERMANENT_ERROR_CODES = {"AccessDeniedException", "ValidationException", "ResourceNotFoundException"}

# Below this much remaining Lambda time, don't start another attempt — go straight to fallback.
MIN_MS_FOR_ATTEMPT = (BEDROCK_CONNECT_TIMEOUT_SECONDS + BEDROCK_READ_TIMEOUT_SECONDS + 2) * 1000

_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            config=Config(
                connect_timeout=BEDROCK_CONNECT_TIMEOUT_SECONDS,
                read_timeout=BEDROCK_READ_TIMEOUT_SECONDS,
                # total_max_attempts (not max_attempts) is what actually caps this at exactly one
                # attempt with zero SDK-level retries — max_attempts counts retries on TOP of the
                # initial request in standard/adaptive mode, which would let this layer and the
                # application-level retry loop in invoke_expand()/invoke_simplify() multiply
                # against each other.
                retries={"mode": "standard", "total_max_attempts": 1},
            ),
        )
    return _client


def _log_failure(exc, attempt, endpoint="expand"):
    # Only the failure type and attempt number — never icons, context, profileId, text, or model output.
    sys.stderr.write(f"[{endpoint}] Bedrock attempt {attempt} failed: {type(exc).__name__}\n")


def _deterministic_fallback(icons):
    words = ", ".join(icon.replace("_", " ").lower() for icon in icons)
    return [
        {"id": "c1", "text": f"I want to say: {words}."},
        {"id": "c2", "text": f"Can we talk about {words}?"},
        {"id": "c3", "text": f"I'm trying to communicate: {words}."},
    ]


def _extract_candidates(response):
    if response.get("stopReason") != "tool_use":
        raise ValueError(f"Unexpected stopReason: {response.get('stopReason')}")

    content = response.get("output", {}).get("message", {}).get("content", [])
    tool_use_blocks = [block["toolUse"] for block in content if "toolUse" in block]
    if len(tool_use_blocks) != 1:
        raise ValueError(f"Expected exactly one toolUse block, got {len(tool_use_blocks)}")

    tool_use = tool_use_blocks[0]
    if tool_use.get("name") != EXPAND_TOOL_NAME:
        raise ValueError(f"Unexpected tool name: {tool_use.get('name')}")

    return tool_use.get("input", {}).get("candidates")


def _call_once(icons, context, profile):
    prompt = build_expand_prompt(icons, context, profile)
    response = get_client().converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": EXPAND_SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 256, "temperature": 0.2},
        toolConfig=EXPAND_TOOL_CONFIG,
    )
    return _extract_candidates(response)


def invoke_expand(icons, context, profile, fallback_candidates, get_remaining_ms):
    """Returns (candidates, source). source is "live" on a validated Bedrock response, else
    "fallback". fallback_candidates is the caller-resolved scripted response for this exact
    icons/context/profile combination (see expand/app.py), or None if nothing was scripted for
    it — in which case a generic, icon-derived response is used instead so the fallback never
    invents specifics. get_remaining_ms is a zero-arg callable re-checked before each attempt (real
    Lambda context under API Gateway, or a lambda returning None under local_server.py's synthetic
    invocation, which is treated as "assume enough time")."""
    attempts = 1 + MAX_RETRIES
    for attempt in range(1, attempts + 1):
        remaining_ms = get_remaining_ms()
        if remaining_ms is not None and remaining_ms < MIN_MS_FOR_ATTEMPT:
            _log_failure(TimeoutError("insufficient remaining Lambda time"), attempt)
            break

        try:
            candidates = _call_once(icons, context, profile)
        except ClientError as exc:
            _log_failure(exc, attempt)
            if exc.response.get("Error", {}).get("Code") in PERMANENT_ERROR_CODES:
                break
            continue
        except Exception as exc:  # network errors, timeouts, malformed tool output, etc.
            _log_failure(exc, attempt)
            continue

        error = validate_expand_candidates(candidates)
        if error is None:
            return candidates, "live"
        _log_failure(ValueError(error), attempt)

    if fallback_candidates is None:
        fallback_candidates = _deterministic_fallback(icons)
    return fallback_candidates, "fallback"


# --- /simplify -----------------------------------------------------------------------------
# Unlike /expand's ambiguity-by-design, simplification has exactly one correct meaning to
# preserve, so the model produces the entire response shape (not just candidates for a human to
# pick from), and there is no safe generic fallback for arbitrary unmatched text: on failure, we
# always degrade to the same labeled PLEASE_REPEAT shape PLAN.md already prescribes for genuine
# ambiguity, never an invented interpretation of what a real person said.

# Bedrock's Converse API wants toolSpec/inputSchema.json; schema.py's SIMPLIFY_TOOL_SCHEMA is kept
# in the frozen Anthropic-tool shape (name/description/input_schema) since that's the shape the
# Lambda-side validator and the fixtures were written against. Adapt here, at the wiring layer,
# rather than changing the frozen schema shape. additionalProperties is pinned closed here too,
# even though validate_simplify_response independently rejects extra keys — the Lambda validator
# can't just trust Bedrock to have honored it.
SIMPLIFY_TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": SIMPLIFY_TOOL_NAME,
                "description": SIMPLIFY_TOOL_SCHEMA["description"],
                "inputSchema": {
                    "json": {**SIMPLIFY_TOOL_SCHEMA["input_schema"], "additionalProperties": False}
                },
            }
        }
    ],
    "toolChoice": {"tool": {"name": SIMPLIFY_TOOL_NAME}},
}

PLEASE_REPEAT_FALLBACK = {
    "steps": [],
    "warnings": [],
    "quickReplies": ["NEED_HELP"],
    "status": "please_repeat",
}

SIMPLIFY_FIXTURES_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "simplify_fixtures.json"


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _load_simplify_fixtures():
    return json.loads(SIMPLIFY_FIXTURES_PATH.read_text(encoding="utf-8"))


def _scripted_simplify_fallback(text):
    normalized = _normalize(text)
    for fixture in _load_simplify_fixtures():
        if _normalize(fixture["input"]) == normalized:
            return dict(fixture["response"])
    return None


def _extract_simplify_response(response):
    if response.get("stopReason") != "tool_use":
        raise ValueError(f"Unexpected stopReason: {response.get('stopReason')}")

    content = response.get("output", {}).get("message", {}).get("content", [])
    tool_use_blocks = [block["toolUse"] for block in content if "toolUse" in block]
    if len(tool_use_blocks) != 1:
        raise ValueError(f"Expected exactly one toolUse block, got {len(tool_use_blocks)}")

    tool_use = tool_use_blocks[0]
    if tool_use.get("name") != SIMPLIFY_TOOL_NAME:
        raise ValueError(f"Unexpected tool name: {tool_use.get('name')}")

    return tool_use.get("input")


def _call_simplify_once(text):
    response = get_client().converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": SIMPLIFY_SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": text}]}],
        inferenceConfig={"maxTokens": 512, "temperature": 0.1},
        toolConfig=SIMPLIFY_TOOL_CONFIG,
    )
    return _extract_simplify_response(response)


def invoke_simplify(text, get_remaining_ms):
    """Returns (response, source). response is the {status, steps, warnings, quickReplies} shape
    (transcript is set by the caller, never by the model). source is "live" on a validated Bedrock
    response, else "fallback" — either the scripted fixture for an exact-matched demo line, or the
    labeled PLEASE_REPEAT shape for everything else, since inventing steps for unmatched text would
    risk misrepresenting what a real person said."""
    attempts = 1 + MAX_RETRIES
    for attempt in range(1, attempts + 1):
        remaining_ms = get_remaining_ms()
        if remaining_ms is not None and remaining_ms < MIN_MS_FOR_ATTEMPT:
            _log_failure(TimeoutError("insufficient remaining Lambda time"), attempt, "simplify")
            break

        try:
            response = _call_simplify_once(text)
        except ClientError as exc:
            _log_failure(exc, attempt, "simplify")
            if exc.response.get("Error", {}).get("Code") in PERMANENT_ERROR_CODES:
                break
            continue
        except Exception as exc:  # network errors, timeouts, malformed tool output, etc.
            _log_failure(exc, attempt, "simplify")
            continue

        error = validate_simplify_response(response)
        if error is None:
            return response, "live"
        _log_failure(ValueError(error), attempt, "simplify")

    fallback = _scripted_simplify_fallback(text)
    if fallback is None:
        fallback = dict(PLEASE_REPEAT_FALLBACK)
    return fallback, "fallback"
