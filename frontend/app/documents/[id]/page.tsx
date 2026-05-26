'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import AuthGuard from '@/components/layout/AuthGuard'
import StatusBadge from '@/components/ui/StatusBadge'
import { Skeleton } from '@/components/ui/Skeleton'
import { fetchDocument, exportReport } from '@/lib/api'
import type { Document } from '@/types'
import {
  ArrowLeft, MessageSquare, Download, FileText,
  Tag, BarChart2, Hash, Clock, HardDrive
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

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [doc, setDoc] = useState<Document | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchDocument(Number(id))
      .then(setDoc)
      .catch(() => toast.error('Documento no encontrado'))
      .finally(() => setLoading(false))
  }, [id])

  const handleExport = async (format: 'excel' | 'pdf' | 'json') => {
    if (!doc) return
    try {
      const data = await exportReport(doc.id, format)
      if (format === 'json') {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = `doc-${doc.id}.json`; a.click()
      } else {
        const url = URL.createObjectURL(data)
        const a = document.createElement('a'); a.href = url; a.download = `doc-${doc.id}.${format === 'excel' ? 'xlsx' : 'pdf'}`; a.click()
      }
      toast.success('Descarga iniciada')
    } catch { toast.error('Error al exportar') }
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
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[rgba(0,194,255,0.08)] border border-[#005580] flex items-center justify-center flex-shrink-0">
                    <FileText className="w-5 h-5 text-[#00c2ff]" />
                  </div>
                  <div>
                    <h1 className="text-xl font-bold text-white break-all">{doc.filename}</h1>
                    <div className="flex items-center gap-2 mt-1.5">
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

                <div className="flex gap-2 flex-shrink-0">
                  {doc.status === 'done' && (
                    <>
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

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Meta */}
                <Section title="Metadatos">
                  <MetaRow icon={HardDrive} label="Tamaño" value={formatBytes(doc.file_size)} />
                  <MetaRow icon={FileText} label="Páginas" value={doc.page_count} />
                  <MetaRow icon={Clock} label="Creado" value={format(new Date(doc.created_at), "d MMM yyyy HH:mm", { locale: es })} />
                  <MetaRow icon={Clock} label="Actualizado" value={format(new Date(doc.updated_at), "d MMM yyyy HH:mm", { locale: es })} />
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
                      <p className="text-sm text-red-400">{doc.error_message ?? 'Error desconocido'}</p>
                    </Section>
                  </div>
                )}

                {(doc.status === 'pending' || doc.status === 'processing') && (
                  <div className="md:col-span-2">
                    <div className="df-card p-8 flex flex-col items-center gap-3 text-center">
                      <div className="w-12 h-12 rounded-full border-2 border-[#00c2ff]/30 border-t-[#00c2ff] animate-spin" />
                      <p className="text-sm font-semibold text-[#c8d8ea]">Procesando documento</p>
                      <p className="text-xs text-[#5a7a96]">La IA está analizando el contenido...</p>
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
