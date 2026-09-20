import { useEffect, useRef, useState } from 'react'
import { createSession, fetchMessages, streamChat, type ChatMsg } from '../../../api'

// Optimistic messages get a temporary id until the server reports the real one.
const LOCAL = 'local-'
const isLocal = (m: ChatMsg) => m.id.startsWith(LOCAL)

const REPLY_FAILED = 'Something went wrong getting a reply. Try sending your message again.'

/**
 * The open conversation: its messages, scrollback pagination and the streamed reply.
 * The active session lives in the URL (?thread=<id>) so a refresh restores it. A new chat has
 * no session yet -- it is created on the first send, so an abandoned "Start a session" leaves
 * no empty row behind.
 */
export function useChat() {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [streaming, setStreaming] = useState(false)
  // the server said the script has finished; sending more would just get an empty reply
  const [sessionDone, setSessionDone] = useState(false)
  // id of the session being viewed; mirrors threadId.current for rendering
  // (refs can't be read during render)
  const [activeThread, setActiveThread] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get('thread'),
  )

  const threadId = useRef<string | null>(activeThread)
  // ref guard: onScroll fires faster than React state updates
  const busy = useRef(false)

  useEffect(() => {
    const tid = threadId.current
    if (!tid) return
    fetchMessages(tid)
      .then((res) => {
        setMessages(res.messages)
        setHasMore(res.has_more)
      })
      .catch(() => {})
  }, [])

  const loadOlder = async () => {
    const tid = threadId.current
    const oldest = messages.find((m) => !isLocal(m))
    if (!tid || !hasMore || busy.current) return
    busy.current = true
    setLoadingOlder(true)
    try {
      const res = await fetchMessages(tid, oldest?.id)
      setMessages((m) => [...res.messages, ...m])
      setHasMore(res.has_more)
    } catch {
      // leave hasMore true so scrolling can retry
    } finally {
      busy.current = false
      setLoadingOlder(false)
    }
  }

  const newSession = () => {
    if (streaming) return
    threadId.current = null
    setActiveThread(null)
    setMessages([])
    setHasMore(false)
    setSessionDone(false)
    // drop ?thread= so a refresh doesn't restore the old chat
    window.history.replaceState(null, '', window.location.pathname)
  }

  const openSession = (tid: string) => {
    if (streaming || tid === threadId.current) return
    threadId.current = tid
    setActiveThread(tid)
    setMessages([])
    setHasMore(false)
    setSessionDone(false)
    window.history.replaceState(null, '', `?thread=${tid}`)
    fetchMessages(tid)
      .then((res) => {
        setMessages(res.messages)
        setHasMore(res.has_more)
      })
      .catch(() => {})
  }

  const send = async (text: string) => {
    if (!text || streaming || sessionDone) return

    const stamp = Date.now()
    const localUserId = `${LOCAL}${stamp}`
    setMessages((m) => [
      ...m,
      { id: localUserId, role: 'user', content: text },
      { id: `${LOCAL}${stamp}-reply`, role: 'assistant', content: '' },
    ])
    setStreaming(true)

    // replace an empty reply bubble with an error note; a partial reply is left as it is
    const failReply = () =>
      setMessages((m) => {
        const last = m[m.length - 1]
        if (last.role === 'assistant' && !last.content) {
          return [...m.slice(0, -1), { ...last, content: REPLY_FAILED }]
        }
        return m
      })

    try {
      let tid = threadId.current
      if (!tid) {
        tid = (await createSession()).id
        threadId.current = tid
        setActiveThread(tid)
        // persist the id so a refresh restores this session
        window.history.replaceState(null, '', `?thread=${tid}`)
      }

      await streamChat(tid, text, {
        onStart: (userMessageId) =>
          setMessages((m) => m.map((x) => (x.id === localUserId ? { ...x, id: userMessageId } : x))),
        onToken: (token) =>
          setMessages((m) => {
            const last = m[m.length - 1]
            if (last.role !== 'assistant') return m
            return [...m.slice(0, -1), { ...last, content: last.content + token }]
          }),
        onDone: ({ messageId, sessionDone: done }) => {
          setSessionDone(done)
          setMessages((m) => {
            const last = m[m.length - 1]
            if (last.role !== 'assistant') return m
            // no reply id means the session had already ended and there is no reply to show
            if (messageId === null) return m.slice(0, -1)
            return [...m.slice(0, -1), { ...last, id: messageId }]
          })
        },
        onError: failReply,
      })
    } catch {
      failReply()
    } finally {
      setStreaming(false)
    }
  }

  return {
    messages,
    hasMore,
    loadingOlder,
    streaming,
    sessionDone,
    activeThread,
    send,
    newSession,
    openSession,
    loadOlder,
  }
}
