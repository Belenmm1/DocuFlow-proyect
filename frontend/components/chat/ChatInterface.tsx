'use client'

import { useEffect, useRef, useState } from 'react'
import { sendChatMessage, fetchChatHistory } from '@/lib/api'
import { Send, Bot, User, Loader2, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { es } from 'date-fns/locale'

interface Message {
  role: 'user' | 'assistant'
  content: string
  created_at?: string
}

interface Props {
  docId: number
  docName: string
}

export default function ChatInterface({ docId, docName }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [convId, setConvId] = useState<string | undefined>()
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)

    try {
      const res = await sendChatMessage(docId, msg, convId)
      setConvId(res.conversation_id)
      setMessages(prev => [...prev, { role: 'assistant', content: res.answer }])
    } catch {
      toast.error('Error enviando mensaje')
      setMessages(prev => prev.slice(0, -1))
      setInput(msg)
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[#1e2d40] flex items-center justify-between">
        <div>
          <p className="text-xs font-mono uppercase tracking-widest text-[#5a7a96] mb-0.5">Chat con documento</p>
          <p className="text-sm font-semibold text-[#c8d8ea] truncate max-w-[400px]">{docName}</p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={() => { setMessages([]); setConvId(undefined) }}
            className="df-btn-ghost text-xs gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Nueva sesión
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
            <div className="w-16 h-16 rounded-2xl bg-[rgba(0,194,255,0.08)] border border-[#005580] flex items-center justify-center">
              <Bot className="w-8 h-8 text-[#00c2ff]" />
            </div>
            <div>
              <p className="text-sm font-semibold text-[#c8d8ea]">Preguntá sobre el documento</p>
              <p className="text-xs text-[#5a7a96] mt-1">Podés preguntar sobre el contenido, pedir resúmenes o extraer información específica.</p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {['¿De qué trata este documento?', '¿Cuáles son los puntos principales?', '¿Hay fechas importantes?'].map(q => (
                <button
                  key={q}
                  onClick={() => { setInput(q); inputRef.current?.focus() }}
                  className="text-xs px-3 py-1.5 rounded-full border border-[#1e2d40] text-[#5a7a96] hover:border-[#2d4463] hover:text-[#c8d8ea] transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={clsx('flex gap-3 animate-in fade-in duration-300', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row')}
          >
            <div className={clsx(
              'w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5',
              msg.role === 'user' ? 'bg-[#1e2d40]' : 'bg-[rgba(0,194,255,0.12)] border border-[#005580]'
            )}>
              {msg.role === 'user'
                ? <User className="w-3.5 h-3.5 text-[#5a7a96]" />
                : <Bot className="w-3.5 h-3.5 text-[#00c2ff]" />
              }
            </div>
            <div className={clsx(
              'max-w-[75%] rounded-xl px-4 py-3 text-sm leading-relaxed',
              msg.role === 'user'
                ? 'bg-[#1e2d40] text-[#c8d8ea] rounded-tr-sm'
                : 'bg-[#0d1219] border border-[#1e2d40] text-[#c8d8ea] rounded-tl-sm'
            )}>
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 bg-[rgba(0,194,255,0.12)] border border-[#005580]">
              <Bot className="w-3.5 h-3.5 text-[#00c2ff]" />
            </div>
            <div className="bg-[#0d1219] border border-[#1e2d40] rounded-xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1.5 items-center">
                {[0, 1, 2].map(i => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-[#00c2ff] animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-[#1e2d40]">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Escribí tu pregunta... (Enter para enviar)"
            rows={1}
            className="df-input resize-none flex-1 min-h-[42px] max-h-[120px] py-2.5"
            style={{ height: 'auto' }}
            onInput={e => {
              const t = e.target as HTMLTextAreaElement
              t.style.height = 'auto'
              t.style.height = Math.min(t.scrollHeight, 120) + 'px'
            }}
          />
          <button
            onClick={send}
            disabled={!input.trim() || loading}
            className="df-btn-primary h-[42px] px-4 flex-shrink-0"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
        <p className="text-[10px] text-[#2d4463] mt-1.5 font-mono">Shift+Enter para nueva línea</p>
      </div>
    </div>
  )
}
