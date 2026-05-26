export interface User {
  id: string
  email: string
  role: 'user' | 'admin'
  plan: 'free' | 'pro' | 'enterprise'
  created_at: string
}

export interface Document {
  id: number
  filename: string
  file_type: 'pdf' | 'docx' | 'xlsx'
  file_size: number
  status: 'pending' | 'processing' | 'done' | 'failed'
  task_id?: string
  summary?: string
  sentiment?: string
  keywords?: string[]
  entities?: Record<string, string[]>
  page_count?: number
  extracted_text?: string
  extracted_text_snippet?: string
  doc_category?: string
  error_message?: string
  created_at: string
  updated_at: string
}

export interface CursorPage<T> {
  items: T[]
  next_cursor: string | null
  prev_cursor: string | null
  total: number
  page_size: number
}

export interface DocumentFilters {
  status?: string
  file_type?: string
  fecha_desde?: string
  fecha_hasta?: string
  search?: string
  order_by?: string
  order_dir?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface Stats {
  total: number
  done: number
  pending: number
  processing: number
  failed: number
  by_type: Record<string, number>
  avg_pages: number
}

export interface ActivityPoint {
  date: string
  count: number
  label: string
}

export interface ActivityData {
  points: ActivityPoint[]
  total: number
  days: number
}
