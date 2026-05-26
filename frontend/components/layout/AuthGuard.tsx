'use client'

import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { Zap } from 'lucide-react'

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { status } = useSession()
  const router = useRouter()

  useEffect(() => {
    if (status === 'unauthenticated') router.replace('/login')
  }, [status, router])

  if (status === 'loading') {
    return (
      <div className="h-screen flex items-center justify-center bg-[#080b12]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-[#00c2ff] flex items-center justify-center animate-pulse">
            <Zap className="w-5 h-5 text-[#080b12]" />
          </div>
          <p className="text-xs font-mono text-[#5a7a96] tracking-widest uppercase">Cargando...</p>
        </div>
      </div>
    )
  }

  if (status !== 'authenticated') return null
  return <>{children}</>
}
