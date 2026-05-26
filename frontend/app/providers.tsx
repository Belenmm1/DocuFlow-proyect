'use client'

import { SessionProvider } from 'next-auth/react'
import { Toaster, useToaster } from 'react-hot-toast'
import { ThemeProvider, useTheme } from '@/lib/theme'

function ThemedToaster() {
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <Toaster
      position="top-right"
      toastOptions={{
        style: {
          background: isDark ? '#0f1117' : '#ffffff',
          color: isDark ? '#e2e8f0' : '#1a2535',
          border: `1px solid ${isDark ? '#1e293b' : '#d1dce8'}`,
          borderRadius: '8px',
          fontSize: '13px',
        },
        success: {
          iconTheme: {
            primary: isDark ? '#22d3ee' : '#0088cc',
            secondary: isDark ? '#0f1117' : '#ffffff',
          },
        },
        error: {
          iconTheme: {
            primary: '#f87171',
            secondary: isDark ? '#0f1117' : '#ffffff',
          },
        },
      }}
    />
  )
}

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <ThemeProvider>
        {children}
        <ThemedToaster />
      </ThemeProvider>
    </SessionProvider>
  )
}
