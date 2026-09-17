export type IconId =
  | 'REPEAT'
  | 'IDEA'
  | 'BUILD'
  | 'HELP'
  | 'AGREE'
  | 'DISAGREE'
  | 'QUESTION'
  | 'STOP'
  | 'CHECK'
  | 'DONE'

export type QuickReplyId = 'DONE' | 'NEED_HELP'
export type ResponseSource = 'mock' | 'live' | 'fallback'

export interface Candidate {
  id: string
  text: string
}

export interface ExpandResponse {
  candidates: Candidate[]
  source: ResponseSource
  error?: string
}

export interface SimpleItem {
  icons: IconId[]
  label: string
}

export interface SimplifyResponse {
  steps: SimpleItem[]
  warnings: SimpleItem[]
  quickReplies: QuickReplyId[]
  transcript: string
  status: 'ok' | 'please_repeat'
  source: ResponseSource
  error?: string
}

export interface SpeakResponse {
  audioBase64: string | null
  contentType: string
  source: ResponseSource
  error?: string
}

export interface DynamicIconSlot {
  word: string
  symbol?: string
}

export type SentenceToken =
  | { kind: 'icon'; id: IconId }
  | { kind: 'word'; word: string; symbol?: string }

export interface FlaggedMoment {
  label: string
  icons: IconId[]
}

export interface ContextUpdateRequest {
  summary: string
  rawWindow: { text: string; timestamp: number }[]
  activityAnchor: string
}

export interface ContextUpdateResponse {
  summary: string
  dynamicIcons: DynamicIconSlot[]
  flaggedMoment?: FlaggedMoment
  source: ResponseSource
  error?: string
}
