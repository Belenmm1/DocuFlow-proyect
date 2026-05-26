'use client'

import { useState } from 'react'
import { signIn } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Zap, Mail, Lock, ArrowRight, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    const res = await signIn('credentials', {
      email,
      password,
      redirect: false,
    })
    setLoading(false)
    if (res?.ok) {
      toast.success('Bienvenido de vuelta')
      router.replace('/dashboard')
    } else {
      toast.error('Credenciales incorrectas')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative">
      {/* Background grid */}
      <div className="absolute inset-0 opacity-30"
        style={{
          backgroundImage: 'linear-gradient(#1e2d40 1px, transparent 1px), linear-gradient(90deg, #1e2d40 1px, transparent 1px)',
          backgroundSize: '40px 40px',
          maskImage: 'radial-gradient(ellipse 60% 60% at 50% 50%, black 30%, transparent 100%)',
        }}
      />

      <div className="relative w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#00c2ff] mb-4 shadow-[0_0_30px_rgba(0,194,255,0.3)]">
            <Zap className="w-7 h-7 text-[#080b12]" strokeWidth={2.5} />
          </div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">
            Docu<span className="text-[#00c2ff]">Flow</span>
          </h1>
          <p className="text-sm text-[#5a7a96] mt-1">Iniciá sesión en tu cuenta</p>
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
                placeholder="••••••••"
                required
                className="df-input pl-10"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="df-btn-primary w-full justify-center mt-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : (
              <>Ingresar <ArrowRight className="w-4 h-4" /></>
            )}
          </button>
        </form>

        <p className="text-center text-sm text-[#5a7a96] mt-4">
          ¿No tenés cuenta?{' '}
          <Link href="/register" className="text-[#00c2ff] hover:underline font-medium">
            Registrate
          </Link>
        </p>
      </div>
    </div>
  )
}
