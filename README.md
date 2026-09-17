# Pebble AAC

Pebble is an AI-powered, bidirectional communication bridge connecting AAC users with their peers during classroom group work.

## Run the demo

Start the backend in one terminal:

```bash
python3 -m pip install -r backend/requirements.txt
cd backend
python3 local_server.py
```

Start the React frontend in another terminal:

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend uses `http://127.0.0.1:8000` by default. Set `VITE_API_BASE_URL` to use a deployed API Gateway URL.

If the backend cannot be reached, Pebble visibly switches to a labeled recorded-demo fallback so the hackathon walkthrough remains reliable and honest.

## Demo flow

1. On **Maya's voice**, select **Confused**, **Build**, and **Help**.
2. Choose **Create my message**, review the three interpretations, and approve one.
3. On **Science team**, send: `take the red wire, connect it to the battery first, but make sure the switch is off`.
4. Return to the student side to see the ordered steps, prominent safety check, transcript, and quick replies.

## Ambient context pipeline

Click the mic button to start session-scoped listening (see `CONTEXT_PIPELINE_PLAN.md`). While
listening, the app quietly builds a rolling conversation summary in the background and, at real
topic shifts (not every utterance), calls the backend to refresh the **Words from the
conversation** row under the board with a few concrete words actually said. This never happens
per-utterance -- it's debounced by a minimum time gap and a local keyword-diff, so most turns cost
nothing.

The **Help Maya understand** button is a separate, human-triggered affordance: it surfaces a
flagged moment (a safety warning or a question addressed to Maya) only when one was actually
detected, and only when Maya's teacher/aide chooses to look -- receptive help is never
auto-surfaced onto the board.
