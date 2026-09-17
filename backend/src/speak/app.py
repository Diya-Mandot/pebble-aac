"""POST /speak — live handler. Calls the pinned Polly voice for the approved message; falls back
to the one bundled prerecorded clip if the live call can't be trusted and the requested text
matches what that clip actually says, otherwise returns no audio at all rather than substituting
the wrong words (see ../common/polly.py). Matches the response contract from PLAN.md's API
contract section."""
from ..common.polly import invoke_speak
from ..common.responses import ok, bad_request
from ..common.validation import parse_json_body, validate_speak_request


def lambda_handler(event, context):
    payload, error = parse_json_body(event.get("body"))
    if error:
        return bad_request(error)

    error = validate_speak_request(payload)
    if error:
        return bad_request(error)

    text = payload["text"]
    get_remaining_ms = context.get_remaining_time_in_millis if context is not None else (lambda: None)
    audio_base64, source = invoke_speak(text, get_remaining_ms)

    if audio_base64 is None:
        return ok(
            {
                "audioBase64": None,
                "contentType": "audio/mpeg",
                "error": "Voice playback is temporarily unavailable for this message.",
            },
            source=source,
        )
    return ok({"audioBase64": audio_base64, "contentType": "audio/mpeg"}, source=source)
