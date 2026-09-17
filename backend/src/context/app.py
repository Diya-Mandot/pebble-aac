"""POST /context/update -- live handler for the ambient context pipeline (CONTEXT_PIPELINE_PLAN.md
Track D). Calls the pinned Bedrock model for a schema-constrained rolling-summary update, dynamic
icon extraction, and rare flagged-moment detection; falls back to a scripted fixture or a
deterministic, transcript-derived response if the live call can't be trusted (see
../common/bedrock.py). Independent of any frontend track -- exercised here against a
fixture-style request body: {summary, rawWindow, activityAnchor}."""
from ..common.bedrock import invoke_context
from ..common.responses import ok, bad_request
from ..common.validation import parse_json_body, validate_context_request


def lambda_handler(event, context):
    payload, error = parse_json_body(event.get("body"))
    if error:
        return bad_request(error)

    error = validate_context_request(payload)
    if error:
        return bad_request(error)

    get_remaining_ms = context.get_remaining_time_in_millis if context is not None else (lambda: None)
    response, source = invoke_context(
        payload["summary"], payload["rawWindow"], payload["activityAnchor"], get_remaining_ms
    )
    return ok(response, source=source)
