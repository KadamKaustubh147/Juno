import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { fetchMessages, fetchSessions, streamChat, type ChatMsg, type SessionSummary } from './api'

// Tight variants of the default markdown elements -- the browser/prose defaults add
// margins sized for full documents, which looks wrong inside a compact chat bubble.
const markdownComponents = {
  p: ({ ...props }) => <p className="[&:not(:last-child)]:mb-2" {...props} />,
  ul: ({ ...props }) => <ul className="mb-2 list-disc pl-5 last:mb-0" {...props} />,
  ol: ({ ...props }) => <ol className="mb-2 list-decimal pl-5 last:mb-0" {...props} />,
  li: ({ ...props }) => <li className="mb-0.5" {...props} />,
  a: ({ ...props }) => <a className="underline" target="_blank" rel="noreferrer" {...props} />,
  code: ({ ...props }) => <code className="rounded bg-black/10 px-1 py-0.5 text-[0.9em]" {...props} />,
  pre: ({ ...props }) => (
    <pre className="mb-2 overflow-x-auto rounded-lg bg-black/10 p-2 text-[0.9em] last:mb-0" {...props} />
  ),
}

// ponytail: single local user until auth exists
const USER_ID = 'kaustubh'

function App() {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [draft, setDraft] = useState('')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  // id of the thread being viewed; mirrors threadId.current for rendering
  // (refs can't be read during render)
  const [activeThread, setActiveThread] = useState<string | null>(
    new URLSearchParams(window.location.search).get('thread'),
  )

  // Existing chat restores via ?thread=<id>; a new chat gets its id on first send.
  const threadId = useRef<string | null>(activeThread)
  const scrollRef = useRef<HTMLDivElement>(null)
  // scrollHeight of the list before older messages are prepended; used to keep
  // the viewport anchored on the same messages after they shift down.
  const anchorScroll = useRef<number | null>(null)
  // ref guard: onScroll fires faster than React state updates
  const busy = useRef(false)

  useEffect(() => {
    fetchSessions(USER_ID)
      .then((res) => setSessions(res.sessions))
      .catch(() => {})
    const tid = threadId.current
    if (!tid) return
    fetchMessages(tid)
      .then((res) => {
        setMessages(res.messages)
        setHasMore(res.has_more)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (anchorScroll.current === null || !scrollRef.current) return
    const el = scrollRef.current
    el.scrollTop = el.scrollHeight - anchorScroll.current
    anchorScroll.current = null
  }, [messages])

  const loadOlder = async () => {
    const tid = threadId.current
    if (!tid || !hasMore || busy.current) return
    busy.current = true
    setLoadingOlder(true)
    try {
      const res = await fetchMessages(tid, messages[0]?.id)
      anchorScroll.current = scrollRef.current?.scrollHeight ?? null
      setMessages((m) => [...res.messages, ...m])
      setHasMore(res.has_more)
    } catch {
      // leave hasMore true so scrolling can retry
    } finally {
      busy.current = false
      setLoadingOlder(false)
    }
  }

  const onScroll = () => {
    if (scrollRef.current && scrollRef.current.scrollTop < 80) loadOlder()
  }

  const newSession = () => {
    if (streaming) return
    threadId.current = null
    setActiveThread(null)
    setMessages([])
    setHasMore(false)
    setDraft('')
    // drop ?thread= so a refresh doesn't restore the old chat
    window.history.replaceState(null, '', window.location.pathname)
  }

  const openSession = (tid: string) => {
    if (streaming || tid === threadId.current) return
    threadId.current = tid
    setActiveThread(tid)
    setMessages([])
    setHasMore(false)
    window.history.replaceState(null, '', `?thread=${tid}`)
    fetchMessages(tid)
      .then((res) => {
        setMessages(res.messages)
        setHasMore(res.has_more)
      })
      .catch(() => {})
  }

  const send = async () => {
    const text = draft.trim()
    if (!text || streaming) return
    if (!threadId.current) {
      threadId.current = crypto.randomUUID()
      setActiveThread(threadId.current)
      // persist the id so a refresh restores this session
      window.history.replaceState(null, '', `?thread=${threadId.current}`)
    }

    const sentAt = Date.now()
    setMessages((m) => [
      ...m,
      { id: sentAt, role: 'user', content: text },
      { id: sentAt + 1, role: 'assistant', content: '' },
    ])
    setDraft('')
    setStreaming(true)
    requestAnimationFrame(() =>
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }),
    )
    try {
      await streamChat(threadId.current, USER_ID, text, (token) => {
        setMessages((m) => {
          const last = m[m.length - 1]
          if (last.role !== 'assistant') return m
          return [...m.slice(0, -1), { ...last, content: last.content + token }]
        })
      })
    } catch {
      setMessages((m) => {
        const last = m[m.length - 1]
        if (last.role === 'assistant' && !last.content) {
          return [...m.slice(0, -1), { ...last, content: '(connection lost)' }]
        }
        return m
      })
    } finally {
      setStreaming(false)
      fetchSessions(USER_ID)
        .then((res) => setSessions(res.sessions))
        .catch(() => {})
    }
  }

  return (
    <div className="flex h-svh bg-cream-dark">
      {/* Sidebar */}
      <aside className="flex w-64 shrink-0 flex-col gap-5 border-r border-line bg-cream p-5">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-full bg-sage-avatar text-sm text-sage">
            K
          </span>
          <span className="font-semibold text-ink">Kaustubh</span>
        </div>
        <button
          onClick={newSession}
          className="rounded-[10px] bg-sage py-3 text-sm font-semibold text-cream hover:bg-sage-dark"
        >
          Start a session
        </button>
        <div className="text-[11px] uppercase tracking-widest text-muted">This month</div>
        <ul className="flex flex-col gap-1.5">
          {sessions.length === 0 && !activeThread && (
            <li className="px-3 text-xs text-muted">No sessions yet</li>
          )}
          {sessions.map((s) => (
            <li key={s.thread_id}>
              <button
                onClick={() => openSession(s.thread_id)}
                className={`w-full rounded-lg px-3 py-2 text-left text-[13px] hover:bg-cream-dark ${
                  s.thread_id === activeThread ? 'bg-cream-dark text-ink' : 'text-ink/70'
                }`}
              >
                <span className="block truncate">Session</span>
                <span className="block text-[11px] text-muted">
                  {new Date(s.last_at).toLocaleDateString()}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {/* Chat */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-line px-6 py-3.5">
          <div className="flex items-baseline gap-2">
            <strong className="text-sm text-ink">Session</strong>
            <span className="text-[13px] text-muted">text</span>
          </div>
          <button className="rounded-full border border-line bg-cream px-3.5 py-1.5 text-[13px] text-ink/70">
            English <span className="text-[10px] text-muted">▾</span>
          </button>
        </header>

        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto p-6">
          {/* justify-end lives on this inner wrapper, not the scrollable div itself --
              justify-content other than flex-start on an overflowing flex container
              clips the start-side overflow instead of making it scrollable (a real
              Chromium/Firefox quirk, not a spec requirement -- see "safe alignment").
              min-h-full keeps short conversations bottom-anchored without that bug. */}
          <div className="flex min-h-full flex-col justify-end gap-2.5">
            {loadingOlder && <div className="text-center text-xs text-muted">Loading…</div>}
            {hasMore && !loadingOlder && (
              <button onClick={loadOlder} className="mx-auto text-xs text-muted hover:text-ink">
                Load earlier messages
              </button>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[62%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${
                    m.role === 'assistant'
                      ? 'rounded-tl-md bg-sage-light font-serif text-sage-dark'
                      : 'rounded-tr-md bg-white text-ink shadow-sm'
                  }`}
                >
                  {m.role === 'assistant' ? (
                    m.content ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                        {m.content}
                      </ReactMarkdown>
                    ) : (
                      streaming && '…'
                    )
                  ) : (
                    m.content
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <footer className="flex gap-2.5 border-t border-line px-6 pt-4 pb-5">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Type a message"
            className="flex-1 rounded-full bg-cream px-5 py-3.5 text-sm text-ink outline-none placeholder:text-muted"
          />
          <button
            onClick={send}
            aria-label="Send"
            className="size-[46px] shrink-0 rounded-full bg-sage text-lg text-cream hover:bg-sage-dark"
          >
            ↑
          </button>
        </footer>
      </main>
    </div>
  )
}

export default App
