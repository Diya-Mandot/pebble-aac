import type {
  Candidate,
  ContextUpdateRequest,
  ContextUpdateResponse,
  ExpandResponse,
  IconId,
  SentenceToken,
  SimplifyResponse,
  SpeakResponse,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

// Small local label map, not imported from App.tsx's ICONS/iconById -- App.tsx already imports
// expandMessage etc. from this module, so pulling iconById back in the other direction would be
// an import cycle. Kept minimal (labels only, no lucide icon components).
const ICON_LABELS: Record<IconId, string> = {
  CONFUSED: 'confused', IDEA: 'i have an idea', BUILD: 'build', HELP: 'help', AGREE: 'i agree',
  DISAGREE: 'i disagree', QUESTION: 'question', STOP: 'stop', CHECK: 'check', DONE: "i'm done",
}

// Matches backend/fixtures/expand_default.json's scripted "request" -- only that exact icon
// sequence + context is safe to answer with the canned demo strings below (mirrors expand/app.py's
// _scripted_fallback_candidates, which does the same exact-order comparison on the backend).
const SCRIPTED_ICONS: IconId[] = ['CONFUSED', 'BUILD', 'HELP']
const SCRIPTED_CONTEXT = 'classroom group project'

// Mirrors expand_default.json's two profiles' canned candidates, so this fully-offline fallback
// (only reached when fetch itself throws, e.g. the backend is unreachable) still shows visibly
// different text per profile, same as the backend's own no-AWS-creds fallback already does.
const scriptedFallbackByProfile: Record<string, Candidate[]> = {
  demo: [
    { id: 'c1', text: "I'm confused about building this. Can you help?" },
    { id: 'c2', text: "I don't understand this part. Please help me build it." },
    { id: 'c3', text: 'How do I build this? I need help.' },
  ],
  demo_alt: [
    { id: 'c1', text: "I'm not sure how to build this. Could we work through it together?" },
    { id: 'c2', text: 'This build is confusing me. Can someone explain how to approach it?' },
    { id: 'c3', text: 'I need some help understanding how this goes together.' },
  ],
}

// Walks tokens in order (icon -> its label, word -> itself) so the offline fallback text
// preserves the sequence the student actually built, matching the backend's own fallback shape
// (see backend/src/common/bedrock.py's _deterministic_fallback).
const genericFallback = (tokens: SentenceToken[]): Candidate[] => {
  const words = tokens.map((token) => (token.kind === 'icon' ? ICON_LABELS[token.id] : token.word)).join(', ')
  return [
    { id: 'c1', text: `I want to say: ${words}.` },
    { id: 'c2', text: `Can we talk about ${words}?` },
    { id: 'c3', text: `I'm trying to communicate: ${words}.` },
  ]
}

const simplifyFallback = (text: string): SimplifyResponse => {
  const isWiringDemo = /red wire|battery|switch/i.test(text)
  if (isWiringDemo) {
    return {
      steps: [
        { icons: ['IDEA', 'BUILD'], label: 'Take the red wire' },
        { icons: ['BUILD'], label: 'Connect it to the battery first' },
      ],
      warnings: [{ icons: ['STOP', 'CHECK'], label: 'Make sure the switch is off' }],
      quickReplies: ['DONE', 'NEED_HELP'],
      transcript: text,
      status: 'ok',
      source: 'fallback',
      error: 'The live service is unavailable. Showing the recorded demo fallback.',
    }
  }

  return {
    steps: [],
    warnings: [],
    quickReplies: ['NEED_HELP'],
    transcript: text,
    status: 'please_repeat',
    source: 'fallback',
    error: 'The live service is unavailable. Ask the speaker to repeat the message.',
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Something went wrong.' }))
    throw new Error(error.error || `Request failed (${response.status})`)
  }

  return response.json() as Promise<T>
}

export async function expandMessage(
  tokens: SentenceToken[],
  context: string,
  profileId: string,
): Promise<ExpandResponse> {
  // symbol is presentation-only; the backend token shape has no such field.
  const wireTokens = tokens.map((token) =>
    token.kind === 'icon' ? { kind: 'icon' as const, id: token.id } : { kind: 'word' as const, word: token.word },
  )
  try {
    return await post<ExpandResponse>('/expand', { tokens: wireTokens, context, profileId })
  } catch {
    // Exact order, not membership -- mirrors expand/app.py's _scripted_fallback_candidates
    // (every token must be an icon matching SCRIPTED_ICONS in order), so a reordered selection
    // like HELP+BUILD+CONFUSED, or any selection including a word token, correctly falls through
    // to the generic fallback instead of matching the scripted CONFUSED+BUILD+HELP demo response
    // it wasn't recorded for.
    const isScripted = context === SCRIPTED_CONTEXT
      && tokens.length === SCRIPTED_ICONS.length
      && tokens.every((token, index) => token.kind === 'icon' && token.id === SCRIPTED_ICONS[index])
    const candidates = isScripted
      ? (scriptedFallbackByProfile[profileId] ?? scriptedFallbackByProfile.demo)
      : genericFallback(tokens)
    return { candidates, source: 'fallback', error: 'The live service is unavailable. Showing a demo fallback.' }
  }
}

export async function simplifyMessage(text: string): Promise<SimplifyResponse> {
  try {
    return await post<SimplifyResponse>('/simplify', { text })
  } catch {
    return simplifyFallback(text)
  }
}

// No synthetic fallback here, unlike expandMessage/simplifyMessage above: there's no safe canned
// audio for arbitrary approved text (see backend/src/common/polly.py's module docstring). Callers
// should treat a thrown error or a null audioBase64 the same way -- fall back to the browser's own
// speechSynthesis, which speaks the exact same approved text, just with a lower-quality voice.
export async function speakMessage(text: string): Promise<SpeakResponse> {
  return post<SpeakResponse>('/speak', { text })
}

// No synthetic fallback here either: a guessed dynamicIcons/flaggedMoment on a network failure
// would violate the "never guess" design rule (CONTEXT_PIPELINE_PLAN.md). Callers should treat a
// thrown error as "no update this cycle" and leave the board as it was.
export async function fetchContextUpdate(payload: ContextUpdateRequest): Promise<ContextUpdateResponse> {
  return post<ContextUpdateResponse>('/context/update', payload)
}
