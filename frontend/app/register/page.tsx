'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Zap, Mail, Lock, ArrowRight, Loader2, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { registerRequest } from '@/lib/api'
import { signIn } from 'next-auth/react'

export default function RegisterPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password !== confirm) { toast.error('Las contraseñas no coinciden'); return }
    if (password.length < 8) { toast.error('La contraseña debe tener al menos 8 caracteres'); return }

    setLoading(true)
    try {
      await registerRequest(email, password)
      toast.success('Cuenta creada correctamente')
      const res = await signIn('credentials', { email, password, redirect: false })
      if (res?.ok) router.replace('/dashboard')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Error al registrarse')
    } finally {
      setLoading(false)
    }
  }

  const passwordOk = password.length >= 8
  const match = password === confirm && confirm.length > 0

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative">
      <div className="absolute inset-0 opacity-30"
        style={{
          backgroundImage: 'linear-gradient(#1e2d40 1px, transparent 1px), linear-gradient(90deg, #1e2d40 1px, transparent 1px)',
          backgroundSize: '40px 40px',
          maskImage: 'radial-gradient(ellipse 60% 60% at 50% 50%, black 30%, transparent 100%)',
        }}
      />

      <div className="relative w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#00c2ff] mb-4 shadow-[0_0_30px_rgba(0,194,255,0.3)]">
            <Zap className="w-7 h-7 text-[#080b12]" strokeWidth={2.5} />
          </div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">
            Docu<span className="text-[#00c2ff]">Flow</span>
          </h1>
          <p className="text-sm text-[#5a7a96] mt-1">Creá tu cuenta gratis</p>
        </div>

        <form onSubmit={handleSubmit} className="df-card p-6 space-y-4">
          <div>
            <label className="df-label">Email</label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5a7a96]" />
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="tu@email.com"
                required
                className="df-input pl-10"
              />
            </div>
          </div>

          <div>
            <label className="df-label">Contraseña</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5a7a96]" />
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres"
                required
                className="df-input pl-10"
              />
              {passwordOk && <CheckCircle className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-emerald-400" />}
            </div>
          </div>

          <div>
            <label className="df-label">Confirmá contraseña</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5a7a96]" />
              <input
                type="password"
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                placeholder="Repetí la contraseña"
                required
                className="df-input pl-10"
              />
              {match && <CheckCircle className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-emerald-400" />}
            </div>
          </div>

          <div className="flex flex-col gap-1">
            {[
              { ok: passwordOk, label: 'Mínimo 8 caracteres' },
              { ok: match, label: 'Las contraseñas coinciden' },
            ].map(({ ok, label }) => (
              <div key={label} className="flex items-center gap-1.5 text-xs">
                <div className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-emerald-400' : 'bg-[#2d4463]'}`} />
                <span className={ok ? 'text-emerald-400' : 'text-[#5a7a96]'}>{label}</span>
              </div>
            ))}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="df-btn-primary w-full justify-center mt-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : (
              <>Crear cuenta <ArrowRight className="w-4 h-4" /></>
            )}
          </button>
        </form>

        <p className="text-center text-sm text-[#5a7a96] mt-4">
          ¿Ya tenés cuenta?{' '}
          <Link href="/login" className="text-[#00c2ff] hover:underline font-medium">
            Iniciá sesión
          </Link>
        </p>
      </div>
    </div>
  )
}
