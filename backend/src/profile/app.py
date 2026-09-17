"""GET/POST /profile/{id} -- DynamoDB profile store with a hard fallback to the synthetic demo
profiles (see ../common/dynamo.py). Matches PLAN.md's frozen API contract:
{vocabLevel, sentenceLength, tone, interests[]}."""
from ..common.dynamo import get_profile, put_profile
from ..common.origin_guard import is_trusted_origin
from ..common.responses import ok, bad_request, forbidden, not_found, server_error
from ..common.validation import parse_json_body, validate_profile_request


def lambda_handler(event, context):
    if not is_trusted_origin(event):
        return forbidden()

    profile_id = (event.get("pathParameters") or {}).get("id")
    if not profile_id:
        return bad_request("Missing profile id in path")

    method = event.get("httpMethod")

    if method == "GET":
        profile, source = get_profile(profile_id)
        if profile is None:
            return not_found(f"No profile found for id '{profile_id}'")
        return ok(profile, source=source)

    if method == "POST":
        payload, error = parse_json_body(event.get("body"))
        if error:
            return bad_request(error)
        error = validate_profile_request(payload)
        if error:
            return bad_request(error)
        # Canonical 4-field object, not the raw payload -- validate_profile_request now rejects
        # unexpected extra keys too, but constructing this explicitly is defense in depth so
        # neither the DynamoDB write nor the HTTP response can ever carry anything outside the
        # frozen {vocabLevel, sentenceLength, tone, interests} contract.
        profile = {
            "vocabLevel": payload["vocabLevel"],
            "sentenceLength": payload["sentenceLength"],
            "tone": payload["tone"],
            "interests": list(payload["interests"]),
        }
        if not put_profile(profile_id, profile):
            return server_error("Could not save the profile right now.")
        return ok(profile, source="live")

    return bad_request(f"Unsupported method: {method}")
