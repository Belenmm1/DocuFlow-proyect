'use client'

import { useState } from 'react'
import { useSession } from 'next-auth/react'
import AppShell from '@/components/layout/AppShell'
import AuthGuard from '@/components/layout/AuthGuard'
import StatsCards from '@/components/dashboard/StatsCards'
import DocumentsTable from '@/components/documents/DocumentsTable'
import Dropzone from '@/components/documents/Dropzone'
import { Plus, X } from 'lucide-react'
import type { Document } from '@/types'

export default function DashboardPage() {
  const { data: session } = useSession()
  const [showUpload, setShowUpload] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleUploaded = (_doc: Document) => {
    setRefreshKey(k => k + 1)
    setTimeout(() => setRefreshKey(k => k + 1), 5000) // refresh after processing
  }

  return (
    <AuthGuard>
      <AppShell>
        <div className="px-8 py-7 max-w-7xl mx-auto">
          {/* Header */}
          <div className="flex items-start justify-between mb-7">
            <div>
              <h1 className="text-2xl font-extrabold text-white tracking-tight">Dashboard</h1>
              <p className="text-sm text-[#5a7a96] mt-0.5">
                Bienvenido, <span className="text-[#c8d8ea]">{session?.user?.email}</span>
              </p>
            </div>
            <button
              onClick={() => setShowUpload(v => !v)}
              className={showUpload ? 'df-btn-ghost' : 'df-btn-primary'}
            >
              {showUpload ? <><X className="w-4 h-4" />Cerrar</> : <><Plus className="w-4 h-4" />Subir documento</>}
            </button>
          </div>

          {/* Upload panel */}
          {showUpload && (
            <div className="df-card p-6 mb-6 animate-in fade-in duration-200">
              <p className="text-xs font-mono uppercase tracking-widest text-[#5a7a96] mb-4">Subir documentos</p>
              <Dropzone onUploaded={handleUploaded} />
            </div>
          )}

          {/* Stats */}
          <div className="mb-6">
            <StatsCards />
          </div>

          {/* Recent docs */}
          <div>
            <p className="text-xs font-mono uppercase tracking-widest text-[#5a7a96] mb-3">Documentos recientes</p>
            <DocumentsTable refreshKey={refreshKey} />
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  )
}
