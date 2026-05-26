import axios from 'axios'
import { getSession, signOut } from 'next-auth/react'
import type { Document, CursorPage, DocumentFilters, ChatMessage, Stats, ActivityData } from '@/types'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({ baseURL: `${BASE_URL}/api/v1` })

api.interceptors.request.use(async (config) => {
  const session = await getSession()
  if (session?.accessToken) {
    config.headers.Authorization = `Bearer ${session.accessToken}`
  }
  return config
})

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    if (err.response?.status === 401) await signOut({ callbackUrl: '/login' })
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function loginRequest(email: string, password: string) {
  const { data } = await axios.post(`${BASE_URL}/api/v1/auth/login`, { email, password })
  return data as { access_token: string; refresh_token: string; token_type: string }
}

export async function registerRequest(email: string, password: string) {
  const { data } = await axios.post(`${BASE_URL}/api/v1/auth/register`, { email, password })
  return data
}

export async function getMeRequest(token: string) {
  const { data } = await axios.get(`${BASE_URL}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return data
}

// ── Documents ─────────────────────────────────────────────────────────────────
export async function fetchDocuments(
  filters: DocumentFilters & { cursor?: string; limit?: number }
): Promise<CursorPage<Document>> {
  const { data } = await api.get('/documents', { params: filters })
  return data
}

export async function fetchDocument(id: number): Promise<Document> {
  const { data } = await api.get(`/documents/${id}`)
  return data
}

export async function fetchDocumentStatus(id: number) {
  const { data } = await api.get(`/documents/${id}/status`)
  return data
}

export async function uploadDocument(file: File): Promise<Document> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function deleteDocument(id: number): Promise<void> {
  await api.delete(`/documents/${id}`)
}

// ── Reports ───────────────────────────────────────────────────────────────────
export async function exportReport(id: number, format: 'excel' | 'pdf' | 'json') {
  const endpoint =
    format === 'excel' ? `/reports/${id}/export/excel`
    : format === 'pdf'   ? `/reports/${id}/export/pdf`
    :                      `/reports/${id}/export/json`
  const { data } = await api.get(endpoint, { responseType: format === 'json' ? 'json' : 'blob' })
  return data
}

/**
 * Normalises the backend stats response into the shape the UI expects.
 * Backend returns: total_documents, done, failed, pending, by_file_type
 * Frontend expects: total, done, failed, pending, processing, by_type, avg_pages
 */
export async function fetchStats(): Promise<Stats> {
  const { data } = await api.get('/reports/stats/summary')
  return {
    total:      data.total_documents  ?? data.total      ?? 0,
    done:       data.done             ?? 0,
    pending:    data.pending          ?? 0,
    processing: data.processing       ?? 0,
    failed:     data.failed           ?? 0,
    by_type:    data.by_file_type     ?? data.by_type    ?? {},
    avg_pages:  data.avg_pages        ?? 0,
  }
}

/**
 * Fetches per-day document activity for the last `days` days.
 * Falls back to a synthesised empty dataset if the endpoint doesn't exist yet.
 */
export async function fetchActivity(days = 14): Promise<ActivityData> {
  try {
    const { data } = await api.get('/reports/stats/activity', { params: { days } })
    return data as ActivityData
  } catch {
    // Endpoint not yet implemented — return empty data so the chart renders gracefully
    return { points: [], total: 0, days }
  }
}

// ── Chat ──────────────────────────────────────────────────────────────────────
export async function sendChatMessage(
  docId: number,
  message: string,
  conversationId?: string
): Promise<{ answer: string; conversation_id: string; history: ChatMessage[] }> {
  const { data } = await api.post(`/documents/${docId}/chat`, {
    message,
    conversation_id: conversationId,
  })
  return data
}

export async function fetchChatHistory(
  docId: number,
  conversationId: string
): Promise<{ conversation_id: string; history: ChatMessage[] }> {
  const { data } = await api.get(`/documents/${docId}/chat/${conversationId}`)
  return data
}
