'use client'

import { useCallback, useEffect, useState } from 'react'
import { deleteDocument, exportReport, fetchDocuments } from '@/lib/api'
import type { Document, DocumentFilters } from '@/types'
import StatusBadge from '@/components/ui/StatusBadge'
import { TableRowSkeleton } from '@/components/ui/Skeleton'
import { Trash2, Download, MessageSquare, Eye, ChevronLeft, ChevronRight, Search, SlidersHorizontal, FileText } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow, format } from 'date-fns'
import { es, enUS } from 'date-fns/locale'
import Link from 'next/link'
import clsx from 'clsx'

const FILE_TYPE_ICON: Record<string, string> = {
  pdf: '📄',
  docx: '📝',
  xlsx: '📊',
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

interface Props {
  refreshKey?: number
}

export default function DocumentsTable({ refreshKey }: Props) {
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [prevCursor, setPrevCursor] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [cursor, setCursor] = useState<string | undefined>(undefined)

  // Filters
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [showFilters, setShowFilters] = useState(false)

  const load = useCallback(async (cur?: string) => {
    setLoading(true)
    try {
      const filters: DocumentFilters & { cursor?: string; limit?: number } = {
        cursor: cur,
        limit: 10,
        search: search || undefined,
        status: statusFilter || undefined,
        file_type: typeFilter || undefined,
      }
      const page = await fetchDocuments(filters)
      setDocs(page.items)
      setNextCursor(page.next_cursor)
      setPrevCursor(page.prev_cursor)
      setTotal(page.total)
    } catch {
      toast.error('Error cargando documentos')
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter, typeFilter])

  useEffect(() => {
    const timer = setTimeout(() => { setCursor(undefined); load(undefined) }, 300)
    return () => clearTimeout(timer)
  }, [search, statusFilter, typeFilter, refreshKey])

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`¿Eliminar "${name}"?`)) return
    try {
      await deleteDocument(id)
      toast.success('Documento eliminado')
      load(cursor)
    } catch {
      toast.error('Error al eliminar')
    }
  }

  const handleExport = async (id: number, format: 'excel' | 'pdf' | 'json') => {
    try {
      const data = await exportReport(id, format)
      if (format === 'json') {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = `doc-${id}.json`; a.click()
      } else {
        const url = URL.createObjectURL(data)
        const a = document.createElement('a'); a.href = url; a.download = `doc-${id}.${format === 'excel' ? 'xlsx' : 'pdf'}`; a.click()
      }
      toast.success('Exportación lista')
    } catch {
      toast.error('Error al exportar')
    }
  }

  return (
    <div className="space-y-3">
      {/* Search + filters bar */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5a7a96]" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar documentos..."
            className="df-input pl-9"
          />
        </div>
        <button
          onClick={() => setShowFilters(v => !v)}
          className={clsx('df-btn-ghost', showFilters && 'border-[#00c2ff] text-[#00c2ff]')}
        >
          <SlidersHorizontal className="w-4 h-4" />
          Filtros
        </button>
      </div>

      {showFilters && (
        <div className="df-card p-4 flex gap-3 flex-wrap">
          <div>
            <label className="df-label">Estado</label>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="df-input w-40"
            >
              <option value="">Todos</option>
              <option value="done">Listo</option>
              <option value="pending">Pendiente</option>
              <option value="processing">Procesando</option>
              <option value="failed">Error</option>
            </select>
          </div>
          <div>
            <label className="df-label">Tipo</label>
            <select
              value={typeFilter}
              onChange={e => setTypeFilter(e.target.value)}
              className="df-input w-36"
            >
              <option value="">Todos</option>
              <option value="pdf">PDF</option>
              <option value="docx">DOCX</option>
              <option value="xlsx">XLSX</option>
            </select>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="df-card overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#1e2d40]">
          <p className="text-xs font-mono text-[#5a7a96]">
            {total} documento{total !== 1 ? 's' : ''}
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e2d40]">
                {['Archivo', 'Tipo', 'Tamaño', 'Estado', 'Categoría', 'Fecha', 'Acciones'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-mono uppercase tracking-wider text-[#5a7a96]">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading
                ? [0,1,2,3,4].map(i => <TableRowSkeleton key={i} />)
                : docs.length === 0
                ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center">
                      <FileText className="w-8 h-8 text-[#2d4463] mx-auto mb-2" />
                      <p className="text-sm text-[#5a7a96]">No hay documentos</p>
                    </td>
                  </tr>
                )
                : docs.map(doc => (
                  <tr
                    key={doc.id}
                    className="border-b border-[#1e2d40]/50 hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-base">{FILE_TYPE_ICON[doc.file_type] ?? '📄'}</span>
                        <div>
                          <p className="font-medium text-[#c8d8ea] max-w-[200px] truncate">{doc.filename}</p>
                          {doc.extracted_text_snippet && (
                            <p className="text-xs text-[#5a7a96] max-w-[200px] truncate">{doc.extracted_text_snippet}</p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs uppercase text-[#5a7a96]">{doc.file_type}</span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-[#5a7a96]">
                      {formatBytes(doc.file_size)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="px-4 py-3">
                      {doc.doc_category
                        ? <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">{doc.doc_category}</span>
                        : <span className="text-[#2d4463] text-xs">—</span>
                      }
                    </td>
                    <td className="px-4 py-3 text-xs text-[#5a7a96] font-mono whitespace-nowrap">
                      {formatDistanceToNow(new Date(doc.created_at), { locale: typeof window !== 'undefined' && localStorage.getItem('docuflow_locale') === 'en' ? enUS : es, addSuffix: true })}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <Link href={`/documents/${doc.id}`} className="w-7 h-7 rounded flex items-center justify-center text-[#5a7a96] hover:text-[#00c2ff] hover:bg-[rgba(0,194,255,0.08)] transition-colors">
                          <Eye className="w-3.5 h-3.5" />
                        </Link>
                        {doc.status === 'done' && (
                          <>
                            <Link href={`/documents/${doc.id}/chat`} className="w-7 h-7 rounded flex items-center justify-center text-[#5a7a96] hover:text-cyan-400 hover:bg-cyan-500/10 transition-colors">
                              <MessageSquare className="w-3.5 h-3.5" />
                            </Link>
                            <div className="relative group/export">
                              <button className="w-7 h-7 rounded flex items-center justify-center text-[#5a7a96] hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors">
                                <Download className="w-3.5 h-3.5" />
                              </button>
                              <div className="absolute right-0 top-8 hidden group-hover/export:flex flex-col z-10 df-card shadow-xl min-w-[110px] overflow-hidden">
                                {(['excel', 'pdf', 'json'] as const).map(fmt => (
                                  <button
                                    key={fmt}
                                    onClick={() => handleExport(doc.id, fmt)}
                                    className="px-3 py-2 text-xs text-left font-mono uppercase tracking-wide text-[#5a7a96] hover:text-[#c8d8ea] hover:bg-white/[0.04] transition-colors"
                                  >
                                    {fmt}
                                  </button>
                                ))}
                              </div>
                            </div>
                          </>
                        )}
                        <button
                          onClick={() => handleDelete(doc.id, doc.filename)}
                          className="w-7 h-7 rounded flex items-center justify-center text-[#5a7a96] hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {(prevCursor || nextCursor) && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-[#1e2d40]">
            <button
              disabled={!prevCursor}
              onClick={() => { setCursor(prevCursor!); load(prevCursor!) }}
              className="df-btn-ghost text-xs disabled:opacity-30"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Anterior
            </button>
            <button
              disabled={!nextCursor}
              onClick={() => { setCursor(nextCursor!); load(nextCursor!) }}
              className="df-btn-ghost text-xs disabled:opacity-30"
            >
              Siguiente <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
