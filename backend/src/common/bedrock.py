"""Bedrock wiring for POST /expand — schema-constrained tool-use calls to the pinned model, with a
labeled fallback (the scripted fixture when the exact request was scripted, otherwise a deterministic
generic response built only from the selected icon labels) whenever the live call can't be trusted.

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
from .validation import validate_expand_candidates

FIXTURES_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "expand_default.json"

TOOL_NAME = "provide_candidates"

EXPAND_TOOL_SPEC = {
    "toolSpec": {
        "name": TOOL_NAME,
        "description": (
            "Provide exactly 3 distinct, plausible spoken-language sentences the AAC student might "
            "mean by the selected icons. Never invent specific names, events, times, or commitments "
            "that aren't implied by the icons or context."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "candidates": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["id", "text"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["candidates"],
                "additionalProperties": False,
            }
        },
    }
}

# TODO(Rishabh): swap for the real drafted /expand prompt once ready. Isolated to this one constant
# so that swap never touches the retry/timeout/fallback plumbing below.
SYSTEM_PROMPT = (
    "You help a nonverbal AAC student speak. The student selected some icons (and maybe typed a "
    "short context note). Icons are ambiguous by design: propose exactly 3 short, distinct, "
    "first-person spoken-language sentences that are all plausible readings of the icons. Never add "
    "specific names, events, times, numbers, or commitments that the icons/context don't already "
    "imply. Respond only by calling the provided tool."
)

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
                # application-level retry loop in invoke_expand() multiply against each other.
                retries={"mode": "standard", "total_max_attempts": 1},
            ),
        )
    return _client


def _build_user_message(icons, context):
    lines = [f"Selected icons: {', '.join(icons)}."]
    if context:
        lines.append(f"Typed context: {context}")
    return {"role": "user", "content": [{"text": " ".join(lines)}]}


def _extract_candidates(response):
    if response.get("stopReason") != "tool_use":
        raise ValueError(f"Unexpected stopReason: {response.get('stopReason')}")

    content = response.get("output", {}).get("message", {}).get("content", [])
    tool_use_blocks = [block["toolUse"] for block in content if "toolUse" in block]
    if len(tool_use_blocks) != 1:
        raise ValueError(f"Expected exactly one toolUse block, got {len(tool_use_blocks)}")

    tool_use = tool_use_blocks[0]
    if tool_use.get("name") != TOOL_NAME:
        raise ValueError(f"Unexpected tool name: {tool_use.get('name')}")

    return tool_use.get("input", {}).get("candidates")


def _call_once(icons, context):
    response = get_client().converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[_build_user_message(icons, context)],
        inferenceConfig={"maxTokens": 256, "temperature": 0.2},
        toolConfig={
            "tools": [EXPAND_TOOL_SPEC],
            "toolChoice": {"tool": {"name": TOOL_NAME}},
        },
    )
    return _extract_candidates(response)


def _log_failure(exc, attempt):
    # Only the failure type and attempt number — never icons, context, profileId, or model output.
    sys.stderr.write(f"[expand] Bedrock attempt {attempt} failed: {type(exc).__name__}\n")


def _load_fixtures():
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def _scripted_fallback(icons, context):
    for fixture in _load_fixtures():
        if fixture["icons"] == icons and fixture["context"] == context:
            return fixture["response"]["candidates"]
    return None


def _deterministic_fallback(icons):
    words = ", ".join(icon.replace("_", " ").lower() for icon in icons)
    return [
        {"id": "c1", "text": f"I want to say: {words}."},
        {"id": "c2", "text": f"Can we talk about {words}?"},
        {"id": "c3", "text": f"I'm trying to communicate: {words}."},
    ]


def invoke_expand(icons, context, get_remaining_ms):
    """Returns (candidates, source). source is "live" on a validated Bedrock response, else
    "fallback". get_remaining_ms is a zero-arg callable re-checked before each attempt (real Lambda
    context under API Gateway, or a lambda returning None under local_server.py's synthetic
    invocation, which is treated as "assume enough time")."""
    attempts = 1 + MAX_RETRIES
    for attempt in range(1, attempts + 1):
        remaining_ms = get_remaining_ms()
        if remaining_ms is not None and remaining_ms < MIN_MS_FOR_ATTEMPT:
            _log_failure(TimeoutError("insufficient remaining Lambda time"), attempt)
            break

        try:
            candidates = _call_once(icons, context)
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

    fallback = _scripted_fallback(icons, context)
    if fallback is None:
        fallback = _deterministic_fallback(icons)
    return fallback, "fallback"
