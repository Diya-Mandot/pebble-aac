import { useMemo, useRef, useState } from 'react'
import {
  ArrowRight,
  BadgeCheck,
  Check,
  ChevronDown,
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
  RotateCcw,
  ScanSearch,
  Send,
  Shell,
  Sun,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Users,
  Volume2,
  X,
  type LucideIcon,
} from 'lucide-react'
import { expandMessage, simplifyMessage, speakMessage } from './api'
import type {
  Candidate,
  ChatMessage,
  IconId,
  QuickReplyId,
  ResponseSource,
  SimplifyResponse,
} from './types'

type IconDefinition = {
  id: IconId
  label: string
  helper: string
  icon: LucideIcon
  tone: string
}

const ICONS: IconDefinition[] = [
  { id: 'CONFUSED', label: 'Confused', helper: "I don't understand", icon: CircleHelp, tone: 'lavender' },
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

// Each student is a distinct workspace identity (own name, avatar, chat history, icon selections)
// backed 1:1 by one of backend/fixtures/expand_default.json's real profiles -- profileId doubles as
// studentId, which is safe here specifically because each profileId already represents exactly one
// persona's personalization settings, never a style shared across people.
const STUDENTS = [
  { id: 'demo', name: 'Maya', avatarInitial: 'M', traits: 'Short sentences · likes making things' },
  { id: 'demo_alt', name: 'Theo', avatarInitial: 'T', traits: 'Developing wording · likes science & puzzles' },
]

const initialMessages: ChatMessage[] = [
  {
    id: 'welcome',
    sender: 'system',
    author: 'Pebble',
    text: 'Science team is ready. Take your time—everyone gets a turn.',
    time: 'Now',
  },
  {
    id: 'peer-welcome',
    sender: 'peer',
    author: 'Jordan',
    text: "Let's figure out the circuit together. What should we try first?",
    time: '10:24 AM',
  },
]

// Per-student state that must not bleed between students when switching -- everything else
// (loading flags, mic state, active mobile panel, toasts) is transient UI chrome shared across
// whichever student is currently active.
type StudentSession = {
  messages: ChatMessage[]
  selectedIcons: IconId[]
  context: string
  feeling: string
  candidates: Candidate[]
  candidateSource: ResponseSource | null
  peerText: string
  simplified: SimplifyResponse | null
  transcriptExpanded: boolean
}

const makeInitialSession = (): StudentSession => ({
  messages: initialMessages,
  selectedIcons: [],
  context: contexts[0].value,
  feeling: feelings[0].label,
  candidates: [],
  candidateSource: null,
  peerText: '',
  simplified: null,
  transcriptExpanded: false,
})

const timeNow = () =>
  new Intl.DateTimeFormat('en', { hour: 'numeric', minute: '2-digit' }).format(new Date())

const iconById = (id: IconId) => ICONS.find((item) => item.id === id) ?? ICONS[6]

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

function App() {
  const [sessions, setSessions] = useState<Record<string, StudentSession>>(() =>
    Object.fromEntries(STUDENTS.map((student) => [student.id, makeInitialSession()])),
  )
  const [activeStudentId, setActiveStudentId] = useState(STUDENTS[0].id)
  const activeStudent = STUDENTS.find((student) => student.id === activeStudentId) ?? STUDENTS[0]
  const session = sessions[activeStudentId]

  const updateSession = (
    patch: Partial<StudentSession> | ((current: StudentSession) => Partial<StudentSession>),
  ) => {
    setSessions((current) => {
      const prev = current[activeStudentId]
      const delta = typeof patch === 'function' ? patch(prev) : patch
      return { ...current, [activeStudentId]: { ...prev, ...delta } }
    })
  }

  const [isExpanding, setIsExpanding] = useState(false)
  const [isSimplifying, setIsSimplifying] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [showHelp, setShowHelp] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const [activeMobilePanel, setActiveMobilePanel] = useState<'student' | 'group'>('student')
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const workspaceRef = useRef<HTMLElement>(null)
  const resizingRef = useRef(false)

  const CHAT_MIN_WIDTH_PX = 360
  const CHAT_MAX_WIDTH_PCT = 50
  const [chatWidthPct, setChatWidthPct] = useState(46)

  const clampChatWidthPct = (pct: number, containerWidth: number) => {
    const minPct = containerWidth ? (CHAT_MIN_WIDTH_PX / containerWidth) * 100 : 0
    return Math.min(CHAT_MAX_WIDTH_PCT, Math.max(minPct, pct))
  }

  const updateChatWidthFromPointer = (clientX: number) => {
    const rect = workspaceRef.current?.getBoundingClientRect()
    if (!rect || !rect.width) return
    const distanceFromRight = rect.right - clientX
    const pct = (distanceFromRight / rect.width) * 100
    setChatWidthPct(clampChatWidthPct(pct, rect.width))
  }

  const handleResizerPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    resizingRef.current = true
    event.currentTarget.setPointerCapture(event.pointerId)
    event.currentTarget.classList.add('active')
  }

  const handleResizerPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!resizingRef.current) return
    updateChatWidthFromPointer(event.clientX)
  }

  const handleResizerPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    resizingRef.current = false
    event.currentTarget.classList.remove('active')
  }

  const handleResizerKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const rect = workspaceRef.current?.getBoundingClientRect()
    if (!rect || !rect.width) return
    const step = 2
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault()
      const direction = event.key === 'ArrowLeft' ? 1 : -1
      setChatWidthPct((current) => clampChatWidthPct(current + direction * step, rect.width))
    }
  }

  // Guards against a pending /expand response landing after the state it was requested for has
  // already changed (icon edits, profile switch, context change, or Reset while a request is in
  // flight) -- invalidating bumps the id and clears the loading state immediately, so a stale
  // response arriving later is a no-op instead of repopulating candidates for state that's gone.
  const requestIdRef = useRef(0)
  const invalidatePendingRequest = () => {
    requestIdRef.current += 1
    setIsExpanding(false)
  }

  const selectedDefinitions = useMemo(
    () => session.selectedIcons.map((id) => iconById(id)),
    [session.selectedIcons],
  )

  const toggleIcon = (id: IconId) => {
    invalidatePendingRequest()
    updateSession((current) => ({
      candidates: [],
      candidateSource: null,
      selectedIcons: current.selectedIcons.includes(id)
        ? current.selectedIcons.filter((item) => item !== id)
        : [...current.selectedIcons, id],
    }))
  }

  const switchStudent = (id: string) => {
    if (id === activeStudentId) return
    invalidatePendingRequest()
    recognitionRef.current?.stop()
    setActiveStudentId(id)
    setActiveMobilePanel('student')
  }

  const changeContext = (value: string) => {
    invalidatePendingRequest()
    updateSession({ candidates: [], candidateSource: null, context: value })
  }

  const setFeeling = (value: string) => updateSession({ feeling: value })

  const makeMessage = async () => {
    const { selectedIcons, context } = session
    if (!selectedIcons.length) return
    invalidatePendingRequest()
    const requestId = requestIdRef.current
    const profileId = activeStudentId
    setIsExpanding(true)
    updateSession({ candidates: [] })
    const response = await expandMessage(selectedIcons, context, profileId)
    if (requestIdRef.current !== requestId) return // superseded; loading state already handled at invalidation time
    setIsExpanding(false)
    updateSession({ candidates: response.candidates, candidateSource: response.source })
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
    updateSession((current) => ({
      messages: [
        ...current.messages,
        {
          id: crypto.randomUUID(),
          sender: 'student',
          author: activeStudent.name,
          text: candidate.text,
          time: timeNow(),
          source: current.candidateSource ?? undefined,
          expandedFrom: [...current.selectedIcons],
        },
      ],
      selectedIcons: [],
      candidates: [],
      candidateSource: null,
    }))
    setActiveMobilePanel('group')
    setNotice('Your message was shared with the group.')
    window.setTimeout(() => setNotice(null), 3200)

    speakText(candidate.text)
  }

  const toggleVoiceInput = () => {
    if (isListening) {
      recognitionRef.current?.stop()
      return
    }

    const SpeechRecognitionCtor = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!SpeechRecognitionCtor) {
      setNotice('Voice input needs Chrome or Edge. Type your message for now.')
      window.setTimeout(() => setNotice(null), 3200)
      return
    }

    const recognition = new SpeechRecognitionCtor()
    recognition.lang = 'en-US'
    recognition.continuous = true
    recognition.interimResults = true
    let finalText = ''

    recognition.onresult = (event) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const chunk = event.results[i][0].transcript
        if (event.results[i].isFinal) finalText += `${chunk} `
        else interim += chunk
      }
      updateSession({ peerText: `${finalText}${interim}`.trim() })
    }

    recognition.onerror = () => {
      setNotice("Didn't catch that. Try again or type your message.")
      window.setTimeout(() => setNotice(null), 3200)
    }

    recognition.onend = () => {
      setIsListening(false)
      recognitionRef.current = null
    }

    recognitionRef.current = recognition
    setIsListening(true)
    recognition.start()
  }

  const sendPeerMessage = async () => {
    const text = session.peerText.trim()
    if (!text || isSimplifying) return

    recognitionRef.current?.stop()

    updateSession((current) => ({
      messages: [
        ...current.messages,
        { id: crypto.randomUUID(), sender: 'peer', author: 'Jordan', text, time: timeNow() },
      ],
      peerText: '',
    }))
    setIsSimplifying(true)
    setActiveMobilePanel('student')
    const response = await simplifyMessage(text)
    updateSession({ simplified: response })
    setIsSimplifying(false)
  }

  const sendQuickReply = (reply: QuickReplyId) => {
    const text = reply === 'DONE' ? "I'm done!" : 'I still need some help.'
    updateSession((current) => ({
      messages: [
        ...current.messages,
        { id: crypto.randomUUID(), sender: 'student', author: activeStudent.name, text, time: timeNow() },
      ],
    }))
    setNotice('Your reply was shared.')
    setActiveMobilePanel('group')
    window.setTimeout(() => setNotice(null), 2800)
  }

  const resetDemo = () => {
    invalidatePendingRequest()
    recognitionRef.current?.stop()
    setSessions(Object.fromEntries(STUDENTS.map((student) => [student.id, makeInitialSession()])))
    setActiveStudentId(STUDENTS[0].id)
    setActiveMobilePanel('student')
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

      <nav className="mobile-switcher" aria-label="Switch workspace">
        <button className={activeMobilePanel === 'student' ? 'active' : ''} onClick={() => setActiveMobilePanel('student')}>
          <MessageCircleHeart size={18} /> My voice
        </button>
        <button className={activeMobilePanel === 'group' ? 'active' : ''} onClick={() => setActiveMobilePanel('group')}>
          <Users size={18} /> Group chat
        </button>
      </nav>

      <main className="workspace" ref={workspaceRef}>
        <section
          id="student-workspace"
          className={`panel student-panel ${activeMobilePanel === 'student' ? 'mobile-active' : ''}`}
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
              <div className="avatar student-avatar" aria-hidden="true">{activeStudent.avatarInitial}</div>
              <div>
                <span className="eyebrow">AAC workspace</span>
                <h1 id="student-title">{activeStudent.name}’s voice</h1>
              </div>
            </div>
            <div className="take-time"><Clock3 size={15} /> Take your time</div>
          </div>

          <fieldset className="student-switch-row">
            <legend>Student</legend>
            <div className="student-switch" role="group" aria-label="Switch student">
              {STUDENTS.map((student) => (
                <button
                  key={student.id}
                  type="button"
                  className={activeStudentId === student.id ? 'active' : ''}
                  aria-pressed={activeStudentId === student.id}
                  onClick={() => switchStudent(student.id)}
                >
                  <span className="student-switch-avatar" aria-hidden="true">{student.avatarInitial}</span>
                  {student.name}
                </button>
              ))}
            </div>
            <small className="profile-traits">{activeStudent.traits}</small>
          </fieldset>

          <div className="student-scroll">
            {(isSimplifying || session.simplified) && (
              <section className="incoming-card" aria-live="polite" aria-busy={isSimplifying}>
                {isSimplifying ? (
                  <div className="thinking-state">
                    <div className="thinking-orb"><Sparkles size={22} /></div>
                    <div><strong>Making that easier to follow…</strong><span>Finding the important steps</span></div>
                  </div>
                ) : session.simplified?.status === 'please_repeat' ? (
                  <div className="repeat-state">
                    <span className="repeat-symbol"><Ear size={27} /></span>
                    <div>
                      <span className="eyebrow">Let’s try that again</span>
                      <h2>I didn’t catch enough to be sure.</h2>
                      <p>Ask your teammate to say it another way.</p>
                      {session.simplified.source && <SourcePill source={session.simplified.source} />}
                    </div>
                  </div>
                ) : session.simplified ? (
                  <>
                    <div className="incoming-header">
                      <div>
                        <span className="eyebrow">Jordan shared a plan</span>
                        <h2>Here’s what to do</h2>
                      </div>
                      <SourcePill source={session.simplified.source} />
                    </div>
                    <ol className="step-list">
                      {session.simplified.steps.map((step, index) => (
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
                    {session.simplified.warnings.map((warning, index) => (
                      <div className="warning-card" key={`${warning.label}-${index}`}>
                        <MiniIcons ids={warning.icons} />
                        <span><small>Important check</small><strong>{warning.label}</strong></span>
                      </div>
                    ))}
                    <div className="quick-replies">
                      <span>Ready to answer?</span>
                      <div>
                        {session.simplified.quickReplies.map((reply) => (
                          <button key={reply} onClick={() => sendQuickReply(reply)} className={reply === 'DONE' ? 'reply-done' : 'reply-help'}>
                            {reply === 'DONE' ? <><Check size={15} /> Done</> : <><HandHelping size={15} /> Need help</>}
                          </button>
                        ))}
                      </div>
                    </div>
                    <button
                      className="transcript-toggle"
                      onClick={() => updateSession((current) => ({ transcriptExpanded: !current.transcriptExpanded }))}
                      aria-expanded={session.transcriptExpanded}
                    >
                      <ChevronDown size={17} /> {session.transcriptExpanded ? 'Hide' : 'Show'} exactly what Jordan said
                    </button>
                    {session.transcriptExpanded && <blockquote className="transcript">“{session.simplified.transcript}”</blockquote>}
                  </>
                ) : null}
              </section>
            )}

            <section className="setup-row" aria-label="Conversation settings">
              <label>
                <span>We’re working on</span>
                <div className="select-wrap">
                  <select value={session.context} onChange={(event) => changeContext(event.target.value)}>
                    {contexts.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                  <ChevronDown size={17} />
                </div>
              </label>
              <label>
                <span>I’m feeling</span>
                <div className="select-wrap">
                  <select value={session.feeling} onChange={(event) => setFeeling(event.target.value)}>
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
                <span className="selection-count">{session.selectedIcons.length} selected</span>
              </div>

              <div className="aac-grid">
                {ICONS.map((item) => {
                  const selectedIndex = session.selectedIcons.indexOf(item.id)
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
          </div>

          <div className="student-composer">
            <div className={`selection-tray ${session.selectedIcons.length ? 'has-items' : ''}`} aria-live="polite">
              {selectedDefinitions.length ? (
                <>
                  <div className="selected-chips">
                    {selectedDefinitions.map((item, index) => (
                      <button key={item.id} onClick={() => toggleIcon(item.id)} title={`Remove ${item.label}`}>
                        <span className="token-icon"><AacIcon id={item.id} size={15} /></span> {item.label} <X size={13} />
                        {index < selectedDefinitions.length - 1 && <i aria-hidden="true"><ArrowRight size={14} /></i>}
                      </button>
                    ))}
                  </div>
                  <button
                    className="clear-button"
                    onClick={() => {
                      invalidatePendingRequest()
                      updateSession({ candidates: [], candidateSource: null, selectedIcons: [] })
                    }}
                    aria-label="Clear all selections"
                  ><Trash2 size={17} /></button>
                </>
              ) : (
                <span className="tray-placeholder"><MousePointerClick size={17} /> Tap a card to begin your message</span>
              )}
            </div>
            <button className="primary-button" onClick={makeMessage} disabled={!session.selectedIcons.length || isExpanding}>
              {isExpanding ? <><span className="spinner" /> Finding your words…</> : <><Sparkles size={19} /> Create my message</>}
            </button>
          </div>

          {session.candidates.length > 0 && (
            <div className="candidate-backdrop" role="presentation">
              <section className="candidate-sheet" role="dialog" aria-modal="true" aria-labelledby="candidate-title">
                <div className="candidate-top">
                  <div className="candidate-icon"><MessageCircleHeart size={24} /></div>
                  <div>
                    <span className="eyebrow">You’re in control</span>
                    <h2 id="candidate-title">Which sounds most like you?</h2>
                    <p>Nothing is shared until you choose.</p>
                  </div>
                  <button className="icon-button close-dialog" onClick={() => updateSession({ candidates: [] })} aria-label="Close message choices"><X size={20} /></button>
                </div>
                {session.candidateSource && <SourcePill source={session.candidateSource} />}
                <div className="candidate-list">
                  {session.candidates.map((candidate, index) => (
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

        <div
          className="panel-resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize chat panel"
          aria-valuenow={Math.round(chatWidthPct)}
          aria-valuemin={0}
          aria-valuemax={CHAT_MAX_WIDTH_PCT}
          tabIndex={0}
          onPointerDown={handleResizerPointerDown}
          onPointerMove={handleResizerPointerMove}
          onPointerUp={handleResizerPointerUp}
          onPointerCancel={handleResizerPointerUp}
          onKeyDown={handleResizerKeyDown}
        />

        <section
          className={`panel group-panel ${activeMobilePanel === 'group' ? 'mobile-active' : ''}`}
          aria-labelledby="group-title"
          style={{ flexBasis: `${chatWidthPct}%` }}
        >
          <div className="ocean-decor" aria-hidden="true">
            <svg className="ocean-wave ocean-wave-back" viewBox="0 0 600 90" preserveAspectRatio="none">
              <path d="M0 42 C75 8 125 76 205 40 C285 4 340 78 425 40 C505 5 550 60 600 36 V90 H0 Z" />
            </svg>
            <svg className="ocean-wave ocean-wave-front" viewBox="0 0 600 90" preserveAspectRatio="none">
              <path d="M0 48 C72 78 130 14 210 50 C290 84 350 10 430 48 C510 82 558 22 600 45 V90 H0 Z" />
            </svg>
            <span className="ocean-bubble bubble-one" />
            <span className="ocean-bubble bubble-two" />
            <span className="ocean-bubble bubble-three" />
          </div>
          <div className="panel-heading group-heading">
            <div className="person-block">
              <div className="avatar group-avatar" aria-hidden="true"><Users size={20} /></div>
              <div>
                <span className="eyebrow">Shared conversation</span>
                <h2 id="group-title">Science team</h2>
              </div>
            </div>
            <div className="group-faces" aria-label={`${activeStudent.name}, Jordan, and two classmates are here`}>
              <span className="face face-one">{activeStudent.avatarInitial}</span><span className="face face-two">J</span><span className="face face-three">A</span><span className="face-count">+1</span>
            </div>
          </div>

          <div className="chat-feed" aria-live="polite">
            <div className="day-divider"><span>Today · Science Lab</span></div>
            {session.messages.map((message) =>
              message.sender === 'system' ? (
                <div className="system-message" key={message.id}><Sparkles size={15} /><span>{message.text}</span></div>
              ) : (
                <article className={`chat-row ${message.sender}`} key={message.id}>
                  <div className={`message-avatar ${message.sender === 'student' ? 'student-message-avatar' : ''}`} aria-hidden="true">
                    {message.author.charAt(0)}
                  </div>
                  <div className="message-stack">
                    <div className="message-meta"><strong>{message.author}</strong><time>{message.time}</time></div>
                    {message.expandedFrom && (
                      <div className="expansion-badge">
                        <Sparkles size={12} />
                        <span>Expanded from AAC:</span>
                        {message.expandedFrom.map((id) => (
                          <span className="expansion-token" key={id}>
                            <AacIcon id={id} size={12} /> {iconById(id).label}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="message-bubble"><span>{message.text}</span></div>
                    {message.sender === 'student' && (
                      <div className="message-foot">
                        <span className="spoken-label"><Volume2 size={13} /> Spoken aloud</span>
                        {message.source && <SourcePill source={message.source} />}
                      </div>
                    )}
                  </div>
                </article>
              ),
            )}
          </div>

          <div className="peer-composer">
            <div className="composer-tip"><MessageCircleHeart size={15} /><span>Keep it clear, kind, and one step at a time.</span></div>
            <div className="composer-box">
              <textarea
                ref={composerRef}
                value={session.peerText}
                onChange={(event) => updateSession({ peerText: event.target.value })}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    void sendPeerMessage()
                  }
                }}
                placeholder="Type a message to the group…"
                rows={2}
                aria-label="Message the group"
              />
              <div className="composer-actions">
                <div className="mic-wrap">
                  <button
                    className={`mic-button ${isListening ? 'listening' : ''}`}
                    type="button"
                    onClick={toggleVoiceInput}
                    aria-pressed={isListening}
                    aria-label={isListening ? 'Stop voice input' : 'Speak your message'}
                  >
                    <Mic size={19} />
                  </button>
                  <span>{isListening ? 'Listening…' : 'Speak'}</span>
                </div>
                <button className="send-button" onClick={sendPeerMessage} disabled={!session.peerText.trim() || isSimplifying}>
                  <span>{isSimplifying ? 'Sending…' : 'Send'}</span><Send size={18} />
                </button>
              </div>
            </div>
            <p className="composer-hint">Press Enter to send · Shift + Enter for a new line</p>
          </div>
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
              <div><span>1</span><p><strong>{activeStudent.name} chooses ideas</strong> using familiar communication cards.</p></div>
              <div><span>2</span><p><strong>Pebble offers natural phrases.</strong> {activeStudent.name} decides which one sounds right.</p></div>
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
