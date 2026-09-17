"""DynamoDB wiring for GET/POST /profile/{id}. Every call has a hard fallback to the matching
synthetic profile already shipped in fixtures/expand_default.json, consistent with PLAN.md's "every
AWS call has a hard fallback" rule -- unlike Bedrock/Polly's fallback being canned *content*, here
the fallback is the same synthetic default profile data, just not persisted.

Single attempt by design (no application-level retry loop like bedrock.py/polly.py have):
get_item/put_item are cheap, low-latency, high-reliability calls, not generative/TTS calls where a
retry has real value. The pinned Config below (not just this docstring) is what actually enforces
"single attempt".
"""
import time
from decimal import Decimal
from pathlib import Path
import json

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import (
    AWS_REGION,
    DYNAMO_CONNECT_TIMEOUT_SECONDS,
    DYNAMO_READ_TIMEOUT_SECONDS,
    PROFILE_TABLE_NAME,
    PROFILE_TTL_SECONDS,
)
from .validation import validate_profile_request

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "expand_default.json"

_resource = None


def get_table():
    global _resource
    if _resource is None:
        _resource = boto3.resource(
            "dynamodb",
            region_name=AWS_REGION,
            config=Config(
                connect_timeout=DYNAMO_CONNECT_TIMEOUT_SECONDS,
                read_timeout=DYNAMO_READ_TIMEOUT_SECONDS,
                retries={"mode": "standard", "total_max_attempts": 1},
            ),
        )
    return _resource.Table(PROFILE_TABLE_NAME)


def _fixture_profile(profile_id):
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    profile = fixture["profiles"].get(profile_id)
    return profile["profile"] if profile else None


def _extract_traits(item):
    """Raises ValueError on anything that doesn't match the frozen {vocabLevel, sentenceLength,
    tone, interests} shape -- a legacy or manually-edited item is untrusted input same as any other
    on-disk/stored data in this codebase (same spirit as polly.py's _load_fallback() hardening), so
    a malformed record must degrade to the fixture fallback, never crash the Lambda, and never be
    trusted just because it's the right shape of dict.

    Reuses validate_profile_request (the same validator POST /profile/{id} runs against a new
    submission) rather than a separate, weaker set of checks -- a read must not be less strict than
    a write, otherwise a whitespace-only field, an empty interests list, or an oversized value that
    a POST would reject can still slip through here as a trusted "live" profile and reach the
    Bedrock prompt unvalidated."""
    traits = {
        "vocabLevel": item.get("vocabLevel"),
        "sentenceLength": item.get("sentenceLength"),
        "tone": item.get("tone"),
        "interests": item.get("interests"),
    }
    error = validate_profile_request(traits)
    if error is not None:
        raise ValueError(error)
    return traits


def get_profile(profile_id):
    """Returns (profile_dict_or_None, source). profile_dict is always exactly the frozen
    {vocabLevel, sentenceLength, tone, interests} shape -- never the raw DynamoDB item, which would
    (a) leak profileId/expiresAt outside the contract and (b) fail json.dumps on expiresAt's
    Decimal type. source is "live" for a real saved item, "fallback" for the fixture default (or
    profile_dict is None if profile_id matches neither known fixture profile either)."""
    try:
        response = get_table().get_item(Key={"profileId": profile_id}, ConsistentRead=True)
        item = response.get("Item")
        if item is not None:
            expires_at = item.get("expiresAt")
            # DynamoDB's TTL deletion is a background sweep that can lag well past the timestamp,
            # so a still-present-but-expired item must not be trusted just because get_item
            # returned it.
            if isinstance(expires_at, (int, Decimal)) and expires_at > int(time.time()):
                return _extract_traits(item), "live"
    except (ClientError, BotoCoreError, KeyError, TypeError, ValueError):
        # ClientError: AWS-side API errors. BotoCoreError: client-side failures (missing
        # credentials, connection issues) that never reach AWS at all. KeyError/TypeError/ValueError
        # from _extract_traits: a malformed stored item, not an AWS exception, but must not crash
        # past this function either.
        pass
    return _fixture_profile(profile_id), "fallback"


def put_profile(profile_id, profile):
    """Returns True on success, False on any failure -- never claim a save succeeded when it didn't."""
    try:
        get_table().put_item(
            Item={
                "profileId": profile_id,
                "vocabLevel": profile["vocabLevel"],
                "sentenceLength": profile["sentenceLength"],
                "tone": profile["tone"],
                "interests": profile["interests"],
                "expiresAt": int(time.time()) + PROFILE_TTL_SECONDS,
            }
        )
        return True
    except (ClientError, BotoCoreError):
        return False
