import { useLayoutEffect, useRef } from 'react'
import type { ChatMsg } from '../../../api'
import { MessageBubble } from './MessageBubble'

type Props = {
  messages: ChatMsg[]
  hasMore: boolean
  loadingOlder: boolean
  streaming: boolean
  onLoadOlder: () => void
}

export function MessageList({ messages, hasMore, loadingOlder, streaming, onLoadOlder }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  // what the list looked like after the previous update, to work out what changed
  const prev = useRef<{ firstId?: ChatMsg['id']; lastId?: ChatMsg['id']; height: number }>({ height: 0 })

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const { firstId: prevFirst, lastId: prevLast, height: prevHeight } = prev.current
    const firstId = messages[0]?.id
    const lastId = messages[messages.length - 1]?.id

    const prepended =
      prevFirst !== undefined && firstId !== prevFirst && messages.some((m) => m.id === prevFirst)
    // was the viewport at the bottom before this update grew the list?
    const wasAtBottom = prevHeight - el.scrollTop - el.clientHeight < 80

    if (prepended) {
      // older messages shifted the content down: keep the viewport on the same messages
      el.scrollTop += el.scrollHeight - prevHeight
    } else if (firstId !== prevFirst || lastId !== prevLast || wasAtBottom) {
      // thread opened/switched, message sent, or a streaming reply growing while the reader is at the bottom
      el.scrollTop = el.scrollHeight
    }
    prev.current = { firstId, lastId, height: el.scrollHeight }
  }, [messages])

  const onScroll = () => {
    if (scrollRef.current && scrollRef.current.scrollTop < 80) onLoadOlder()
  }

  return (
    <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto p-4 md:p-6">
      {/* justify-end lives on this inner wrapper, not the scrollable div itself --
          justify-content other than flex-start on an overflowing flex container
          clips the start-side overflow instead of making it scrollable (a real
          Chromium/Firefox quirk, not a spec requirement -- see "safe alignment").
          min-h-full keeps short conversations bottom-anchored without that bug. */}
      <div className="flex min-h-full flex-col justify-end gap-2.5">
        {loadingOlder && <div className="text-center text-xs text-muted">Loading…</div>}
        {hasMore && !loadingOlder && (
          <button onClick={onLoadOlder} className="mx-auto text-xs text-muted hover:text-ink">
            Load earlier messages
          </button>
        )}
        {messages.length === 0 && (
          <p className="my-auto text-center font-serif text-lg text-muted">
            Say hello whenever you&rsquo;re ready.
          </p>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} role={m.role} content={m.content} pending={streaming} />
        ))}
      </div>
    </div>
  )
}
