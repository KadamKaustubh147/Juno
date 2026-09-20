// The whole API client. Every route except /auth/* needs `Authorization: Bearer <jwt>`; the server
// takes the user from the token, so nothing here sends a user id.

export type ChatMsg = {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export type SessionSummary = {
  id: string
  status: 'active' | 'completed' | 'abandoned'
  script_id: string
  current_section: string
  created_at: string
  ended_at: string | null
  last_at: string
}

export type User = {
  id: string
  email: string
  full_name: string | null
  created_at: string
}

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// --- auth ---------------------------------------------------------------------------------
// The access token never expires (there are no refresh tokens), so it just sits in
// localStorage until the user logs out or the server stops accepting it.

const TOKEN_KEY = 'juno_token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage blocked: the session just won't survive a reload
  }
}

export function logout() {
  setToken(null)
}

// Called when the server rejects our token (401), so the UI can fall back to the login screen.
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const { detail } = await res.json()
    if (typeof detail === 'string') return detail
    // FastAPI validation errors: a list of {msg, loc, ...}
    if (Array.isArray(detail)) return detail.map((d: { msg: string }) => d.msg).join('; ')
  } catch {
    // not JSON
  }
  return `request failed (${res.status})`
}

async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body) headers.set('Content-Type', 'application/json')

  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  // only a rejected *token* means "signed out" -- a wrong password on /auth/login is also a 401
  if (res.status === 401 && token) {
    setToken(null)
    onUnauthorized?.()
  }
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  return res
}

type AuthResponse = { access_token: string; token_type: string; user: User }

async function authenticate(path: string, body: object) {
  const res = await apiFetch(path, { method: 'POST', body: JSON.stringify(body) })
  const { access_token, user } = (await res.json()) as AuthResponse
  setToken(access_token)
  return user
}

export const login = (email: string, password: string) =>
  authenticate('/auth/login', { email, password })

export const register = (email: string, password: string, fullName?: string) =>
  authenticate('/auth/register', { email, password, full_name: fullName || null })

export async function fetchMe() {
  return (await (await apiFetch('/users/me')).json()) as User
}

// --- sessions -----------------------------------------------------------------------------

export async function createSession() {
  const res = await apiFetch('/sessions', { method: 'POST' })
  return (await res.json()) as SessionSummary
}

export async function fetchSessions() {
  const res = await apiFetch('/sessions')
  return (await res.json()) as { sessions: SessionSummary[] }
}

export async function fetchMessages(sessionId: string, before?: string) {
  const params = new URLSearchParams({ limit: '20' })
  if (before !== undefined) params.set('before', before)
  const res = await apiFetch(`/sessions/${sessionId}/messages?${params}`)
  return (await res.json()) as { messages: ChatMsg[]; has_more: boolean }
}

// --- chat ---------------------------------------------------------------------------------

export type ChatHandlers = {
  /** The user's message is saved server-side; `userMessageId` is its real id. */
  onStart?: (userMessageId: string) => void
  /** The session moved to a new script section. */
  onSection?: (from: string, to: string) => void
  onToken: (token: string) => void
  /** The reply is complete and saved. `messageId` is null if there was no reply (session already over). */
  onDone?: (done: { messageId: string | null; currentSection: string; sessionDone: boolean }) => void
  /** The turn failed after streaming began. */
  onError?: (detail: string) => void
}

/**
 * POST /chat and read the reply as Server-Sent Events. EventSource can't POST or send an
 * Authorization header, so this reads the fetch body and parses the frames itself:
 * `event: <name>\ndata: <json>\n\n`.
 */
export async function streamChat(threadId: string, text: string, handlers: ChatHandlers) {
  const res = await apiFetch('/chat', {
    method: 'POST',
    body: JSON.stringify({ thread_id: threadId, message: text }),
  })
  if (!res.body) throw new ApiError(res.status, 'no response body')

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += value
    // frames end with a blank line; keep any trailing partial frame for the next chunk
    for (let end = buffer.indexOf('\n\n'); end !== -1; end = buffer.indexOf('\n\n')) {
      dispatch(buffer.slice(0, end), handlers)
      buffer = buffer.slice(end + 2)
    }
  }
}

function dispatch(frame: string, handlers: ChatHandlers) {
  let event = 'message'
  let data = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice('event: '.length)
    else if (line.startsWith('data: ')) data += line.slice('data: '.length)
  }
  if (!data) return
  const payload = JSON.parse(data)

  switch (event) {
    case 'start':
      handlers.onStart?.(payload.user_message_id)
      break
    case 'section':
      handlers.onSection?.(payload.from, payload.to)
      break
    case 'token':
      handlers.onToken(payload.text)
      break
    case 'done':
      handlers.onDone?.({
        messageId: payload.message_id,
        currentSection: payload.current_section,
        sessionDone: payload.session_done,
      })
      break
    case 'error':
      handlers.onError?.(payload.detail)
      break
  }
}
