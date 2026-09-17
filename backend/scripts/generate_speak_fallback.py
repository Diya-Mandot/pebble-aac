"""One-off setup script: synthesizes the bundled /speak fallback clip via a real Polly call.

Run manually once, with valid AWS credentials, after Polly voice access is verified against this
account: `python backend/scripts/generate_speak_fallback.py` (works from anywhere -- this script
puts backend/ on sys.path itself before importing src..., so no `-m` invocation or particular cwd
is required). Not part of the deployed Lambda or CI. Regenerate only if the fallback text or
pinned voice changes -- always regenerate both backend/fixtures/speak_fallback.mp3 and
backend/fixtures/speak_fallback.json together so they can't drift out of sync. common/polly.py's
invoke_speak() trusts the .json's "text" field as the single source of truth for what the .mp3
actually says, and verifies the .json's "audioSha256" against the .mp3's actual bytes before ever
treating them as a matched pair -- refusing to play the clip if they've drifted apart (e.g. an
interrupted regeneration or a partial commit left stale files paired together).

If config.POLLY_VOICE_ID/POLLY_ENGINE aren't entitled for this hackathon account, this script will
surface the real ClientError (e.g. AccessDeniedException) from Polly -- update
backend/src/common/config.py with a voice that does work (Ivy, then a standard adult neural voice
like Joanna, are reasonable next tries) and re-run.
"""
import hashlib
import json
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on sys.path

import boto3  # noqa: E402

from src.common import config  # noqa: E402

FALLBACK_TEXT = "I'm confused about building this. Can you help?"

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
AUDIO_PATH = FIXTURES_DIR / "speak_fallback.mp3"
METADATA_PATH = FIXTURES_DIR / "speak_fallback.json"


def _write_through_temp(path, data):
    """Writes to a temp file in the same directory, then atomically renames it onto `path`. So a
    process interrupted partway through (Ctrl-C, crash) never leaves a half-written .mp3 or .json
    behind -- the target file is either the old complete version or the new complete version, never
    a truncated in-between one."""
    binary = isinstance(data, bytes)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "wb" if binary else "w", encoding=None if binary else "utf-8") as f:
            f.write(data)
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def main():
    client = boto3.client("polly", region_name=config.AWS_REGION)
    response = client.synthesize_speech(
        Text=FALLBACK_TEXT,
        OutputFormat=config.POLLY_OUTPUT_FORMAT,
        VoiceId=config.POLLY_VOICE_ID,
        Engine=config.POLLY_ENGINE,
    )
    with closing(response["AudioStream"]) as audio_stream:
        audio_bytes = audio_stream.read()
    if not audio_bytes:
        raise RuntimeError("Polly returned an empty audio stream")

    audio_sha256 = hashlib.sha256(audio_bytes).hexdigest()

    _write_through_temp(AUDIO_PATH, audio_bytes)
    _write_through_temp(
        METADATA_PATH,
        json.dumps(
            {
                "text": FALLBACK_TEXT,
                "voice": config.POLLY_VOICE_ID,
                "engine": config.POLLY_ENGINE,
                "generatedDate": datetime.now(timezone.utc).date().isoformat(),
                "audioSha256": audio_sha256,
            },
            indent=2,
        )
        + "\n",
    )
    print(f"Wrote {AUDIO_PATH} ({len(audio_bytes)} bytes) and {METADATA_PATH}")


if __name__ == "__main__":
    main()
