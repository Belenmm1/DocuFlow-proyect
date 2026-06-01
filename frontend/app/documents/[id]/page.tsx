'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import AuthGuard from '@/components/layout/AuthGuard'
import StatusBadge from '@/components/ui/StatusBadge'
import { Skeleton } from '@/components/ui/Skeleton'
import { fetchDocument, exportReport, reprocessDocument, compareDocuments, fetchDocuments } from '@/lib/api'
import type { Document } from '@/types'
import {
  ArrowLeft, MessageSquare, Download, FileText,
  Tag, BarChart2, Hash, Clock, HardDrive,
  RefreshCw, GitCompare, ChevronDown, AlertTriangle,
  CheckCircle2, Info, X
} from 'lucide-react'
import Link from 'next/link'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="df-card p-5">
      <p className="text-xs font-mono uppercase tracking-widest text-[#5a7a96] mb-4">{title}</p>
      {children}
    </div>
  )
}

function MetaRow({ icon: Icon, label, value }: { icon: any; label: string; value: string | number | undefined }) {
  if (!value) return null
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-[#1e2d40]/50 last:border-0">
      <Icon className="w-4 h-4 text-[#5a7a96] flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-[#5a7a96] mb-0.5">{label}</p>
        <p className="text-sm text-[#c8d8ea] break-all">{value}</p>
      </div>
    </div>
  )
}

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1048576) return `${(b/1024).toFixed(0)} KB`
  return `${(b/1048576).toFixed(1)} MB`
}

const IMPACT_COLORS = {
  alto:  'text-red-400 bg-red-500/10 border-red-500/20',
  medio: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  bajo:  'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
}

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [doc, setDoc] = useState<Document | null>(null)
  const [loading, setLoading] = useState(true)
  const [reprocessing, setReprocessing] = useState(false)

  // Compare state
  const [showCompare, setShowCompare] = useState(false)
  const [compareDocs, setCompareDocs] = useState<Document[]>([])
  const [selectedCompareId, setSelectedCompareId] = useState<number | null>(null)
  const [comparing, setComparing] = useState(false)
  const [compareResult, setCompareResult] = useState<any>(null)

  // SSE ref
  const sseRef = useRef<EventSource | null>(null)

  const loadDoc = async () => {
    try {
      const d = await fetchDocument(Number(id))
      setDoc(d)
      return d
    } catch {
      toast.error('Documento no encontrado')
      return null
    }
  }

  // SSE: escuchar cambios de estado mientras procesa
  const startSSE = (docId: number) => {
    if (sseRef.current) sseRef.current.close()
    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const es = new EventSource(`${apiBase}/api/v1/documents/${docId}/status/stream`)
    sseRef.current = es

    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data)
        if (payload.status === 'done' || payload.status === 'failed') {
          es.close()
          sseRef.current = null
          loadDoc().then(d => {
            if (d?.status === 'done') toast.success('✅ Documento procesado correctamente')
            if (d?.status === 'failed') toast.error('❌ Error al procesar el documento')
          })
        }
      } catch {}
    }

    es.onerror = () => {
      es.close()
      sseRef.current = null
    }
  }

  useEffect(() => {
    loadDoc().then(d => {
      if (d && (d.status === 'pending' || d.status === 'processing')) {
        startSSE(d.id)
      }
    }).finally(() => setLoading(false))

    return () => { sseRef.current?.close() }
  }, [id])

  const handleReprocess = async () => {
    if (!doc) return
    setReprocessing(true)
    try {
      const updated = await reprocessDocument(doc.id)
      setDoc(updated)
      toast.success('Reprocesando documento...')
      startSSE(doc.id)
    } catch {
      toast.error('Error al reprocesar')
    } finally {
      setReprocessing(false)
    }
  }

  const handleExport = async (fmt: 'excel' | 'pdf' | 'json') => {
    if (!doc) return
    try {
      const data = await exportReport(doc.id, fmt)
      if (fmt === 'json') {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = `doc-${doc.id}.json`; a.click()
      } else {
        const url = URL.createObjectURL(data)
        const a = document.createElement('a'); a.href = url; a.download = `doc-${doc.id}.${fmt === 'excel' ? 'xlsx' : 'pdf'}`; a.click()
      }
      toast.success('Descarga iniciada')
    } catch { toast.error('Error al exportar') }
  }

  const openCompare = async () => {
    setShowCompare(true)
    setCompareResult(null)
    try {
      const page = await fetchDocuments({ status: 'done', limit: 50 } as any)
      setCompareDocs(page.items.filter((d: Document) => d.id !== Number(id)))
    } catch {}
  }

  const handleCompare = async () => {
    if (!selectedCompareId || !doc) return
    setComparing(true)
    try {
      const result = await compareDocuments(doc.id, selectedCompareId)
      setCompareResult(result)
    } catch {
      toast.error('Error al comparar documentos')
    } finally {
      setComparing(false)
    }
  }

  return (
    <AuthGuard>
      <AppShell>
        <div className="px-8 py-7 max-w-5xl mx-auto">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 text-sm text-[#5a7a96] mb-6">
            <Link href="/documents" className="flex items-center gap-1 hover:text-[#c8d8ea] transition-colors">
              <ArrowLeft className="w-4 h-4" /> Documentos
            </Link>
            <span>/</span>
            <span className="text-[#c8d8ea] truncate max-w-[300px]">
              {loading ? '...' : doc?.filename}
            </span>
          </div>

          {loading ? (
            <div className="space-y-4">
              <Skeleton className="h-8 w-2/3" />
              <div className="grid grid-cols-3 gap-4">
                {[0,1,2].map(i => <Skeleton key={i} className="h-32" />)}
              </div>
            </div>
          ) : !doc ? (
            <p className="text-[#5a7a96]">Documento no encontrado</p>
          ) : (
            <div className="space-y-5">
              {/* Header */}
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[rgba(0,194,255,0.08)] border border-[#005580] flex items-center justify-center flex-shrink-0">
                    <FileText className="w-5 h-5 text-[#00c2ff]" />
                  </div>
                  <div>
                    <h1 className="text-xl font-bold text-white break-all">{doc.filename}</h1>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <StatusBadge status={doc.status} />
                      {doc.doc_category && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
                          {doc.doc_category}
                        </span>
                      )}
                      <span className="text-xs font-mono uppercase text-[#5a7a96]">{doc.file_type}</span>
                    </div>
                  </div>
                </div>

                <div className="flex gap-2 flex-shrink-0 flex-wrap justify-end">
                  {/* Botón Reprocesar: visible para failed y done */}
                  {(doc.status === 'failed' || doc.status === 'done') && (
                    <button
                      onClick={handleReprocess}
                      disabled={reprocessing}
                      className="df-btn-ghost text-xs gap-1.5 disabled:opacity-50"
                    >
                      <RefreshCw className={`w-4 h-4 ${reprocessing ? 'animate-spin' : ''}`} />
                      {reprocessing ? 'Reprocesando...' : 'Reprocesar'}
                    </button>
                  )}

                  {doc.status === 'done' && (
                    <>
                      <button
                        onClick={openCompare}
                        className="df-btn-ghost text-xs gap-1.5"
                      >
                        <GitCompare className="w-4 h-4" /> Comparar
                      </button>
                      <Link href={`/documents/${doc.id}/chat`} className="df-btn-ghost text-xs">
                        <MessageSquare className="w-4 h-4" /> Chat
                      </Link>
                      {(['excel','pdf','json'] as const).map(fmt => (
                        <button key={fmt} onClick={() => handleExport(fmt)} className="df-btn-ghost text-xs font-mono uppercase">
                          <Download className="w-4 h-4" /> {fmt}
                        </button>
                      ))}
                    </>
                  )}
                </div>
              </div>

              {/* Comparar panel */}
              {showCompare && (
                <div className="df-card p-5 border border-[#1e2d40]">
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-xs font-mono uppercase tracking-widest text-[#5a7a96]">Comparar con otro documento</p>
                    <button onClick={() => { setShowCompare(false); setCompareResult(null) }} className="text-[#5a7a96] hover:text-[#c8d8ea]">
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="flex gap-3 items-end">
                    <div className="flex-1">
                      <label className="df-label">Seleccionar documento</label>
                      <select
                        value={selectedCompareId ?? ''}
                        onChange={e => setSelectedCompareId(Number(e.target.value) || null)}
                        className="df-input w-full"
                      >
                        <option value="">— elegí un documento —</option>
                        {compareDocs.map(d => (
                          <option key={d.id} value={d.id}>{d.filename}</option>
                        ))}
                      </select>
                    </div>
                    <button
                      onClick={handleCompare}
                      disabled={!selectedCompareId || comparing}
                      className="df-btn-primary text-xs disabled:opacity-50"
                    >
                      {comparing ? 'Comparando...' : 'Comparar'}
                    </button>
                  </div>

                  {/* Resultado de comparación */}
                  {compareResult && (
                    <div className="mt-5 space-y-4">
                      <div className="flex items-center gap-3">
                        <p className="text-sm font-semibold text-[#c8d8ea]">{compareResult.comparison.resumen_cambios}</p>
                        <span className={`text-xs px-2 py-0.5 rounded-full border font-mono uppercase ${IMPACT_COLORS[compareResult.comparison.impacto as keyof typeof IMPACT_COLORS] ?? ''}`}>
                          impacto {compareResult.comparison.impacto}
                        </span>
                      </div>

                      {compareResult.comparison.recomendacion && (
                        <div className="flex gap-2 p-3 rounded-lg bg-amber-500/5 border border-amber-500/20">
                          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                          <p className="text-xs text-amber-300">{compareResult.comparison.recomendacion}</p>
                        </div>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {compareResult.comparison.cambios_agregados?.length > 0 && (
                          <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                            <p className="text-xs font-mono text-emerald-400 mb-2 uppercase">+ Agregado ({compareResult.comparison.cambios_agregados.length})</p>
                            <ul className="space-y-1">
                              {compareResult.comparison.cambios_agregados.map((c: string, i: number) => (
                                <li key={i} className="text-xs text-[#c8d8ea]">• {c}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {compareResult.comparison.cambios_eliminados?.length > 0 && (
                          <div className="p-3 rounded-lg bg-red-500/5 border border-red-500/20">
                            <p className="text-xs font-mono text-red-400 mb-2 uppercase">− Eliminado ({compareResult.comparison.cambios_eliminados.length})</p>
                            <ul className="space-y-1">
                              {compareResult.comparison.cambios_eliminados.map((c: string, i: number) => (
                                <li key={i} className="text-xs text-[#c8d8ea]">• {c}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {compareResult.comparison.cambios_modificados?.length > 0 && (
                          <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/20">
                            <p className="text-xs font-mono text-blue-400 mb-2 uppercase">~ Modificado ({compareResult.comparison.cambios_modificados.length})</p>
                            <ul className="space-y-1">
                              {compareResult.comparison.cambios_modificados.map((c: any, i: number) => (
                                <li key={i} className="text-xs">
                                  <span className="text-red-400 line-through">{c.original}</span>
                                  <span className="text-[#5a7a96]"> → </span>
                                  <span className="text-emerald-400">{c.nuevo}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Meta */}
                <Section title="Metadatos">
                  <MetaRow icon={HardDrive} label="Tamaño" value={formatBytes(doc.file_size)} />
                  <MetaRow icon={FileText} label="Páginas" value={doc.page_count} />
                  <MetaRow icon={Clock} label="Creado" value={format(new Date(doc.created_at), "d MMM yyyy HH:mm")} />
                  <MetaRow icon={Clock} label="Actualizado" value={format(new Date(doc.updated_at), "d MMM yyyy HH:mm")} />
                </Section>

                {/* AI Analysis */}
                {doc.status === 'done' && (
                  <div className="md:col-span-2 space-y-4">
                    {doc.summary && (
                      <Section title="Resumen IA">
                        <p className="text-sm text-[#c8d8ea] leading-relaxed">{doc.summary}</p>
                      </Section>
                    )}

                    <div className="grid grid-cols-2 gap-4">
                      {doc.sentiment && (
                        <Section title="Sentimiento">
                          <div className="flex items-center gap-2">
                            <BarChart2 className="w-5 h-5 text-[#00c2ff]" />
                            <span className="text-lg font-bold text-[#c8d8ea] capitalize">{doc.sentiment}</span>
                          </div>
                        </Section>
                      )}

                      {doc.keywords && doc.keywords.length > 0 && (
                        <Section title="Palabras clave">
                          <div className="flex flex-wrap gap-1.5">
                            {doc.keywords.slice(0, 10).map(kw => (
                              <span key={kw} className="text-xs px-2 py-0.5 rounded-full bg-[#1e2d40] text-[#c8d8ea] border border-[#2d4463]">
                                {kw}
                              </span>
                            ))}
                          </div>
                        </Section>
                      )}
                    </div>

                    {doc.entities && Object.keys(doc.entities).length > 0 && (
                      <Section title="Entidades detectadas">
                        <div className="space-y-2">
                          {Object.entries(doc.entities).map(([type, items]) => (
                            <div key={type}>
                              <p className="text-xs font-mono uppercase text-[#5a7a96] mb-1">{type}</p>
                              <div className="flex flex-wrap gap-1.5">
                                {(items as string[]).slice(0, 8).map(item => (
                                  <span key={item} className="text-xs px-2 py-0.5 rounded bg-[#0d1219] text-[#c8d8ea] border border-[#1e2d40]">
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
                      <p className="text-sm text-red-400 mb-4">{doc.error_message ?? 'Error desconocido'}</p>
                      <button
                        onClick={handleReprocess}
                        disabled={reprocessing}
                        className="df-btn-primary text-sm gap-2 disabled:opacity-50"
                      >
                        <RefreshCw className={`w-4 h-4 ${reprocessing ? 'animate-spin' : ''}`} />
                        {reprocessing ? 'Reprocesando...' : '🔄 Reprocesar documento'}
                      </button>
                    </Section>
                  </div>
                )}

                {(doc.status === 'pending' || doc.status === 'processing') && (
                  <div className="md:col-span-2">
                    <div className="df-card p-8 flex flex-col items-center gap-3 text-center">
                      <div className="w-12 h-12 rounded-full border-2 border-[#00c2ff]/30 border-t-[#00c2ff] animate-spin" />
                      <p className="text-sm font-semibold text-[#c8d8ea]">Procesando documento</p>
                      <p className="text-xs text-[#5a7a96]">La IA está analizando el contenido... esta página se actualizará automáticamente.</p>
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
