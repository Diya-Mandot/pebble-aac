"""Pinned config per PLAN.md's API contract section.

Verified 2026-09-16 against the hackathon AWS account (WSParticipantRole): most Claude models are
blocked by an explicit deny policy (ws-deny-bedrock-models-policy-1) or not opted into for this
event. anthropic.claude-sonnet-4-6 works, but ONLY via its inference profile ID (the "us." prefix)
-- the bare model ID fails with "on-demand throughput isn't supported."
"""

AWS_REGION = "us-east-1"
BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-6"

# Separate budgets so a Bedrock call can never eat the whole Lambda timeout: LAMBDA_TIMEOUT_SECONDS
# must stay comfortably above BEDROCK_CONNECT_TIMEOUT_SECONDS + BEDROCK_READ_TIMEOUT_SECONDS times
# (1 + MAX_RETRIES) attempts. The Bedrock client itself is configured with zero internal SDK retries
# (total_max_attempts=1) so this application-level MAX_RETRIES is the only retry budget in play.
LAMBDA_TIMEOUT_SECONDS = 25
BEDROCK_CONNECT_TIMEOUT_SECONDS = 2
BEDROCK_READ_TIMEOUT_SECONDS = 8
MAX_RETRIES = 1
