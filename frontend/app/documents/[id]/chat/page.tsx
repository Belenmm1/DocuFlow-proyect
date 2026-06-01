'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import AuthGuard from '@/components/layout/AuthGuard'
import { fetchDocument, chatWithDocument } from '@/lib/api'
import type { Document } from '@/types'
import {
  ArrowLeft, Send, Bot, User, Sparkles,
  FileText, Loader2
} from 'lucide-react'
import Link from 'next/link'
import toast from 'react-hot-toast'

interface Message {
  role: 'user' | 'assistant'
  content: string
  ts: Date
}

const SUGGESTED_QUESTIONS: Record<string, string[]> = {
  factura:       ['¿Cuál es el total?', '¿Está vencida la fecha?', '¿Quién es el emisor?'],
  contrato:      ['¿Cuándo vence el contrato?', '¿Cuáles son las penalidades?', '¿Se renueva automáticamente?'],
  cv:            ['¿Cuántos años de experiencia tiene?', '¿Qué tecnologías maneja?', '¿Cuál es su último cargo?'],
  medico:        ['¿Cuál es el diagnóstico?', '¿Qué medicamentos se indican?', '¿Hay alertas urgentes?'],
  academico:     ['¿Cuál es la hipótesis principal?', '¿Qué metodología usaron?', '¿Cuáles son las conclusiones?'],
  contrato:      ['¿Cuáles son las obligaciones clave?', '¿Qué ley aplica?', '¿Quiénes son las partes?'],
  informe:       ['¿Cuáles son los puntos clave?', '¿Qué se recomienda?', '¿Quién lo elaboró?'],
  legal:         ['¿Quiénes son las partes?', '¿Cuál es la jurisdicción?', '¿Qué se dispone?'],
  resolucion:    ['¿Qué se resuelve?', '¿Quién la emite?', '¿Cuándo entra en vigencia?'],
  presentacion:  ['¿Cuál es la propuesta de valor?', '¿A quién va dirigida?', '¿Qué se pide al receptor?'],
  otro:          ['¿De qué trata este documento?', '¿Cuáles son los puntos principales?'],
}

function ChatBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center ${
        isUser
          ? 'bg-[#00c2ff]/10 border border-[#00c2ff]/20'
          : 'bg-purple-500/10 border border-purple-500/20'
      }`}>
        {isUser
          ? <User className="w-4 h-4 text-[#00c2ff]" />
          : <Bot className="w-4 h-4 text-purple-400" />
        }
      </div>
      <div className={`max-w-[70%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
        isUser
          ? 'bg-[#00c2ff]/10 border border-[#00c2ff]/20 text-[#c8d8ea] rounded-tr-sm'
          : 'bg-[#0d1829] border border-[#1e2d40] text-[#c8d8ea] rounded-tl-sm'
      }`}>
        {msg.content}
        <p className="text-[10px] text-[#5a7a96] mt-1.5 font-mono">
          {msg.ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  )
}

export default function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const [doc, setDoc] = useState<Document | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    fetchDocument(Number(id))
      .then(setDoc)
      .catch(() => toast.error('Documento no encontrado'))
  }, [id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (text?: string) => {
    const question = (text ?? input).trim()
    if (!question || sending) return

    setInput('')
    setSending(true)

    const userMsg: Message = { role: 'user', content: question, ts: new Date() }
    setMessages(prev => [...prev, userMsg])

    try {
      const res = await chatWithDocument(Number(id), question)
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: res.response, ts: new Date() }
      ])
    } catch {
      toast.error('Error al consultar el documento')
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Ocurrió un error al procesar tu consulta. Intentá de nuevo.', ts: new Date() }
      ])
    } finally {
      setSending(false)
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const suggestions = doc?.doc_category
    ? (SUGGESTED_QUESTIONS[doc.doc_category] ?? SUGGESTED_QUESTIONS['otro'])
    : SUGGESTED_QUESTIONS['otro']

  return (
    <AuthGuard>
      <AppShell>
        <div className="flex flex-col h-[calc(100vh-4rem)] max-w-3xl mx-auto px-4">

          {/* Header */}
          <div className="flex items-center gap-3 py-4 border-b border-[#1e2d40] flex-shrink-0">
            <Link
              href={`/documents/${id}`}
              className="flex items-center gap-1 text-sm text-[#5a7a96] hover:text-[#c8d8ea] transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
              <FileText className="w-4 h-4 text-purple-400" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[#c8d8ea] truncate">
                Chat — {doc?.filename ?? '...'}
              </p>
              {doc?.doc_category && (
                <p className="text-xs text-[#5a7a96] capitalize">{doc.doc_category}</p>
              )}
            </div>
            <div className="ml-auto flex items-center gap-1.5 text-xs text-purple-400 font-mono bg-purple-500/10 px-2 py-1 rounded-full border border-purple-500/20">
              <Sparkles className="w-3 h-3" />
              RAG
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto py-5 space-y-4">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-6">
                <div className="w-16 h-16 rounded-2xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                  <Bot className="w-8 h-8 text-purple-400" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-semibold text-[#c8d8ea] mb-1">
                    Hacé tu primera pregunta
                  </p>
                  <p className="text-xs text-[#5a7a96]">
                    La IA analizará el documento y te responderá con precisión
                  </p>
                </div>

                {/* Suggested questions */}
                <div className="w-full max-w-md">
                  <p className="text-xs font-mono uppercase text-[#5a7a96] text-center mb-3">
                    Preguntas sugeridas
                  </p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {suggestions.map(q => (
                      <button
                        key={q}
                        onClick={() => send(q)}
                        disabled={sending}
                        className="text-xs px-3 py-1.5 rounded-full bg-[#0d1829] border border-[#1e2d40] text-[#c8d8ea] hover:border-[#2d4463] hover:text-white transition-colors disabled:opacity-50"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              messages.map((msg, i) => <ChatBubble key={i} msg={msg} />)
            )}

            {sending && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                  <Bot className="w-4 h-4 text-purple-400" />
                </div>
                <div className="bg-[#0d1829] border border-[#1e2d40] rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 text-[#5a7a96] animate-spin" />
                  <span className="text-xs text-[#5a7a96]">Analizando...</span>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="py-4 border-t border-[#1e2d40] flex-shrink-0">
            <div className="flex gap-2 items-end">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Hacé una pregunta sobre este documento..."
                rows={1}
                disabled={sending || !doc}
                className="df-input flex-1 resize-none min-h-[42px] max-h-[120px] py-2.5 text-sm"
                style={{ fieldSizing: 'content' } as any}
              />
              <button
                onClick={() => send()}
                disabled={!input.trim() || sending || !doc}
                className="df-btn-primary h-[42px] w-[42px] p-0 flex items-center justify-center disabled:opacity-50 flex-shrink-0"
              >
                {sending
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <Send className="w-4 h-4" />
                }
              </button>
            </div>
            <p className="text-[10px] text-[#5a7a96] mt-1.5 font-mono">
              Enter para enviar · Shift+Enter para nueva línea
            </p>
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  )
}
