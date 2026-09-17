// Conversation buffer + context formalization (Track B). Consumes the `Turn` shape Track A
// publishes (src/turnEmitter.ts) but does not subscribe to that emitter itself -- callers wire
// `addTurn` to whatever emitter is available, real or stubbed, keeping this module swappable and
// independently testable.
import type { Turn } from './turnEmitter'

const RAW_WINDOW_SIZE = 8
const MIN_REFRESH_GAP_MS = 25_000

// Deliberately tiny/cheap -- this is a local heuristic gate, not a summarizer. It only needs to
// tell "probably the same topic" from "probably moved on", not produce good prose.
const STOPWORDS = new Set([
  'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
  'to', 'of', 'in', 'on', 'at', 'for', 'with', 'and', 'or', 'but', 'so',
  'i', 'you', 'we', 'they', 'he', 'she', 'it', 'this', 'that', 'these', 'those',
  'do', 'does', 'did', 'have', 'has', 'had', 'will', 'would', 'can', 'could',
  'just', 'like', 'okay', 'ok', 'um', 'uh', 'yeah', 'about', 'what', 'then',
])

const keywordsOf = (text: string): Set<string> =>
  new Set(
    text
      .toLowerCase()
      .split(/[^a-z0-9']+/)
      .filter((word) => word.length > 2 && !STOPWORDS.has(word)),
  )

export type ContextPayload = {
  summary: string
  rawWindow: Turn[]
  activityAnchor: string
  studentLastApprovedMessage: string | null
}

export class ConversationBuffer {
  private rawWindow: Turn[] = []
  private summary = ''
  private lastRefreshAt = 0

  addTurn(turn: Turn): void {
    this.rawWindow.push(turn)
    if (this.rawWindow.length > RAW_WINDOW_SIZE) {
      // Only regenerate the summary when a turn actually ages out of the raw window -- most
      // turns just extend the window and cost nothing.
      const aged = this.rawWindow.shift() as Turn
      this.summary = `${this.summary} ${aged.text}`.trim()
    }
  }

  getSummary(): string {
    return this.summary
  }

  getRawWindow(): Turn[] {
    return [...this.rawWindow]
  }

  private rawWindowText(): string {
    return this.rawWindow.map((turn) => turn.text).join(' ')
  }

  // Cheap local gate for Track E's backend call: fires only at a turn boundary (called after
  // addTurn), only once the raw window actually contains vocabulary the summary hasn't seen
  // (a topic-shift proxy, not real diffing), and only after a minimum time gap since the last
  // refresh -- this is the token-efficiency mechanism, most turns should short-circuit here.
  shouldRequestRefresh(now: number = Date.now()): boolean {
    if (this.rawWindow.length === 0) return false
    if (now - this.lastRefreshAt < MIN_REFRESH_GAP_MS) return false

    const summaryKeywords = keywordsOf(this.summary)
    const windowKeywords = keywordsOf(this.rawWindowText())
    const hasNewKeyword = [...windowKeywords].some((word) => !summaryKeywords.has(word))
    return hasNewKeyword
  }

  markRefreshed(now: number = Date.now()): void {
    this.lastRefreshAt = now
  }

  composePayload(activityAnchor: string, studentLastApprovedMessage: string | null): ContextPayload {
    return {
      summary: this.summary,
      rawWindow: this.getRawWindow(),
      activityAnchor,
      studentLastApprovedMessage,
    }
  }

  // Convenience for Track E: evaluates the gate and, if it passes, marks the refresh as taken and
  // returns the payload to send -- returns null when nothing should be sent, so most turns are a
  // single cheap no-op call for the caller.
  maybeRequestRefresh(
    activityAnchor: string,
    studentLastApprovedMessage: string | null,
    now: number = Date.now(),
  ): ContextPayload | null {
    if (!this.shouldRequestRefresh(now)) return null
    this.markRefreshed(now)
    return this.composePayload(activityAnchor, studentLastApprovedMessage)
  }
}
