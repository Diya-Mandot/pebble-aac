"""POST /simplify — live handler. Calls the pinned Bedrock model for a schema-constrained
simplification; falls back to a labeled scripted/PLEASE_REPEAT response if the live call can't be
trusted (see ../common/bedrock.py). Matches the response contract from PLAN.md's API contract
section."""
from ..common.bedrock import invoke_simplify
from ..common.origin_guard import is_trusted_origin
from ..common.responses import ok, bad_request, forbidden
from ..common.validation import parse_json_body, validate_simplify_request


def lambda_handler(event, context):
    if not is_trusted_origin(event):
        return forbidden()

    payload, error = parse_json_body(event.get("body"))
    if error:
        return bad_request(error)

    error = validate_simplify_request(payload)
    if error:
        return bad_request(error)

    text = payload["text"]
    get_remaining_ms = context.get_remaining_time_in_millis if context is not None else (lambda: None)
    response, source = invoke_simplify(text, get_remaining_ms)

    response = dict(response)
    response["transcript"] = text  # verbatim, always -- never model-produced
    return ok(response, source=source)
