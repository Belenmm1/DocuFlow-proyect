"use client";

import { useState, useEffect } from "react";
import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function LoginPage() {
  const router = useRouter();
  const { data: session, status } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/dashboard");
    }
  }, [status, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
      });

      if (result?.error) {
        setError("Credenciales incorrectas. Verificá tu email y contraseña.");
      } else {
        router.replace("/dashboard");
      }
    } catch {
      setError("Error de conexión. Intentá de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  if (status === "loading") {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-[#c8f55a] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex">
      {/* Left panel — branding */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between p-12 border-r border-white/[0.06]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-[#c8f55a] rounded-sm flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 3h12v2H2V3zm0 4h8v2H2V7zm0 4h10v2H2v-2z" fill="#0a0a0a" />
            </svg>
          </div>
          <span className="text-white font-semibold tracking-tight text-lg">DocuFlow</span>
        </div>

        <div>
          <p className="text-white/20 text-xs font-mono uppercase tracking-widest mb-8">
            Procesamiento inteligente
          </p>
          <h1 className="text-white text-5xl font-bold leading-[1.05] tracking-tight mb-6">
            Tus documentos,<br />
            <span className="text-[#c8f55a]">analizados.</span>
          </h1>
          <p className="text-white/40 text-base leading-relaxed max-w-sm">
            Extraé entidades, generá informes y conversá con tus archivos mediante IA de última generación.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Documentos procesados", value: "1.2M+" },
            { label: "Tiempo promedio", value: "4.3s" },
            { label: "Precisión IA", value: "97.8%" },
          ].map((stat) => (
            <div key={stat.label} className="border border-white/[0.08] rounded-lg p-4">
              <p className="text-white text-xl font-bold mb-1">{stat.value}</p>
              <p className="text-white/30 text-xs leading-tight">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel — form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="flex items-center gap-3 mb-10 lg:hidden">
            <div className="w-7 h-7 bg-[#c8f55a] rounded-sm flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M2 3h12v2H2V3zm0 4h8v2H2V7zm0 4h10v2H2v-2z" fill="#0a0a0a" />
              </svg>
            </div>
            <span className="text-white font-semibold text-lg">DocuFlow</span>
          </div>

          <h2 className="text-white text-2xl font-bold mb-1">Iniciá sesión</h2>
          <p className="text-white/40 text-sm mb-8">
            ¿No tenés cuenta?{" "}
            <Link href="/register" className="text-[#c8f55a] hover:underline transition-all">
              Registrate gratis
            </Link>
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-white/60 text-xs font-medium uppercase tracking-wider mb-2">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="tu@email.com"
                className="w-full bg-white/[0.04] border border-white/[0.10] rounded-lg px-4 py-3 text-white text-sm placeholder-white/20 outline-none focus:border-[#c8f55a]/50 focus:bg-white/[0.06] transition-all"
              />
            </div>

            {/* Password */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-white/60 text-xs font-medium uppercase tracking-wider">
                  Contraseña
                </label>
                <Link
                  href="/forgot-password"
                  className="text-white/30 text-xs hover:text-white/60 transition-colors"
                >
                  ¿Olvidaste tu contraseña?
                </Link>
              </div>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  placeholder="••••••••"
                  className="w-full bg-white/[0.04] border border-white/[0.10] rounded-lg px-4 py-3 pr-11 text-white text-sm placeholder-white/20 outline-none focus:border-[#c8f55a]/50 focus:bg-white/[0.06] transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors p-1"
                  aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                >
                  {showPassword ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Error message */}
            {error && (
              <div className="flex items-start gap-2.5 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
                <svg className="mt-0.5 shrink-0" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#c8f55a] hover:bg-[#d4f870] disabled:opacity-50 disabled:cursor-not-allowed text-[#0a0a0a] font-bold text-sm rounded-lg py-3.5 transition-all duration-150 active:scale-[0.99] flex items-center justify-center gap-2 mt-2"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-[#0a0a0a]/30 border-t-[#0a0a0a] rounded-full animate-spin" />
                  Ingresando...
                </>
              ) : (
                "Ingresar"
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-white/[0.06]" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-[#0a0a0a] px-3 text-white/20 text-xs">o continuá con</span>
            </div>
          </div>

          {/* OAuth placeholders */}
          <div className="grid grid-cols-2 gap-3">
            {[
              {
                name: "Google",
                provider: "google",
                icon: (
                  <svg width="16" height="16" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                  </svg>
                ),
              },
              {
                name: "GitHub",
                provider: "github",
                icon: (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" className="text-white">
                    <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                  </svg>
                ),
              },
            ].map((provider) => (
              <button
                key={provider.provider}
                onClick={() => signIn(provider.provider, { callbackUrl: "/dashboard" })}
                className="flex items-center justify-center gap-2.5 bg-white/[0.04] hover:bg-white/[0.07] border border-white/[0.08] rounded-lg py-2.5 text-white/70 text-sm font-medium transition-all"
              >
                {provider.icon}
                {provider.name}
              </button>
            ))}
          </div>

          <p className="text-white/20 text-xs text-center mt-8">
            Al ingresar aceptás los{" "}
            <Link href="/terms" className="underline hover:text-white/40 transition-colors">
              Términos de Servicio
            </Link>{" "}
            y la{" "}
            <Link href="/privacy" className="underline hover:text-white/40 transition-colors">
              Política de Privacidad
            </Link>
            .
          </p>
        </div>
      </div>
    </div>
  );
}
