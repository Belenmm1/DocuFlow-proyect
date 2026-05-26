'use client'

import { useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import AuthGuard from '@/components/layout/AuthGuard'
import DocumentsTable from '@/components/documents/DocumentsTable'
import Dropzone from '@/components/documents/Dropzone'
import { Plus, X, FileText } from 'lucide-react'
import type { Document } from '@/types'

export default function DocumentsPage() {
  const [showUpload, setShowUpload] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  return (
    <AuthGuard>
      <AppShell>
        <div className="px-8 py-7 max-w-7xl mx-auto">
          <div className="flex items-start justify-between mb-7">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-[rgba(0,194,255,0.08)] border border-[#005580] flex items-center justify-center">
                <FileText className="w-4 h-4 text-[#00c2ff]" />
              </div>
              <div>
                <h1 className="text-2xl font-extrabold text-white tracking-tight">Documentos</h1>
                <p className="text-sm text-[#5a7a96] mt-0.5">Todos tus documentos procesados</p>
              </div>
            </div>
            <button
              onClick={() => setShowUpload(v => !v)}
              className={showUpload ? 'df-btn-ghost' : 'df-btn-primary'}
            >
              {showUpload ? <><X className="w-4 h-4" />Cerrar</> : <><Plus className="w-4 h-4" />Nuevo documento</>}
            </button>
          </div>

          {showUpload && (
            <div className="df-card p-6 mb-6 animate-in fade-in duration-200">
              <p className="text-xs font-mono uppercase tracking-widest text-[#5a7a96] mb-4">Subir documentos</p>
              <Dropzone onUploaded={() => setRefreshKey(k => k + 1)} />
            </div>
          )}

          <DocumentsTable refreshKey={refreshKey} />
        </div>
      </AppShell>
    </AuthGuard>
  )
}
