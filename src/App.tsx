import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowRight,
  BadgeCheck,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Ear,
  HandHelping,
  Info,
  Lightbulb,
  MessageCircleHeart,
  MessageCircleQuestionMark,
  Mic,
  MousePointerClick,
  OctagonX,
  Puzzle,
  Repeat,
  RotateCcw,
  ScanSearch,
  Shell,
  Sun,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Volume2,
  X,
  type LucideIcon,
} from 'lucide-react'
import { expandMessage, fetchContextUpdate, simplifyMessage, speakMessage } from './api'
import type {
  Candidate,
  DynamicIconSlot,
  FlaggedMoment,
  IconId,
  QuickReplyId,
  ResponseSource,
  SentenceToken,
  SimplifyResponse,
} from './types'
import { emitTurn, onTurn } from './turnEmitter'
import { ConversationBuffer } from './conversationBuffer'
import { symbolIcon } from './symbols'

type IconDefinition = {
  id: IconId
  label: string
  helper: string
  icon: LucideIcon
  tone: string
}

const ICONS: IconDefinition[] = [
  { id: 'REPEAT', label: 'Repeat', helper: 'Say it again', icon: Repeat, tone: 'lavender' },
  { id: 'IDEA', label: 'I have an idea', helper: 'I want to share', icon: Lightbulb, tone: 'sun' },
  { id: 'BUILD', label: 'Build', helper: 'Make or put together', icon: Puzzle, tone: 'blue' },
  { id: 'HELP', label: 'Help', helper: 'I need support', icon: HandHelping, tone: 'teal' },
  { id: 'AGREE', label: 'I agree', helper: 'Yes, that works', icon: ThumbsUp, tone: 'mint' },
  { id: 'DISAGREE', label: 'I disagree', helper: 'I think differently', icon: ThumbsDown, tone: 'peach' },
  { id: 'QUESTION', label: 'Question', helper: 'I want to ask', icon: MessageCircleQuestionMark, tone: 'lilac' },
  { id: 'STOP', label: 'Stop', helper: 'Please pause', icon: OctagonX, tone: 'coral' },
  { id: 'CHECK', label: 'Check', helper: 'Please look again', icon: ScanSearch, tone: 'sky' },
  { id: 'DONE', label: "I'm done", helper: 'I finished', icon: BadgeCheck, tone: 'green' },
]

const contexts = [
  { label: 'Science lab group project', value: 'classroom group project' },
  { label: 'Reading circle', value: 'reading circle' },
  { label: 'Math partner work', value: 'math partner work' },
  { label: 'Art table', value: 'art table' },
]

const feelings = [
  { label: 'Unsure' },
  { label: 'Calm' },
  { label: 'Excited' },
  { label: 'Frustrated' },
  { label: 'Low energy' },
]

// Style-labeled, not person-named -- this is one student (Maya, see the heading/avatar/message
// author below) with different personalization settings, not two different people. Mirrors
// backend/fixtures/expand_default.json's "demo"/"demo_alt" profiles 1:1.
const PROFILES = [
  { id: 'demo', label: 'Simple & direct', traits: 'Short sentences · likes making things' },
  { id: 'demo_alt', label: 'Curious & exploring', traits: 'Developing wording · likes science & puzzles' },
]

// Slot count is fixed (design rule: the dynamic row's slot positions never move, only their
// labels). Track D's dynamicIcons list is at most 6 items, most-relevant first -- mapped directly
// onto these positions, padded with nulls for any unfilled slot.
const DYNAMIC_ICON_SLOT_COUNT = 6
const EMPTY_DYNAMIC_ICONS: (DynamicIconSlot | null)[] = Array(DYNAMIC_ICON_SLOT_COUNT).fill(null)

const toDynamicSlots = (icons: DynamicIconSlot[]): (DynamicIconSlot | null)[] =>
  Array.from({ length: DYNAMIC_ICON_SLOT_COUNT }, (_, index) => icons[index] ?? null)

const iconById = (id: IconId) => ICONS.find((item) => item.id === id) ?? ICONS[6]

const normalizeWord = (word: string) => word.trim().toLowerCase()

const tokenKey = (token: SentenceToken) =>
  token.kind === 'icon' ? `icon:${token.id}` : `word:${normalizeWord(token.word)}`

function AacIcon({ id, size = 18 }: { id: IconId; size?: number }) {
  const Icon = iconById(id).icon
  return <Icon size={size} strokeWidth={2.2} aria-hidden="true" />
}

function SourcePill({ source }: { source: ResponseSource }) {
  const copy = {
    live: { label: 'Live AI', className: 'source-live' },
    mock: { label: 'Demo data', className: 'source-demo' },
    fallback: { label: 'Recorded demo fallback', className: 'source-fallback' },
  }[source]

  return (
    <span className={`source-pill ${copy.className}`}>
      <span className="source-dot" />
      {copy.label}
    </span>
  )
}

function MiniIcons({ ids }: { ids: IconId[] }) {
  return (
    <span className="mini-icons" aria-label={ids.map((id) => iconById(id).label).join(', ')}>
      {ids.map((id) => (
        <span key={id} title={iconById(id).label}>
          <AacIcon id={id} />
        </span>
      ))}
    </span>
  )
}

// Dumb presentational component -- slot content is swappable (fake data now, Track D's response
// once Track E wires it up). Position/count of slots is fixed; only the word in each slot changes.
// Keying each tile by its slot index + word makes React remount only the tile whose word actually
// changed, so the CSS mount animation naturally pulses just that tile instead of the whole row --
// tapping a filled tile toggles it into the sentence tray below, same as the fixed vocabulary tiles.
function DynamicIconRow({
  slots,
  selectedWordKeys,
  onToggle,
}: {
  slots: (DynamicIconSlot | null)[]
  selectedWordKeys: Set<string>
  onToggle: (slot: DynamicIconSlot) => void
}) {
  return (
    <div className="dynamic-row" role="group" aria-label="Words from the conversation">
      {slots.map((slot, index) => {
        if (!slot) {
          return (
            <div className="dynamic-tile empty" key={`${index}-empty`} aria-hidden="true">
              <span className="dynamic-tile-placeholder" />
            </div>
          )
        }
        const Icon = symbolIcon(slot.symbol)
        const isSelected = selectedWordKeys.has(normalizeWord(slot.word))
        return (
          <button
            type="button"
            className={`dynamic-tile filled ${isSelected ? 'selected' : ''}`}
            aria-pressed={isSelected}
            key={`${index}-${slot.word}`}
            onClick={() => onToggle(slot)}
          >
            {Icon && (
              <span className="dynamic-symbol">
                <Icon size={18} strokeWidth={2.2} aria-hidden="true" />
              </span>
            )}
            <strong>{slot.word}</strong>
          </button>
        )
      })}
    </div>
  )
}

function App() {
  const [sentence, setSentence] = useState<SentenceToken[]>([])
  const [context, setContext] = useState(contexts[0].value)
  const [feeling, setFeeling] = useState(feelings[0].label)
  const [profileId, setProfileId] = useState(PROFILES[0].id)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [candidateSource, setCandidateSource] = useState<ResponseSource | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [isExpanding, setIsExpanding] = useState(false)
  // Interim (not-yet-final) speech text, shown next to the mic as a live caption only -- it's
  // never sent anywhere; each finalized chunk is what actually drives simplify/context below.
  const [liveCaption, setLiveCaption] = useState('')
  const [isSimplifying, setIsSimplifying] = useState(false)
  // Every finalized utterance produces one instruction card, but they never overwrite each other --
  // that was overwhelming the student when a new one popped in mid-read. Instead each result queues
  // up here, and only left/right navigation or clicking "Done" moves which one is on screen.
  const [instructionQueue, setInstructionQueue] = useState<SimplifyResponse[]>([])
  const [instructionIndex, setInstructionIndex] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [showHelp, setShowHelp] = useState(false)
  const [dynamicIcons, setDynamicIcons] = useState<(DynamicIconSlot | null)[]>(EMPTY_DYNAMIC_ICONS)
  // Usually null -- Track D's flaggedMoment is omitted whenever the call is ambiguous, and even
  // when present it's only ever surfaced through the human-triggered button below (design rule:
  // receptive help is never auto-pushed).
  const [flaggedMoment, setFlaggedMoment] = useState<FlaggedMoment | null>(null)
  const [showFlaggedMoment, setShowFlaggedMoment] = useState(false)
  const conversationBufferRef = useRef(new ConversationBuffer())
  const lastApprovedMessageRef = useRef<string | null>(null)
  const [isListening, setIsListening] = useState(false)
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  // True whenever the student wants the session-scoped listening to keep going -- distinguishes an
  // explicit stop from the browser's forced onend (Web Speech API drops the connection ~every 60s),
  // so onend knows whether to auto-restart or actually end the session.
  const wantsListeningRef = useRef(false)
  // Guards against overlapping /simplify calls from the recognition callback (a stable closure that
  // can't read fresh state) -- set alongside isSimplifying so both the gate and the UI stay in sync.
  const isSimplifyingRef = useRef(false)

  // Wires Track A's continuous-listening turns into Track B's buffer, and -- only when its
  // debounce/topic-shift gate actually fires -- into Track D's live endpoint. Re-subscribes when
  // `context` (the activity anchor) changes so a fresh request always carries the current anchor;
  // it doesn't reset the buffer itself, since switching the anchor mid-conversation shouldn't
  // throw away turns already captured.
  useEffect(() => {
    const unsubscribe = onTurn((turn) => {
      const buffer = conversationBufferRef.current
      buffer.addTurn(turn)
      const payload = buffer.maybeRequestRefresh(context, lastApprovedMessageRef.current)
      if (!payload) return

      fetchContextUpdate({
        summary: payload.summary,
        rawWindow: payload.rawWindow,
        activityAnchor: payload.activityAnchor,
      })
        .then((response) => {
          setDynamicIcons(toDynamicSlots(response.dynamicIcons))
          setFlaggedMoment(response.flaggedMoment ?? null)
        })
        .catch(() => {
          // Never guess: a failed call just means no update this cycle, not a fabricated one.
        })
    })
    return unsubscribe
  }, [context])

  // Guards against a pending /expand response landing after the state it was requested for has
  // already changed (icon edits, profile switch, context change, or Reset while a request is in
  // flight) -- invalidating bumps the id and clears the loading state immediately, so a stale
  // response arriving later is a no-op instead of repopulating candidates for state that's gone.
  const requestIdRef = useRef(0)
  const invalidatePendingRequest = () => {
    requestIdRef.current += 1
    setIsExpanding(false)
  }

  const selectedWordKeys = useMemo(
    () => new Set(sentence.filter((token) => token.kind === 'word').map((token) => normalizeWord(token.word))),
    [sentence],
  )

  const toggleToken = (token: SentenceToken) => {
    invalidatePendingRequest()
    setCandidates([])
    setCandidateSource(null)
    setSentence((current) => {
      const key = tokenKey(token)
      if (current.some((item) => tokenKey(item) === key)) {
        return current.filter((item) => tokenKey(item) !== key)
      }
      return [...current, token]
    })
  }

  const toggleIcon = (id: IconId) => toggleToken({ kind: 'icon', id })
  const toggleWord = (slot: DynamicIconSlot) => toggleToken({ kind: 'word', word: slot.word, symbol: slot.symbol })

  const switchProfile = (id: string) => {
    invalidatePendingRequest()
    setCandidates([])
    setCandidateSource(null)
    setProfileId(id)
  }

  const changeContext = (value: string) => {
    invalidatePendingRequest()
    setCandidates([])
    setCandidateSource(null)
    setContext(value)
  }

  const makeMessage = async () => {
    if (!sentence.length) return
    invalidatePendingRequest()
    const requestId = requestIdRef.current
    setIsExpanding(true)
    setCandidates([])
    const response = await expandMessage(sentence, context, profileId)
    if (requestIdRef.current !== requestId) return // superseded; loading state already handled at invalidation time
    setIsExpanding(false)
    setCandidates(response.candidates)
    setCandidateSource(response.source)
  }

  const speakText = (text: string) => {
    const speakWithBrowserVoice = () => {
      if (!('speechSynthesis' in window)) return
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.rate = 0.94
      window.speechSynthesis.speak(utterance)
    }

    // Real Polly playback (Kevin, neural) when available; browser speechSynthesis is only a
    // last-resort fallback -- it still speaks the exact approved text, just with a lower-quality
    // voice, so falling back to it here is safe (unlike the backend's own bundled-clip fallback,
    // which may only ever play back its one fixed sentence).
    speakMessage(text)
      .then((response) => {
        if (!response.audioBase64) {
          speakWithBrowserVoice()
          return
        }
        const audio = new Audio(`data:${response.contentType};base64,${response.audioBase64}`)
        audio.play().catch(speakWithBrowserVoice)
      })
      .catch(speakWithBrowserVoice)
  }

  const approveCandidate = (candidate: Candidate) => {
    lastApprovedMessageRef.current = candidate.text
    setSentence([])
    setCandidates([])
    setCandidateSource(null)
    setNotice('Your message was spoken aloud.')
    window.setTimeout(() => setNotice(null), 3200)

    speakText(candidate.text)
  }

  // Runs /simplify against one finalized utterance from the room -- this is what the "Following
  // along" card below now depends on, replacing the old typed-and-sent composer flow entirely.
  // Guarded by a ref (not the isSimplifying state) because this is called from inside the
  // recognition.onresult closure, which doesn't get fresh state across renders.
  const runSimplifyForTurn = async (text: string) => {
    if (isSimplifyingRef.current) return
    isSimplifyingRef.current = true
    setIsSimplifying(true)
    setLiveCaption('')
    const response = await simplifyMessage(text)
    // Only jump the view to this new instruction if nothing was queued yet (first one this
    // session). Otherwise it joins the back of the queue and waits for the student to page to it.
    setInstructionQueue((queue) => {
      if (queue.length === 0) setInstructionIndex(0)
      return [...queue, response]
    })
    setIsSimplifying(false)
    isSimplifyingRef.current = false
  }

  const currentInstruction = instructionQueue[instructionIndex] ?? null
  const hasOlderInstruction = instructionIndex > 0
  const hasNewerInstruction = instructionIndex < instructionQueue.length - 1

  const goToInstruction = (delta: number) => {
    setInstructionIndex((index) => {
      const next = index + delta
      return Math.min(Math.max(next, 0), instructionQueue.length - 1)
    })
  }

  const startRecognition = () => {
    const SpeechRecognitionCtor = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!SpeechRecognitionCtor) {
      setNotice('Voice input needs Chrome or Edge.')
      window.setTimeout(() => setNotice(null), 3200)
      wantsListeningRef.current = false
      return
    }

    const recognition = new SpeechRecognitionCtor()
    recognition.lang = 'en-US'
    recognition.continuous = true
    recognition.interimResults = true

    recognition.onresult = (event) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const chunk = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          const text = chunk.trim()
          if (text) {
            emitTurn({ text, timestamp: Date.now() })
            void runSimplifyForTurn(text)
          }
        } else {
          interim += chunk
        }
      }
      setLiveCaption(interim.trim())
    }

    recognition.onerror = () => {
      setNotice("Didn't catch that. Keep listening or try again.")
      window.setTimeout(() => setNotice(null), 3200)
    }

    // The browser forces onend roughly every 60s even mid-session. If the student never asked to
    // stop, treat this as a transparent hiccup and restart immediately rather than ending the
    // listening session and requiring another click.
    recognition.onend = () => {
      recognitionRef.current = null
      if (wantsListeningRef.current) {
        startRecognition()
        return
      }
      setIsListening(false)
    }

    recognitionRef.current = recognition
    setIsListening(true)
    recognition.start()
  }

  const toggleVoiceInput = () => {
    if (isListening) {
      wantsListeningRef.current = false
      recognitionRef.current?.stop()
      return
    }

    setLiveCaption('')
    wantsListeningRef.current = true
    startRecognition()
  }

  const sendQuickReply = (reply: QuickReplyId) => {
    const text = reply === 'DONE' ? "I'm done!" : 'I still need some help.'
    speakText(text)
    setNotice('Your reply was spoken aloud.')
    window.setTimeout(() => setNotice(null), 2800)

    // Marking an instruction done moves on to whatever's next in the queue -- if nothing is
    // queued yet, stay put rather than running off the end.
    if (reply === 'DONE') goToInstruction(1)
  }

  const resetDemo = () => {
    invalidatePendingRequest()
    setSentence([])
    setCandidates([])
    setCandidateSource(null)
    setInstructionQueue([])
    setInstructionIndex(0)
    setLiveCaption('')
    setFeeling(feelings[0].label)
    setContext(contexts[0].value)
    setProfileId(PROFILES[0].id)
    setDynamicIcons(EMPTY_DYNAMIC_ICONS)
    setFlaggedMoment(null)
    setShowFlaggedMoment(false)
    conversationBufferRef.current = new ConversationBuffer()
    lastApprovedMessageRef.current = null
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#student-workspace">Skip to communication board</a>

      <header className="topbar">
        <div className="brand" aria-label="Pebble home">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span className="brand-word">pebble</span>
          <span className="brand-tagline">Every idea belongs.</span>
        </div>

        <div className="topbar-actions">
          <div className="session-context" title="Current classroom activity">
            <span className="presence-dot" />
            <span><strong>Science Lab</strong><small>4 people connected</small></span>
          </div>
          <button className="icon-button" type="button" onClick={() => setShowHelp(true)} aria-label="How Pebble works">
            <CircleHelp size={21} />
          </button>
          <button className="reset-button" type="button" onClick={resetDemo}>
            <RotateCcw size={17} />
            <span>Reset demo</span>
          </button>
        </div>
      </header>

      <main className="workspace">
        <section
          id="student-workspace"
          className="panel student-panel mobile-active"
          aria-labelledby="student-title"
        >
          <div className="sand-decor" aria-hidden="true">
            <Sun className="beach-sun" />
            <span className="sand-dune sand-dune-one" />
            <span className="sand-dune sand-dune-two" />
            <Shell className="sand-shell" />
          </div>
          <div className="panel-heading student-heading">
            <div className="person-block">
              <div className="avatar student-avatar" aria-hidden="true">M</div>
              <div>
                <span className="eyebrow">AAC workspace</span>
                <h1 id="student-title">Maya’s voice</h1>
              </div>
            </div>
            <div className="heading-actions">
              <button
                type="button"
                className="help-understand-button"
                aria-pressed={showFlaggedMoment}
                onClick={() => setShowFlaggedMoment((value) => !value)}
              >
                <HandHelping size={15} /> <span>Help Maya understand</span>
              </button>
              <div className="take-time"><Clock3 size={15} /> Take your time</div>
            </div>
          </div>

          <div className="student-scroll">
            <section className="listening-control" aria-label="Ambient listening">
              <button
                className={`mic-button ${isListening ? 'listening' : ''}`}
                type="button"
                onClick={toggleVoiceInput}
                aria-pressed={isListening}
                aria-label={isListening ? 'Stop listening' : 'Start listening'}
              >
                <Mic size={22} />
              </button>
              <div className="listening-status">
                <strong>{isListening ? 'Listening…' : 'Not listening'}</strong>
                <span>
                  {isListening
                    ? liveCaption || 'Following the conversation…'
                    : 'Turn on the mic to follow along and get help understanding.'}
                </span>
              </div>
            </section>

            {showFlaggedMoment && (
              <div className="flagged-moment-card" role="status">
                {flaggedMoment ? (
                  <>
                    <MiniIcons ids={flaggedMoment.icons} />
                    <span><small>Might need your attention</small><strong>{flaggedMoment.label}</strong></span>
                  </>
                ) : (
                  <span className="flagged-moment-empty">Nothing flagged in the conversation right now.</span>
                )}
              </div>
            )}

            {((isSimplifying && instructionQueue.length === 0) || currentInstruction) && (
              <section className="incoming-card" aria-live="polite" aria-busy={isSimplifying && instructionQueue.length === 0}>
                {instructionQueue.length > 1 && (
                  <div className="instruction-nav">
                    <button
                      type="button"
                      onClick={() => goToInstruction(-1)}
                      disabled={!hasOlderInstruction}
                      aria-label="Show the previous instruction"
                    >
                      <ChevronLeft size={17} />
                    </button>
                    <span>{instructionIndex + 1} of {instructionQueue.length}</span>
                    <button
                      type="button"
                      onClick={() => goToInstruction(1)}
                      disabled={!hasNewerInstruction}
                      aria-label="Show the next instruction"
                      className={hasNewerInstruction ? 'has-unseen' : ''}
                    >
                      <ChevronRight size={17} />
                    </button>
                  </div>
                )}
                {!currentInstruction && isSimplifying ? (
                  <div className="thinking-state">
                    <div className="thinking-orb"><Sparkles size={22} /></div>
                    <div><strong>Making that easier to follow…</strong><span>Finding the important steps</span></div>
                  </div>
                ) : currentInstruction?.status === 'please_repeat' ? (
                  <div className="repeat-state">
                    <span className="repeat-symbol"><Ear size={27} /></span>
                    <div>
                      <span className="eyebrow">Let’s try that again</span>
                      <h2>I didn’t catch enough to be sure.</h2>
                      <p>Ask them to say it another way.</p>
                      {currentInstruction.source && <SourcePill source={currentInstruction.source} />}
                    </div>
                  </div>
                ) : currentInstruction ? (
                  <>
                    <div className="incoming-header">
                      <div>
                        <span className="eyebrow">From the conversation</span>
                        <h2>Here’s what to do</h2>
                      </div>
                      <SourcePill source={currentInstruction.source} />
                    </div>
                    <ol className="step-list">
                      {currentInstruction.steps.map((step, index) => (
                        <li key={`${step.label}-${index}`}>
                          <button
                            type="button"
                            className="step-row"
                            onClick={() => speakText(step.label)}
                            aria-label={`Hear step ${index + 1} out loud: ${step.label}`}
                          >
                            <span className="step-number">{index + 1}</span>
                            <MiniIcons ids={step.icons} />
                            <strong>{step.label}</strong>
                            <Volume2 className="step-listen-icon" size={16} aria-hidden="true" />
                          </button>
                        </li>
                      ))}
                    </ol>
                    {currentInstruction.warnings.map((warning, index) => (
                      <div className="warning-card" key={`${warning.label}-${index}`}>
                        <MiniIcons ids={warning.icons} />
                        <span><small>Important check</small><strong>{warning.label}</strong></span>
                      </div>
                    ))}
                    <div className="quick-replies">
                      <span>Ready to answer?</span>
                      <div>
                        {currentInstruction.quickReplies.map((reply) => (
                          <button key={reply} onClick={() => sendQuickReply(reply)} className={reply === 'DONE' ? 'reply-done' : 'reply-help'}>
                            {reply === 'DONE' ? <><Check size={15} /> Done</> : <><HandHelping size={15} /> Need help</>}
                          </button>
                        ))}
                      </div>
                    </div>
                    <button className="transcript-toggle" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
                      <ChevronDown size={17} /> {expanded ? 'Hide' : 'Show'} exactly what was said
                    </button>
                    {expanded && <blockquote className="transcript">“{currentInstruction.transcript}”</blockquote>}
                  </>
                ) : null}
              </section>
            )}

            <section className="setup-row" aria-label="Conversation settings">
              <label>
                <span>We’re working on</span>
                <div className="select-wrap">
                  <select value={context} onChange={(event) => changeContext(event.target.value)}>
                    {contexts.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                  <ChevronDown size={17} />
                </div>
              </label>
              <fieldset className="profile-toggle-row">
                <legend>Talking style</legend>
                <div className="profile-toggle" role="group" aria-label="Talking style">
                  {PROFILES.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={profileId === item.id ? 'active' : ''}
                      aria-pressed={profileId === item.id}
                      onClick={() => switchProfile(item.id)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
                <small className="profile-traits">{PROFILES.find((item) => item.id === profileId)?.traits}</small>
              </fieldset>
              <label>
                <span>I’m feeling</span>
                <div className="select-wrap">
                  <select value={feeling} onChange={(event) => setFeeling(event.target.value)}>
                    {feelings.map((item) => <option key={item.label} value={item.label}>{item.label}</option>)}
                  </select>
                  <ChevronDown size={17} />
                </div>
              </label>
            </section>

            <section className="board-section" aria-labelledby="board-title">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">Choose one or more</span>
                  <h2 id="board-title">What do you want to say?</h2>
                </div>
                <span className="selection-count">{sentence.length} selected</span>
              </div>

              <div className="aac-grid">
                {ICONS.map((item) => {
                  const selectedIndex = sentence.findIndex((token) => token.kind === 'icon' && token.id === item.id)
                  const isSelected = selectedIndex >= 0
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`aac-tile tone-${item.tone} ${isSelected ? 'selected' : ''}`}
                      onClick={() => toggleIcon(item.id)}
                      aria-pressed={isSelected}
                      aria-label={`${item.label}: ${item.helper}`}
                    >
                      {isSelected && <span className="selection-order" aria-label={`Selected item ${selectedIndex + 1}`}><Check size={13} strokeWidth={3} /></span>}
                      <span className="aac-symbol"><AacIcon id={item.id} size={30} /></span>
                      <strong>{item.label}</strong>
                      <small>{item.helper}</small>
                    </button>
                  )
                })}
              </div>
            </section>

            <section className="dynamic-row-section" aria-labelledby="dynamic-row-title">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">Following along</span>
                  <h2 id="dynamic-row-title">Words from the conversation</h2>
                </div>
              </div>
              <DynamicIconRow slots={dynamicIcons} selectedWordKeys={selectedWordKeys} onToggle={toggleWord} />
            </section>
          </div>

          <div className="student-composer">
            <div className={`selection-tray ${sentence.length ? 'has-items' : ''}`} aria-live="polite">
              {sentence.length ? (
                <>
                  <div className="selected-chips">
                    {sentence.map((token, index) => {
                      const label = token.kind === 'icon' ? iconById(token.id).label : token.word
                      const WordIcon = token.kind === 'word' ? symbolIcon(token.symbol) : null
                      return (
                        <button key={tokenKey(token)} onClick={() => toggleToken(token)} title={`Remove ${label}`}>
                          <span className="token-icon">
                            {token.kind === 'icon' ? (
                              <AacIcon id={token.id} size={15} />
                            ) : (
                              WordIcon && <WordIcon size={15} aria-hidden="true" />
                            )}
                          </span>{' '}
                          {label} <X size={13} />
                          {index < sentence.length - 1 && <i aria-hidden="true"><ArrowRight size={14} /></i>}
                        </button>
                      )
                    })}
                  </div>
                  <button
                    className="clear-button"
                    onClick={() => {
                      invalidatePendingRequest()
                      setCandidates([])
                      setCandidateSource(null)
                      setSentence([])
                    }}
                    aria-label="Clear all selections"
                  ><Trash2 size={17} /></button>
                </>
              ) : (
                <span className="tray-placeholder"><MousePointerClick size={17} /> Tap a card to begin your message</span>
              )}
            </div>
            <button className="primary-button" onClick={makeMessage} disabled={!sentence.length || isExpanding}>
              {isExpanding ? <><span className="spinner" /> Finding your words…</> : <><Sparkles size={19} /> Create my message</>}
            </button>
          </div>

          {candidates.length > 0 && (
            <div className="candidate-backdrop" role="presentation">
              <section className="candidate-sheet" role="dialog" aria-modal="true" aria-labelledby="candidate-title">
                <div className="candidate-top">
                  <div className="candidate-icon"><MessageCircleHeart size={24} /></div>
                  <div>
                    <span className="eyebrow">You’re in control</span>
                    <h2 id="candidate-title">Which sounds most like you?</h2>
                    <p>Nothing is shared until you choose.</p>
                  </div>
                  <button className="icon-button close-dialog" onClick={() => setCandidates([])} aria-label="Close message choices"><X size={20} /></button>
                </div>
                {candidateSource && <SourcePill source={candidateSource} />}
                <div className="candidate-list">
                  {candidates.map((candidate, index) => (
                    <div className="candidate-row" key={candidate.id}>
                      <button
                        type="button"
                        className="candidate-listen"
                        onClick={(event) => {
                          event.stopPropagation()
                          speakText(candidate.text)
                        }}
                        aria-label={`Hear option ${index + 1} out loud: ${candidate.text}`}
                      >
                        <Volume2 size={17} />
                      </button>
                      <button className="candidate-choose" onClick={() => approveCandidate(candidate)}>
                        <span className="candidate-number">{index + 1}</span>
                        <span>{candidate.text}</span>
                        <span className="choose-label">Choose <ArrowRight size={16} /></span>
                      </button>
                    </div>
                  ))}
                </div>
                <p className="privacy-note"><Info size={14} /> Pebble offers choices. You decide what represents you.</p>
              </section>
            </div>
          )}
        </section>
      </main>

      {notice && <div className="toast" role="status"><span><Check size={17} /></span>{notice}</div>}

      {showHelp && (
        <div className="help-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setShowHelp(false)}>
          <section className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="help-title">
            <button className="icon-button close-dialog" onClick={() => setShowHelp(false)} aria-label="Close help"><X size={20} /></button>
            <div className="help-mark"><MessageCircleHeart size={28} /></div>
            <span className="eyebrow">A communication bridge</span>
            <h2 id="help-title">Pebble helps everyone meet in the middle.</h2>
            <div className="help-steps">
              <div><span>1</span><p><strong>Maya chooses ideas</strong> using familiar communication cards.</p></div>
              <div><span>2</span><p><strong>Pebble offers natural phrases.</strong> Maya decides which one sounds right.</p></div>
              <div><span>3</span><p><strong>Fast group messages become clear steps</strong> that are easier to follow.</p></div>
            </div>
            <p className="help-principle">The AI never speaks for the student. It helps the student be heard.</p>
            <button className="primary-button" onClick={() => setShowHelp(false)}>Got it</button>
          </section>
        </div>
      )}
    </div>
  )
}

export default App
