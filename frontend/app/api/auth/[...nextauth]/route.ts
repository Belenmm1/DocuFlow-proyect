import NextAuth from 'next-auth'
import CredentialsProvider from 'next-auth/providers/credentials'

declare module 'next-auth' {
  interface Session {
    accessToken: string
    user: { id: string; email: string; role: string; plan: string }
  }
  interface User { accessToken: string; refreshToken: string; role: string; plan: string }
}

declare module 'next-auth/jwt' {
  interface JWT { accessToken: string; refreshToken: string; role: string; plan: string }
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const handler = NextAuth({
  providers: [
    CredentialsProvider({
      name: 'credentials',
      credentials: {
        email: { label: 'Email', type: 'email' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null
        try {
          const loginRes = await fetch(`${BASE_URL}/api/v1/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: credentials.email, password: credentials.password }),
          })
          if (!loginRes.ok) return null
          const tokens = await loginRes.json()
          const meRes = await fetch(`${BASE_URL}/api/v1/auth/me`, {
            headers: { Authorization: `Bearer ${tokens.access_token}` },
          })
          if (!meRes.ok) return null
          const me = await meRes.json()
          return { id: me.id, email: me.email, role: me.role, plan: me.plan, accessToken: tokens.access_token, refreshToken: tokens.refresh_token }
        } catch { return null }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.accessToken = user.accessToken
        token.refreshToken = user.refreshToken
        token.role = user.role
        token.plan = user.plan
      }
      return token
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken
      session.user.role = token.role
      session.user.plan = token.plan
      return session
    },
  },
  pages: { signIn: '/login', error: '/login' },
  session: { strategy: 'jwt', maxAge: 30 * 60 },
  secret: process.env.NEXTAUTH_SECRET,
})

export { handler as GET, handler as POST }
