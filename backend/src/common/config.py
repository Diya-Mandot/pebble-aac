"""Pinned config per PLAN.md's API contract section.

Verified 2026-09-16 against the hackathon AWS account (WSParticipantRole): most Claude models are
blocked by an explicit deny policy (ws-deny-bedrock-models-policy-1) or not opted into for this
event. anthropic.claude-sonnet-4-6 works, but ONLY via its inference profile ID (the "us." prefix)
-- the bare model ID fails with "on-demand throughput isn't supported."

Verified 2026-09-17 against the same hackathon AWS account: Polly's Kevin voice (en-US, male,
"child") is entitled with the neural engine in us-east-1, confirmed via describe_voices and a live
synthesize_speech call, plus scripts/generate_speak_fallback.py's real run (see
backend/fixtures/speak_fallback.json for the generation record). No deny-policy issue here, unlike
Bedrock's model restrictions above.
"""
import os

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

# Verified 2026-09-17 against the hackathon account -- see module docstring above.
POLLY_VOICE_ID = "Kevin"
POLLY_ENGINE = "neural"
POLLY_OUTPUT_FORMAT = "mp3"
POLLY_CONNECT_TIMEOUT_SECONDS = 2
POLLY_READ_TIMEOUT_SECONDS = 8

# GET/POST /profile/{id} -- table name is normally injected by template.yaml's
# Environment.Variables (SAM-generated, since the table name isn't hardcoded); the literal default
# here only matters for local_server.py runs without a real deployed table, where DynamoDB calls
# will fail and every profile lookup falls back to the fixture (see common/dynamo.py).
PROFILE_TABLE_NAME = os.environ.get("PROFILE_TABLE_NAME", "bridge-profiles-local")
PROFILE_TTL_SECONDS = 24 * 60 * 60  # PLAN.md privacy section: "DynamoDB TTL 24h"
DYNAMO_CONNECT_TIMEOUT_SECONDS = 2
DYNAMO_READ_TIMEOUT_SECONDS = 3
