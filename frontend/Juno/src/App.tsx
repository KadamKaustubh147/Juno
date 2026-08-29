import { useEffect, useRef, useState } from 'react'
import { fetchMessages, streamChat, type ChatMsg } from './api'

// ponytail: single local user until auth exists
const USER_ID = 'kaustubh'

function App() {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [draft, setDraft] = useState('')
  // mirrors threadId.current for rendering (refs can't be read during render)
  const [hasThread, setHasThread] = useState(false)

  // Existing chat restores via ?thread=<id>; a new chat gets its id on first send.
  const threadId = useRef<string | null>(
    new URLSearchParams(window.location.search).get('thread'),
  )
  const scrollRef = useRef<HTMLDivElement>(null)
  // scrollHeight of the list before older messages are prepended; used to keep
  // the viewport anchored on the same messages after they shift down.
  const anchorScroll = useRef<number | null>(null)
  // ref guard: onScroll fires faster than React state updates
  const busy = useRef(false)

  useEffect(() => {
    const tid = threadId.current
    if (!tid) return
    setHasThread(true)
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

  const send = async () => {
    const text = draft.trim()
    if (!text || streaming) return
    if (!threadId.current) {
      threadId.current = crypto.randomUUID()
      setHasThread(true)
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
        <button className="rounded-[10px] bg-sage py-3 text-sm font-semibold text-cream hover:bg-sage-dark">
          Start a session
        </button>
        <div className="text-[11px] uppercase tracking-widest text-muted">This month</div>
        <ul className="flex flex-col gap-1.5">
          {!hasThread && (
            <li className="px-3 text-xs text-muted">No sessions yet</li>
          )}
        </ul>
        <nav className="mt-auto flex flex-col gap-2">
          <a href="#" className="text-[13px] text-ink/60 hover:text-ink">
            Journal
          </a>
          <a href="#" className="text-[13px] text-ink/60 hover:text-ink">
            Exercises
          </a>
          <a href="#" className="text-[13px] text-ink/60 hover:text-ink">
            Privacy &amp; access
          </a>
        </nav>
      </aside>

      {/* Chat */}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-line px-6 py-3.5">
          <div className="flex items-baseline gap-2">
            <strong className="text-sm text-ink">Session</strong>
            <span className="text-[13px] text-muted">text</span>
          </div>
          <button className="rounded-full border border-line bg-cream px-3.5 py-1.5 text-[13px] text-ink/70">
            English <span className="text-[10px] text-muted">▾</span>
          </button>
        </header>

        <div ref={scrollRef} onScroll={onScroll} className="flex flex-1 flex-col justify-end gap-2.5 overflow-y-auto p-6">
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
                {m.content || (streaming ? '…' : '')}
              </div>
            </div>
          ))}
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
