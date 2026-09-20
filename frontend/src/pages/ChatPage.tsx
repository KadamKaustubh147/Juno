import { useState } from 'react'
import { useMe } from '../features/auth/useMe'
import { ChatHeader } from '../features/chat/components/ChatHeader'
import { Composer } from '../features/chat/components/Composer'
import { MessageList } from '../features/chat/components/MessageList'
import { Sidebar } from '../features/chat/components/Sidebar'
import { useChat } from '../features/chat/hooks/useChat'
import { useSessions } from '../features/chat/hooks/useSessions'

export function ChatPage({ onLogout }: { onLogout: () => void }) {
  const user = useMe()
  const { sessions, refresh } = useSessions()
  const chat = useChat()
  const [drawerOpen, setDrawerOpen] = useState(false)

  // a finished session: told so just now, or already marked completed when it was opened
  const ended =
    chat.sessionDone || sessions.find((s) => s.id === chat.activeThread)?.status === 'completed'

  const send = async (text: string) => {
    await chat.send(text)
    refresh() // the session now exists (or moved to the top of the list)
  }

  return (
    <div className="flex h-svh bg-cream-dark">
      <Sidebar
        user={user}
        sessions={sessions}
        activeThread={chat.activeThread}
        busy={chat.streaming}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onNewSession={() => {
          chat.newSession()
          setDrawerOpen(false)
        }}
        onOpenSession={(id) => {
          chat.openSession(id)
          setDrawerOpen(false)
        }}
        onLogout={onLogout}
      />

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ChatHeader onMenu={() => setDrawerOpen(true)} />
        <MessageList
          messages={chat.messages}
          hasMore={chat.hasMore}
          loadingOlder={chat.loadingOlder}
          streaming={chat.streaming}
          onLoadOlder={chat.loadOlder}
        />
        <Composer disabled={chat.streaming} ended={ended} onSend={send} />
      </main>
    </div>
  )
}
