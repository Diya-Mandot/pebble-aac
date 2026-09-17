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
import { expandMessage, simplifyMessage } from './api'
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
  const [selectedIcons, setSelectedIcons] = useState<IconId[]>([])
  const [context, setContext] = useState(contexts[0].value)
  const [feeling, setFeeling] = useState(feelings[0].label)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [candidateSource, setCandidateSource] = useState<ResponseSource | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [isExpanding, setIsExpanding] = useState(false)
  const [peerText, setPeerText] = useState('')
  const [isSimplifying, setIsSimplifying] = useState(false)
  const [simplified, setSimplified] = useState<SimplifyResponse | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const [notice, setNotice] = useState<string | null>(null)
  const [showHelp, setShowHelp] = useState(false)
  const [activeMobilePanel, setActiveMobilePanel] = useState<'student' | 'group'>('student')
  const composerRef = useRef<HTMLTextAreaElement>(null)

  const selectedDefinitions = useMemo(
    () => selectedIcons.map((id) => iconById(id)),
    [selectedIcons],
  )

  const toggleIcon = (id: IconId) => {
    setCandidates([])
    setCandidateSource(null)
    setSelectedIcons((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id)
      return [...current, id]
    })
  }

  const makeMessage = async () => {
    if (!selectedIcons.length) return
    setIsExpanding(true)
    setCandidates([])
    const response = await expandMessage(selectedIcons, context)
    setCandidates(response.candidates)
    setCandidateSource(response.source)
    setIsExpanding(false)
  }

  const approveCandidate = (candidate: Candidate) => {
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        sender: 'student',
        author: 'Maya',
        text: candidate.text,
        time: timeNow(),
        source: candidateSource ?? undefined,
        expandedFrom: [...selectedIcons],
      },
    ])
    setSelectedIcons([])
    setCandidates([])
    setCandidateSource(null)
    setActiveMobilePanel('group')
    setNotice('Your message was shared with the group.')
    window.setTimeout(() => setNotice(null), 3200)

    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(candidate.text)
      utterance.rate = 0.94
      window.speechSynthesis.speak(utterance)
    }
  }

  const sendPeerMessage = async () => {
    const text = peerText.trim()
    if (!text || isSimplifying) return

    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        sender: 'peer',
        author: 'Jordan',
        text,
        time: timeNow(),
      },
    ])
    setPeerText('')
    setIsSimplifying(true)
    setActiveMobilePanel('student')
    const response = await simplifyMessage(text)
    setSimplified(response)
    setIsSimplifying(false)
  }

  const sendQuickReply = (reply: QuickReplyId) => {
    const text = reply === 'DONE' ? "I'm done!" : 'I still need some help.'
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        sender: 'student',
        author: 'Maya',
        text,
        time: timeNow(),
      },
    ])
    setNotice('Your reply was shared.')
    setActiveMobilePanel('group')
    window.setTimeout(() => setNotice(null), 2800)
  }

  const resetDemo = () => {
    setSelectedIcons([])
    setCandidates([])
    setCandidateSource(null)
    setSimplified(null)
    setMessages(initialMessages)
    setPeerText('')
    setFeeling(feelings[0].label)
    setContext(contexts[0].value)
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

      <main className="workspace">
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
              <div className="avatar student-avatar" aria-hidden="true">M</div>
              <div>
                <span className="eyebrow">AAC workspace</span>
                <h1 id="student-title">Maya’s voice</h1>
              </div>
            </div>
            <div className="take-time"><Clock3 size={15} /> Take your time</div>
          </div>

          <div className="student-scroll">
            {(isSimplifying || simplified) && (
              <section className="incoming-card" aria-live="polite" aria-busy={isSimplifying}>
                {isSimplifying ? (
                  <div className="thinking-state">
                    <div className="thinking-orb"><Sparkles size={22} /></div>
                    <div><strong>Making that easier to follow…</strong><span>Finding the important steps</span></div>
                  </div>
                ) : simplified?.status === 'please_repeat' ? (
                  <div className="repeat-state">
                    <span className="repeat-symbol"><Ear size={27} /></span>
                    <div>
                      <span className="eyebrow">Let’s try that again</span>
                      <h2>I didn’t catch enough to be sure.</h2>
                      <p>Ask your teammate to say it another way.</p>
                      {simplified.source && <SourcePill source={simplified.source} />}
                    </div>
                  </div>
                ) : simplified ? (
                  <>
                    <div className="incoming-header">
                      <div>
                        <span className="eyebrow">Jordan shared a plan</span>
                        <h2>Here’s what to do</h2>
                      </div>
                      <SourcePill source={simplified.source} />
                    </div>
                    <ol className="step-list">
                      {simplified.steps.map((step, index) => (
                        <li key={`${step.label}-${index}`}>
                          <span className="step-number">{index + 1}</span>
                          <MiniIcons ids={step.icons} />
                          <strong>{step.label}</strong>
                        </li>
                      ))}
                    </ol>
                    {simplified.warnings.map((warning, index) => (
                      <div className="warning-card" key={`${warning.label}-${index}`}>
                        <MiniIcons ids={warning.icons} />
                        <span><small>Important check</small><strong>{warning.label}</strong></span>
                      </div>
                    ))}
                    <div className="quick-replies">
                      <span>Ready to answer?</span>
                      <div>
                        {simplified.quickReplies.map((reply) => (
                          <button key={reply} onClick={() => sendQuickReply(reply)} className={reply === 'DONE' ? 'reply-done' : 'reply-help'}>
                            {reply === 'DONE' ? <><Check size={15} /> Done</> : <><HandHelping size={15} /> Need help</>}
                          </button>
                        ))}
                      </div>
                    </div>
                    <button className="transcript-toggle" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
                      <ChevronDown size={17} /> {expanded ? 'Hide' : 'Show'} exactly what Jordan said
                    </button>
                    {expanded && <blockquote className="transcript">“{simplified.transcript}”</blockquote>}
                  </>
                ) : null}
              </section>
            )}

            <section className="setup-row" aria-label="Conversation settings">
              <label>
                <span>We’re working on</span>
                <div className="select-wrap">
                  <select value={context} onChange={(event) => setContext(event.target.value)}>
                    {contexts.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                  <ChevronDown size={17} />
                </div>
              </label>
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
                <span className="selection-count">{selectedIcons.length} selected</span>
              </div>

              <div className="aac-grid">
                {ICONS.map((item) => {
                  const selectedIndex = selectedIcons.indexOf(item.id)
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
            <div className={`selection-tray ${selectedIcons.length ? 'has-items' : ''}`} aria-live="polite">
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
                  <button className="clear-button" onClick={() => setSelectedIcons([])} aria-label="Clear all selections"><Trash2 size={17} /></button>
                </>
              ) : (
                <span className="tray-placeholder"><MousePointerClick size={17} /> Tap a card to begin your message</span>
              )}
            </div>
            <button className="primary-button" onClick={makeMessage} disabled={!selectedIcons.length || isExpanding}>
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
                    <button key={candidate.id} onClick={() => approveCandidate(candidate)}>
                      <span className="candidate-number">{index + 1}</span>
                      <span>{candidate.text}</span>
                      <span className="choose-label">Choose <ArrowRight size={16} /></span>
                    </button>
                  ))}
                </div>
                <p className="privacy-note"><Info size={14} /> Pebble offers choices. You decide what represents you.</p>
              </section>
            </div>
          )}
        </section>

        <section className={`panel group-panel ${activeMobilePanel === 'group' ? 'mobile-active' : ''}`} aria-labelledby="group-title">
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
            <div className="group-faces" aria-label="Maya, Jordan, and two classmates are here">
              <span className="face face-one">M</span><span className="face face-two">J</span><span className="face face-three">A</span><span className="face-count">+1</span>
            </div>
          </div>

          <div className="chat-feed" aria-live="polite">
            <div className="day-divider"><span>Today · Science Lab</span></div>
            {messages.map((message) =>
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
                value={peerText}
                onChange={(event) => setPeerText(event.target.value)}
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
                  <button className="mic-button" type="button" onClick={() => setNotice('Voice notes are coming next. Type your message for now.')} aria-label="Record a voice note">
                    <Mic size={19} />
                  </button>
                  <span>Voice note</span>
                </div>
                <button className="send-button" onClick={sendPeerMessage} disabled={!peerText.trim() || isSimplifying}>
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
