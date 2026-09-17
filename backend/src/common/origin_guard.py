"""Rejects requests that didn't come through the deployed CloudFront distribution.

API Gateway's default execute-api URL is always publicly invokable regardless of the CloudFront
Basic-auth gate in front of the site, so CloudFront is configured to inject a shared secret header
(X-Pebble-Origin) that only it knows. Local dev (local_server.py) and unit tests never set
ORIGIN_SECRET, so the guard is a no-op there -- it only activates once the Lambda's environment
carries the secret set by template.yaml's ApiOriginSecret parameter.
"""
import hmac
import os


def is_trusted_origin(event: dict) -> bool:
    expected = os.environ.get("ORIGIN_SECRET")
    if not expected:
        return True

    headers = event.get("headers") or {}
    provided = next((v for k, v in headers.items() if k.lower() == "x-pebble-origin"), "")
    return hmac.compare_digest(provided or "", expected)
