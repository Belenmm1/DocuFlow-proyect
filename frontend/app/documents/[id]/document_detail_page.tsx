'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import AuthGuard from '@/components/layout/AuthGuard'
import StatusBadge from '@/components/ui/StatusBadge'
import { Skeleton } from '@/components/ui/Skeleton'
import { fetchDocument, exportReport } from '@/lib/api'
import type { Document } from '@/types'
import {
  ArrowLeft, MessageSquare, Download, FileText,
  BarChart2, Clock, HardDrive, RefreshCw
} from 'lucide-react'
import Link from 'next/link'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

// Poll interval when document is still being processed
const POLL_INTERVAL_MS = 4000

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="df-card p-5">
      <p className="text-xs font-mono uppercase tracking-widest mb-4" style={{ color: 'var(--df-muted)' }}>
        {title}
      </p>
      {children}
    </div>
  )
}

function MetaRow({
  icon: Icon, label, value
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number | undefined
}) {
  if (!value) return null
  return (
    <div className="flex items-start gap-3 py-2.5 border-b last:border-0" style={{ borderColor: 'var(--df-border)' }}>
      <Icon className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: 'var(--df-muted)' }} />
      <div className="flex-1 min-w-0">
        <p className="text-xs mb-0.5" style={{ color: 'var(--df-muted)' }}>{label}</p>
        <p className="text-sm break-all" style={{ color: 'var(--df-text)' }}>{value}</p>
      </div>
    </div>
  )
}

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1048576) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / 1048576).toFixed(1)} MB`
}

const TERMINAL_STATUSES = new Set(['done', 'failed'])

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [doc, setDoc] = useState<Document | null>(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    try {
      const d = await fetchDocument(Number(id))
      setDoc(d)
      return d
    } catch {
      toast.error('Documento no encontrado')
      return null
    } finally {
      setLoading(false)
    }
  }, [id])

  // Polling logic: keep refreshing while status is pending/processing
  const schedulePoll = useCallback((d: Document | null) => {
    if (pollRef.current) clearTimeout(pollRef.current)
    if (!d || TERMINAL_STATUSES.has(d.status)) return
    pollRef.current = setTimeout(async () => {
      const updated = await load()
      schedulePoll(updated)
    }, POLL_INTERVAL_MS)
  }, [load])

  useEffect(() => {
    load().then(schedulePoll)
    return () => { if (pollRef.current) clearTimeout(pollRef.current) }
  }, [load, schedulePoll])

  const handleExport = async (fmt: 'excel' | 'pdf' | 'json') => {
    if (!doc) return
    setExporting(fmt)
    try {
      const data = await exportReport(doc.id, fmt)
      if (fmt === 'json') {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = `doc-${doc.id}.json`; a.click()
      } else {
        const url = URL.createObjectURL(data)
        const a = document.createElement('a')
        a.href = url
        a.download = `doc-${doc.id}.${fmt === 'excel' ? 'xlsx' : 'pdf'}`
        a.click()
      }
      toast.success('Descarga iniciada')
    } catch {
      toast.error('Error al exportar')
    } finally {
      setExporting(null)
    }
  }

  const isProcessing = doc && !TERMINAL_STATUSES.has(doc.status)

  return (
    <AuthGuard>
      <AppShell>
        <div className="px-8 py-7 max-w-5xl mx-auto">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 text-sm mb-6" style={{ color: 'var(--df-muted)' }}>
            <Link
              href="/documents"
              className="flex items-center gap-1 hover:opacity-80 transition-opacity"
              style={{ color: 'var(--df-muted)' }}
            >
              <ArrowLeft className="w-4 h-4" /> Documentos
            </Link>
            <span>/</span>
            <span className="truncate max-w-[300px]" style={{ color: 'var(--df-text)' }}>
              {loading ? '...' : doc?.filename}
            </span>
            {isProcessing && (
              <RefreshCw className="w-3.5 h-3.5 animate-spin ml-1" style={{ color: 'var(--df-accent)' }} />
            )}
          </div>

          {loading ? (
            <div className="space-y-4">
              <Skeleton className="h-8 w-2/3" />
              <div className="grid grid-cols-3 gap-4">
                {[0,1,2].map(i => <Skeleton key={i} className="h-32" />)}
              </div>
            </div>
          ) : !doc ? (
            <p style={{ color: 'var(--df-muted)' }}>Documento no encontrado</p>
          ) : (
            <div className="space-y-5">
              {/* Header */}
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex items-start gap-3">
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(0,194,255,0.08)', border: '1px solid var(--df-accent-dim)' }}
                  >
                    <FileText className="w-5 h-5" style={{ color: 'var(--df-accent)' }} />
                  </div>
                  <div>
                    <h1 className="text-xl font-bold break-all" style={{ color: 'var(--df-text)' }}>
                      {doc.filename}
                    </h1>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <StatusBadge status={doc.status} />
                      {doc.doc_category && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
                          {doc.doc_category}
                        </span>
                      )}
                      <span className="text-xs font-mono uppercase" style={{ color: 'var(--df-muted)' }}>
                        {doc.file_type}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex gap-2 flex-wrap">
                  {doc.status === 'done' && (
                    <>
                      <Link href={`/documents/${doc.id}/chat`} className="df-btn-ghost text-xs">
                        <MessageSquare className="w-4 h-4" /> Chat
                      </Link>
                      {(['excel','pdf','json'] as const).map(fmt => (
                        <button
                          key={fmt}
                          onClick={() => handleExport(fmt)}
                          disabled={exporting === fmt}
                          className="df-btn-ghost text-xs font-mono uppercase disabled:opacity-40"
                        >
                          <Download className="w-4 h-4" /> {fmt}
                        </button>
                      ))}
                    </>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Metadata */}
                <Section title="Metadatos">
                  <MetaRow icon={HardDrive} label="Tamaño" value={formatBytes(doc.file_size)} />
                  <MetaRow icon={FileText}  label="Páginas" value={doc.page_count} />
                  <MetaRow
                    icon={Clock}
                    label="Creado"
                    value={format(new Date(doc.created_at), "d MMM yyyy HH:mm", { locale: es })}
                  />
                  <MetaRow
                    icon={Clock}
                    label="Actualizado"
                    value={format(new Date(doc.updated_at), "d MMM yyyy HH:mm", { locale: es })}
                  />
                </Section>

                {/* Processing / AI results */}
                {doc.status === 'done' && (
                  <div className="md:col-span-2 space-y-4">
                    {doc.summary && (
                      <Section title="Resumen IA">
                        <p className="text-sm leading-relaxed" style={{ color: 'var(--df-text)' }}>
                          {doc.summary}
                        </p>
                      </Section>
                    )}

                    <div className="grid grid-cols-2 gap-4">
                      {doc.sentiment && (
                        <Section title="Sentimiento">
                          <div className="flex items-center gap-2">
                            <BarChart2 className="w-5 h-5" style={{ color: 'var(--df-accent)' }} />
                            <span className="text-lg font-bold capitalize" style={{ color: 'var(--df-text)' }}>
                              {doc.sentiment}
                            </span>
                          </div>
                        </Section>
                      )}

                      {doc.keywords && doc.keywords.length > 0 && (
                        <Section title="Palabras clave">
                          <div className="flex flex-wrap gap-1.5">
                            {doc.keywords.slice(0, 10).map(kw => (
                              <span
                                key={kw}
                                className="text-xs px-2 py-0.5 rounded-full"
                                style={{
                                  background: 'var(--df-surface)',
                                  border: '1px solid var(--df-border)',
                                  color: 'var(--df-text)',
                                }}
                              >
                                {kw}
                              </span>
                            ))}
                          </div>
                        </Section>
                      )}
                    </div>

                    {doc.entities && Object.keys(doc.entities).length > 0 && (
                      <Section title="Entidades detectadas">
                        <div className="space-y-3">
                          {Object.entries(doc.entities).map(([type, items]) => (
                            <div key={type}>
                              <p className="text-xs font-mono uppercase mb-1.5" style={{ color: 'var(--df-muted)' }}>
                                {type}
                              </p>
                              <div className="flex flex-wrap gap-1.5">
                                {(items as string[]).slice(0, 8).map(item => (
                                  <span
                                    key={item}
                                    className="text-xs px-2 py-0.5 rounded"
                                    style={{
                                      background: 'var(--df-surface)',
                                      border: '1px solid var(--df-border)',
                                      color: 'var(--df-text)',
                                    }}
                                  >
                                    {item}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </Section>
                    )}
                  </div>
                )}

                {doc.status === 'failed' && (
                  <div className="md:col-span-2">
                    <Section title="Error de procesamiento">
                      <p className="text-sm text-red-400">{doc.error_message ?? 'Error desconocido'}</p>
                    </Section>
                  </div>
                )}

                {(doc.status === 'pending' || doc.status === 'processing') && (
                  <div className="md:col-span-2">
                    <div className="df-card p-8 flex flex-col items-center gap-4 text-center">
                      <div
                        className="w-14 h-14 rounded-full border-2 animate-spin"
                        style={{ borderColor: 'rgba(0,194,255,0.3)', borderTopColor: 'var(--df-accent)' }}
                      />
                      <div>
                        <p className="text-sm font-semibold" style={{ color: 'var(--df-text)' }}>
                          {doc.status === 'processing' ? 'Analizando con IA...' : 'En cola de procesamiento'}
                        </p>
                        <p className="text-xs mt-1" style={{ color: 'var(--df-muted)' }}>
                          Esta página se actualiza automáticamente cada {POLL_INTERVAL_MS / 1000} segundos
                        </p>
                      </div>
                      <StatusBadge status={doc.status} />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </AppShell>
    </AuthGuard>
  )
}
