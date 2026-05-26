'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import AuthGuard from '@/components/layout/AuthGuard'
import ChatInterface from '@/components/chat/ChatInterface'
import { fetchDocument } from '@/lib/api'
import type { Document } from '@/types'
import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'

export default function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const [doc, setDoc] = useState<Document | null>(null)

  useEffect(() => {
    fetchDocument(Number(id)).then(setDoc).catch(() => {})
  }, [id])

  return (
    <AuthGuard>
      <AppShell>
        <div className="flex flex-col h-screen">
          {/* Breadcrumb */}
          <div className="px-6 py-3 border-b border-[#1e2d40] flex items-center gap-2 text-sm text-[#5a7a96]">
            <Link href={`/documents/${id}`} className="flex items-center gap-1 hover:text-[#c8d8ea] transition-colors">
              <ArrowLeft className="w-4 h-4" /> Detalle
            </Link>
            <span>/</span>
            <span className="text-[#c8d8ea]">Chat</span>
          </div>

          <div className="flex-1 overflow-hidden">
            <ChatInterface docId={Number(id)} docName={doc?.filename ?? `Documento #${id}`} />
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  )
}
