"""POST /expand — live handler. Calls the pinned Bedrock model for schema-constrained candidates;
falls back to a labeled scripted/deterministic response if the live call can't be trusted (see
../common/bedrock.py). Matches the response contract from PLAN.md's API contract section."""
from ..common.bedrock import invoke_expand
from ..common.responses import ok, bad_request
from ..common.validation import parse_json_body, validate_expand_request


def lambda_handler(event, context):
    payload, error = parse_json_body(event.get("body"))
    if error:
        return bad_request(error)

    error = validate_expand_request(payload)
    if error:
        return bad_request(error)

    get_remaining_ms = context.get_remaining_time_in_millis if context is not None else (lambda: None)
    candidates, source = invoke_expand(payload["icons"], payload["context"], get_remaining_ms)
    return ok({"candidates": candidates}, source=source)
