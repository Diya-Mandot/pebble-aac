export type IconId =
  | 'CONFUSED'
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

export interface ChatMessage {
  id: string
  sender: 'student' | 'peer' | 'system'
  author: string
  text: string
  time: string
  source?: ResponseSource
  expandedFrom?: IconId[]
}
