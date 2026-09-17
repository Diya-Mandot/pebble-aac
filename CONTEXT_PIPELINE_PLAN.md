# Ambient Context Pipeline — Implementation Plan

Follow-on to PLAN.md's pivot away from the chat metaphor (see README/PLAN.md demo flow, which this
plan does **not** change — /expand, /simplify, /speak stay as-is). This covers the new pieces only:
continuous in-room listening feeding (a) a dynamic row of context-relevant icons on the student's
board and (b) rare, human-triggered "help understand" moments — never an unprompted, continuously
translated peer-speech stream. See design rules below; do not reopen these without flagging the group.

## Design rules (do not reopen mid-build)

- **Fixed icons never move.** The existing 10 icons in `ICONS` ([src/App.tsx](src/App.tsx)) keep
  their positions permanently. A new dynamic row gets its own fixed set of slots (~6) whose *labels*
  change, never their *position* or count.
- **Updates are rare and topic-driven**, not per-utterance. Debounced, not real-time.
- **Receptive help is human-triggered, not auto-surfaced.** Continuous listening feeds context for
  the student's *own* expression (low risk, self-correcting — nothing reaches the group until they
  approve it). It does not auto-push translated peer speech at the student.
- **Never guess.** Same principle as PLEASE_REPEAT in the existing simplify contract — an ambiguous
  "is this addressed to the student" or "is this a safety warning" call defaults to *not surfacing*.

---

## Track A — Continuous voice capture (frontend, independent)

Owner: TBD · No dependencies, can start immediately.

- [ ] Convert `toggleVoiceInput`/`recognitionRef` in [src/App.tsx](src/App.tsx) from push-to-talk to
      session-scoped continuous mode (`recognition.continuous = true`).
- [ ] Handle the browser's periodic forced `onend` (Web Speech API drops ~every 60s) by
      auto-restarting recognition transparently.
- [ ] Emit a structured `Turn` object (`{text, timestamp}`) on each `isFinal` result — this is the
      interface Track B consumes. Publish it via a simple callback/event so Track B can be built
      against a stub emitter without waiting on this track.
- [ ] Add the on-screen "listening" indicator (start/stop control, visible state) — this is the
      transparency affordance, not optional polish.

## Track B — Conversation buffer + context formalization (frontend, mostly independent)

Owner: TBD · Can start in parallel with Track A against a **stub turn emitter** (a fake generator
pushing sample `Turn` objects on a timer) — swap in Track A's real emitter once it lands.

- [ ] New module `src/conversationBuffer.ts`: ring buffer of last ~6-8 raw `Turn`s.
- [ ] Rolling summary string that absorbs turns as they age out of the raw window (only
      regenerated when the window actually rolls over, not every turn).
- [ ] Debounce/trigger logic for Track E's backend call: turn boundary **and** a cheap local
      keyword-diff against the current summary **and** a minimum time gap (~20-30s) since the last
      refresh. This is the token-efficiency mechanism — most turns cost nothing.
- [ ] Compose the bounded context payload: `summary + raw window + activity anchor (existing
      `context` dropdown) + student's last approved message`.

## Track C — Dynamic icon row UI (frontend, independent)

Owner: TBD · Can start immediately against **fake dynamic-icon data** (hardcoded array), no
dependency on A/B/D until final wiring.

- [ ] Add the fixed ~6-slot row to the board layout in [src/App.tsx](src/App.tsx)/
      [src/styles.css](src/styles.css), visually distinct from the permanent 10-icon set.
- [ ] Render dynamic slots as generic tile shape + word label (no ARASAAC dependency — that's
      separate polish work already tracked elsewhere).
- [ ] Subtle highlight/pulse animation on newly-added tiles only (not a full-row flash).
- [ ] Wire slot content to whatever prop shape Track E ends up passing — keep this a dumb
      presentational component so the data source is swappable.
- [ ] Separately: add the human-triggered "help [name] understand" affordance (button, not
      automatic) that surfaces a `flaggedMoment` when present — reuses existing `/simplify`-style
      rendering (icons + label), just a new trigger path.

## Track D — Backend context endpoint (backend, independent)

Owner: TBD · Can start immediately against a fixture-style request body, no dependency on any
frontend track.

- [ ] New handler, e.g. `backend/src/context/app.py`, `POST /context/update`, taking
      `{summary, rawWindow, activityAnchor}` (mirrors the bounded payload Track B produces).
- [ ] Returns `{summary, dynamicIcons: [{word}], flaggedMoment?: {label, icons}}` — one combined
      call, not three, to keep token cost down.
- [ ] Prompt/schema for `dynamicIcons`: extract concrete nouns/verbs actually present in the raw
      window — same "no fabricated specifics" discipline as the existing `/expand` contract
      (PLAN.md:20).
- [ ] Prompt/schema for `flaggedMoment`: fires only for (a) safety/warning content or (b) a direct
      question addressed to the student (name mention, or unnamed direct question with no other
      addressee) — high-confidence only, default to omitting the field when ambiguous.
- [ ] Fixtures first (mirrors [backend/fixtures/](backend/fixtures/) convention): a wiring-safety
      transcript, a name-addressed question, an ordinary aside that should produce neither.
- [ ] Add fallback path consistent with the rest of the API (`source: "fallback"` on live failure),
      same pattern as [src/api.ts](src/api.ts)'s existing fallbacks.

## Track E — Integration (depends on A + B + C + D)

Owner: TBD · Do not start until the above land — this is where shapes have to actually match.

- [ ] Replace Track C's fake data and Track B's stub emitter with the real Track A emitter and
      Track D endpoint.
- [ ] Confirm the debounce logic in Track B actually bounds call frequency in a live multi-minute
      test conversation (not just unit-level).
- [ ] End-to-end fixture replay: feed a scripted multi-turn transcript through the whole pipeline,
      confirm dynamic row updates land at topic shifts (not per-turn) and `flaggedMoment` only
      appears for the safety/addressed-question cases.
- [ ] Update [README.md](README.md)'s demo flow to include the new board behavior.

---

## Suggested order

1. **Now, in parallel:** Track A, Track C, and Track D have no dependencies on each other or on
   anyone else — start all three immediately.
2. **Also now, in parallel:** Track B, against a stub emitter — don't wait on Track A to finish.
3. **After A + B + C + D:** Track E integration — this is the only serial step, and it's mostly
   glue + a live test pass, not new design work.

## Open decision, not yet made

Which persona this targets (expressive-only vs. combined expressive+receptive difficulty) affects
how prominently the "help understand" trigger is surfaced in the UI and how it's framed on the
ethics slide. Flag before Track C's help-affordance work goes final.
