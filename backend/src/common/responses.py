"""Shared API Gateway response helpers.

Never log request bodies, icons, context text, transcripts, or profile IDs here (PLAN.md privacy
section: "no transcripts/prompts/profiles in logs"). Only method/path/status may be logged.
"""
import json

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
}


def json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def ok(body: dict, source: str = "mock") -> dict:
    return json_response(200, {**body, "source": source})


def bad_request(message: str) -> dict:
    return json_response(400, {"error": message})
