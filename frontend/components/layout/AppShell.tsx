'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { signOut, useSession } from 'next-auth/react'
import {
  LayoutDashboard, FileText, LogOut, Zap,
  ChevronDown, User, Sun, Moon
} from 'lucide-react'
import { useState } from 'react'
import clsx from 'clsx'
import { useTheme } from '@/lib/theme'

const NAV = [
  { href: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { href: '/documents',  icon: FileText,        label: 'Documentos' },
]

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { data: session } = useSession()
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const { theme, toggle } = useTheme()

  const planColors: Record<string, string> = {
    free:       'var(--df-muted)',
    pro:        'var(--df-cyan)',
    enterprise: 'var(--df-purple)',
  }
  const planColor = planColors[(session?.user as any)?.plan ?? 'free'] ?? 'var(--df-muted)'

  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: 'var(--df-base)' }}>
      {/* Sidebar */}
      <aside
        className="w-60 flex-shrink-0 flex flex-col"
        style={{
          backgroundColor: 'var(--df-sidebar)',
          borderRight: '1px solid var(--df-sidebar-border)',
        }}
      >
        {/* Logo */}
        <div
          className="px-5 pt-6 pb-5"
          style={{ borderBottom: '1px solid var(--df-sidebar-border)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center"
                style={{
                  background: 'var(--df-accent)',
                  boxShadow: '0 0 12px rgba(0,194,255,0.4)',
                }}
              >
                <Zap className="w-4 h-4" style={{ color: '#080b12' }} strokeWidth={2.5} />
              </div>
              <div>
                <span className="text-base font-extrabold tracking-tight" style={{ color: 'var(--df-text)' }}>
                  Docu
                </span>
                <span className="text-base font-extrabold tracking-tight" style={{ color: 'var(--df-accent)' }}>
                  Flow
                </span>
              </div>
            </div>

            {/* Theme toggle */}
            <button
              onClick={toggle}
              title={theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}
              className="w-7 h-7 rounded-md flex items-center justify-center transition-colors"
              style={{ color: 'var(--df-muted)' }}
              onMouseEnter={e => (e.currentTarget.style.background = 'rgba(128,128,128,0.1)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              {theme === 'dark'
                ? <Sun className="w-3.5 h-3.5" />
                : <Moon className="w-3.5 h-3.5" />
              }
            </button>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {NAV.map(({ href, icon: Icon, label }) => {
            const active = pathname === href || pathname.startsWith(href + '/')
            return (
              <Link
                key={href}
                href={href}
                className={clsx('sidebar-link', active && 'sidebar-link-active')}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                <span>{label}</span>
              </Link>
            )
          })}
        </nav>

        {/* User section */}
        <div
          className="px-3 pb-4 pt-3"
          style={{ borderTop: '1px solid var(--df-sidebar-border)' }}
        >
          <button
            onClick={() => setUserMenuOpen(v => !v)}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 transition-colors"
            style={{ color: 'var(--df-text)' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(128,128,128,0.07)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ background: 'var(--df-border)' }}
            >
              <User className="w-3.5 h-3.5" style={{ color: 'var(--df-muted)' }} />
            </div>
            <div className="flex-1 text-left min-w-0">
              <p className="text-xs font-medium truncate" style={{ color: 'var(--df-text)' }}>
                {session?.user?.email}
              </p>
              <p className="text-[10px] uppercase tracking-widest font-mono" style={{ color: planColor }}>
                {(session?.user as any)?.plan ?? 'free'}
              </p>
            </div>
            <ChevronDown
              className={clsx('w-3.5 h-3.5 transition-transform', userMenuOpen && 'rotate-180')}
              style={{ color: 'var(--df-muted)' }}
            />
          </button>

          {userMenuOpen && (
            <div className="mt-1 space-y-0.5">
              <button
                onClick={() => signOut({ callbackUrl: '/login' })}
                className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-red-400 transition-colors"
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(239,68,68,0.1)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <LogOut className="w-3.5 h-3.5" />
                Cerrar sesión
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto" style={{ backgroundColor: 'var(--df-base)' }}>
        {children}
      </main>
    </div>
  )
}
