import type { ExpandResponse, IconId, SimplifyResponse, SpeakResponse } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

const expandFallback: ExpandResponse = {
  candidates: [
    { id: 'local-1', text: "I'm confused about building this. Can you help?" },
    { id: 'local-2', text: "I'm stuck on this part. Could we work through it together?" },
    { id: 'local-3', text: 'Can someone show me the first step for building this?' },
  ],
  source: 'fallback',
  error: 'The live service is unavailable. Showing the recorded demo fallback.',
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

export async function expandMessage(icons: IconId[], context: string): Promise<ExpandResponse> {
  try {
    return await post<ExpandResponse>('/expand', { icons, context, profileId: 'demo' })
  } catch {
    return expandFallback
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
