export type ChatMsg = {
  id: number
  role: 'user' | 'assistant'
  content: string
}

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type SessionSummary = {
  thread_id: string
  last_at: string
}

export async function fetchSessions(userId: string) {
  const url = new URL(`${BASE}/sessions`)
  url.searchParams.set('user_id', userId)
  const res = await fetch(url)
  if (!res.ok) throw new Error(`fetchSessions failed: ${res.status}`)
  return (await res.json()) as { sessions: SessionSummary[] }
}

export async function fetchMessages(threadId: string, before?: number) {
  const url = new URL(`${BASE}/messages`)
  url.searchParams.set('thread_id', threadId)
  url.searchParams.set('limit', '20')
  if (before !== undefined) url.searchParams.set('before', String(before))
  const res = await fetch(url)
  if (!res.ok) throw new Error(`fetchMessages failed: ${res.status}`)
  return (await res.json()) as { messages: ChatMsg[]; has_more: boolean }
}

export async function streamChat(
  threadId: string,
  userId: string,
  text: string,
  onToken: (token: string) => void,
) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, user_id: userId, message: text }),
  })
  if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onToken(decoder.decode(value, { stream: true }))
  }
}
