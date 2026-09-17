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

## Deploy a public demo (AWS)

`deploy.ps1` stands up the whole app in the Workshop Studio hackathon account: backend Lambdas +
API Gateway (`backend/template.yaml`), plus the built frontend behind a CloudFront distribution
gated with HTTP Basic Auth. No Docker or SAM CLI required -- it vendors Linux Lambda dependencies
with `pip`'s cross-platform flags and deploys with the AWS CLI directly.

Prereqs: AWS CLI v2, Node, Python, and fresh Workshop Studio credentials in `backend/.env` (copy
`backend/.env.example`; these are short-lived and expire every few hours -- re-copy from the event
portal's "AWS Console"/"CLI" panel when `deploy.ps1` reports `ExpiredToken`).

```powershell
.\deploy.ps1 -SitePassword pebblehackathon
```

Re-run the same command to redeploy after code changes. The printed `SiteUrl` is the public URL;
sign in with username `pebble` and the password you passed. The raw API Gateway URL is not
protected by the Basic-auth prompt, so the Lambdas separately reject any request that doesn't carry
the shared secret header CloudFront injects (`common/origin_guard.py`) -- fine for a demo, not a
substitute for real auth in a classroom deployment.

## Demo flow

1. On **Maya's voice**, select **Confused**, **Build**, and **Help**.
2. Choose **Create my message**, review the three interpretations, and approve one.
3. On **Science team**, send: `take the red wire, connect it to the battery first, but make sure the switch is off`.
4. Return to the student side to see the ordered steps, prominent safety check, transcript, and quick replies.
