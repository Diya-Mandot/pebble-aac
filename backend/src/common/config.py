"""Pinned config per PLAN.md's API contract section.

Verified 2026-09-16 against the hackathon AWS account (WSParticipantRole): most Claude models are
blocked by an explicit deny policy (ws-deny-bedrock-models-policy-1) or not opted into for this
event. anthropic.claude-sonnet-4-6 works, but ONLY via its inference profile ID (the "us." prefix)
-- the bare model ID fails with "on-demand throughput isn't supported."
"""

AWS_REGION = "us-east-1"
BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-6"

TIMEOUT_SECONDS = 10
MAX_RETRIES = 1
