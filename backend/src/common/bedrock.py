"""Shared Bedrock Converse API invocation for the live /expand and /simplify paths.

Both handlers need the same "call the model with a forced tool, validate the tool-use
output against the response schema, 1 retry, then labeled fallback" behavior from
PLAN.md's design rules (PLAN.md:23,43). This module implements that once so app.py
files only supply their prompt/tool/validator.
"""
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from . import config as app_config

_CLIENT = None


def bedrock_configured() -> bool:
    """False while config.py still holds PLAN.md's TODO placeholders (item 5, blocked
    on AWS account access) — callers use this to stay on the fixture-backed mock/
    fallback path without changing the response contract."""
    return not (
        app_config.AWS_REGION.startswith("TODO_")
        or app_config.BEDROCK_MODEL_ID.startswith("TODO_")
    )


def _client():
    global _CLIENT
    if _CLIENT is None:
        import boto3

        _CLIENT = boto3.client(
            "bedrock-runtime",
            region_name=app_config.AWS_REGION,
            config=BotoConfig(
                read_timeout=app_config.TIMEOUT_SECONDS,
                connect_timeout=app_config.TIMEOUT_SECONDS,
                retries={"max_attempts": 0},
            ),
        )
    return _CLIENT


def _extract_tool_input(response: dict):
    try:
        content = response["output"]["message"]["content"]
    except (KeyError, TypeError):
        return None
    for block in content:
        tool_use = block.get("toolUse")
        if tool_use:
            return tool_use.get("input")
    return None


def invoke_tool(system_prompt: str, user_prompt: str, tool_config: dict, validate):
    """Call Bedrock with forced tool use and validate the result.

    `validate` takes the tool-use input dict and returns an error string, or None if
    valid. Retries once (PLAN.md's "1 retry, then labeled fallback") on a transport
    error, a missing tool-use block, or a validation failure.

    Returns (tool_input, None) on success, or (None, error_message) if both attempts
    failed — callers use the error to fall back to a labeled response.
    """
    last_error = "Bedrock call did not run"
    for _ in range(app_config.MAX_RETRIES + 1):
        try:
            response = _client().converse(
                modelId=app_config.BEDROCK_MODEL_ID,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                toolConfig=tool_config,
            )
        except (BotoCoreError, ClientError) as exc:
            last_error = str(exc)
            continue

        tool_input = _extract_tool_input(response)
        if tool_input is None:
            last_error = "Model did not return a tool-use response"
            continue

        error = validate(tool_input)
        if error:
            last_error = error
            continue

        return tool_input, None

    return None, last_error
