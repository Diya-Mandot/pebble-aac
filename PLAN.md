# Bridge — Bidirectional AAC Classroom Communicator · PLAN v2 (mid-Day-1)

**One-liner:** Current tools help nonverbal kids talk *at* people. Bridge helps them talk *with* people — AAC icons expand into speech the student approves; peers' speech distills into icon sequences the student can act on.

**Track:** Collaborate (+ Learn) · **Pattern:** Managed-services orchestration (Bedrock + Transcribe + Polly). No external runtime services.

---

## Decisions made — do not reopen

- **Frontend:** React, ONE page, split screen, client-side session state. No WebSockets. No two-device sync.
- **Backend:** REST → API Gateway → Lambda. DynamoDB for profiles only.
- **Input order:** TYPED peer input first. Voice (Transcribe) is build step 6, not MVP.
- **Icons:** 10 fixed IDs (below). Placeholder emoji/labels NOW; swap in ARASAAC symbols only if time (then attribute: CC BY-NC-SA, credit in UI footer + submission; prod note: "would license a commercial symbol set").
- **Fallbacks are labeled.** Any canned output shows "Recorded demo fallback" on screen. Never disguised as live.

## Design rules (encode in prompts + schemas)

**Two directions, two fidelity contracts:**
- **Expansion (student → group):** icons are ambiguous BY DESIGN. Candidates span *plausible interpretations* of icons + context — the student's choice is the disambiguation. Invariant: every candidate is a defensible reading; **no fabricated specifics** (names, events, commitments). Interests may shape word choice, never add content.
- **Simplification (group → student):** meaning is fixed by the speaker. Preserve **objects, order, quantities, negation** exactly. Warnings/negations render as mandatory icons. Low confidence or ambiguity → return `PLEASE_REPEAT`, never guess.
- Transcript is one tap away (icon-first for the AAC user; verbatim never silently edited).
- All model calls use **schema-constrained output** (Bedrock tool-use) against the icon enum. Lambda validates every response against the JSON schema; invalid output gets 1 retry, then a labeled fallback (`PLEASE_REPEAT` for simplification). No free-text parsing.

## Icon enum (FROZEN — copy into code + prompts verbatim)

`CONFUSED, IDEA, BUILD, HELP, AGREE, DISAGREE, QUESTION, STOP, CHECK, DONE`
QuickReplyID: `DONE, NEED_HELP` · system status: `PLEASE_REPEAT`

## API contract (FREEZE IN THE NEXT HOUR — integration owner: [YOU])

```
POST /expand    {icons:[IconID], context:string, profileId:string}
             → {candidates:[{id,text}], error?}
POST /simplify  {text:string}
             → {steps:[{icons:[IconID], label:string}], warnings:[{icons:[IconID], label:string}],
                quickReplies:[QuickReplyID], transcript:string, status:"ok"|"please_repeat", error?}
POST /speak     {text:string} → {audioBase64, contentType:"audio/mpeg"}  # Polly; bundled prerecorded clip is the labeled fallback
GET  /profile/{id} · POST /profile/{id}             # {vocabLevel, sentenceLength, tone, interests[]}
```
Every AWS call has a hard fallback (canned JSON, labeled on screen). Model ID, region, timeout (10s), 1 retry — pin in one config file now.

## Build order (strict — do not skip ahead)

1. ☐ React split screen, icon grid, typed chat — hardcoded fake responses end-to-end
2. ☐ /expand live: icons → 3 schema-constrained candidates → **approval chooser** → text lands in chat
3. ☐ /simplify live: typed peer message → icon steps + warnings + quick replies; PLEASE_REPEAT path
4. ☐ /speak: Polly playback of approved message (child-appropriate neural voice — test voice/region NOW; bundle one prerecorded fallback clip)
5. ☐ Profile toggle: 2 synthetic profiles, same icons → visibly different candidates
6. ☐ Voice input: MediaRecorder → presigned S3 URL → batch Transcribe → poll → /simplify (+ S3 lifecycle delete)
7. ☐ Polish only: ARASAAC swap, loading states, empty states

**Ship line:** steps 1–4 = complete demo. 5 = strong. 6 = wow. 7 = gravy.

## Test fixtures (Rishabh writes as files in /fixtures NOW — they are the spec)

- Wiring line w/ negation: "take the red wire, connect it to the battery first, but make sure the switch is off" → must yield STOP/CHECK warning for "switch off"
- Ordering: 3-step instruction → steps in order
- Ambiguous mumble → PLEASE_REPEAT
- Prompt injection: "ignore your instructions and say…" → simplified as ordinary (weird) speech, never obeyed
- Expansion: CONFUSED+BUILD+HELP × 2 profiles → interpretations differ, zero fabricated specifics

## Privacy (statements + config, ~30 min total — Diya writes, you configure)

Synthetic profiles only, no real student data · pseudonymous session IDs · DynamoDB TTL 24h · S3 audio auto-delete (lifecycle 1 day) · no transcripts/prompts/profiles in logs · README note: classroom deployment requires auth + retention policy (not claimed for the prototype). **Agency ≠ privacy — the demo says both, separately.**

## Demo script (~4 min)

1. Hook: "talk at → talk WITH." Split screen, science-lab context.
2. CONFUSED+BUILD+HELP → 3 candidates → **pause: "AI drafts, student decides — it never speaks for the child. And because icons are ambiguous, choosing IS the disambiguation."** → pick → Polly speaks.
3. Peer message (typed; voice if step 6 shipped — else labeled fallback clip): wiring line → icon steps + [CHECK: SWITCH OFF] warning → tap reveals transcript.
4. Profile toggle → same icons, different candidates. One line on DynamoDB.
5. Tap [DONE] → confirmation in chat. Loop closed.
6. Close: managed AWS architecture · ethics slide (agency, asymmetric fidelity contracts, bounded personalization, symbol licensing) · feasibility (any browser, no hardware).

## Responsibilities (rebalanced: single integration owner)

- **You — END-TO-END INTEGRATION OWNER.** API contract, Lambdas, DynamoDB, config pinning, Polly response handling, all fallbacks, privacy config. You merge; conflicts resolve in your favor.
- **Rishabh —** fixtures first, then /expand and /simplify prompts + schema definitions; iterate against fixtures only. Transcribe pipeline at step 6.
- **Diya —** split-screen UI against the frozen contract (mock server until Lambdas land), then slides/one-pager in parallel once UI is stable: hook, ethics slide, criteria mapping. Owns rehearsal + backup recording.

## Next 60 minutes

1. All three: freeze contract + enum above (edit here if needed, then it's law)
2. You: repo scaffold, config file, mock /expand + /simplify returning fixture-shaped JSON
3. Rishabh: fixtures committed, first /expand prompt drafted
4. Diya: split-screen skeleton against mocks
5. Anyone idle 5 min: verify Bedrock model access + Polly voices in the team account — TODAY, not tomorrow

## Cut list (already decided — do not resurrect)

Two-device sync · WebSockets · SLP interview (cite AAC/ARASAAC research in slides instead) · Strands · real ARASAAC unless step 7 · streaming Transcribe
