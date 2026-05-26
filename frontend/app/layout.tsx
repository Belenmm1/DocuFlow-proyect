import type { Metadata } from 'next'
import './globals.css'
import Providers from './providers'
import { THEME_SCRIPT } from '@/lib/theme'

export const metadata: Metadata = {
  title: 'DocuFlow — Procesamiento Inteligente de Documentos',
  description: 'Analizá, extraé y chateá con tus documentos usando IA.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        {/* Run before React hydrates to avoid flash of wrong theme */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=Space+Mono:wght@400;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
