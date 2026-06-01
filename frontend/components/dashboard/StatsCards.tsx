'use client'

import { useEffect, useState } from 'react'
import { FileText, CheckCircle, Clock, AlertCircle, TrendingUp } from 'lucide-react'
import { fetchStats, fetchActivity } from '@/lib/api'
import type { Stats, ActivityData } from '@/types'
import { CardSkeleton } from '@/components/ui/Skeleton'
import {
  AreaChart, Area, ResponsiveContainer, Tooltip, XAxis,
  PieChart, Pie, Cell, Legend
} from 'recharts'
import { format, parseISO } from 'date-fns'
import { es } from 'date-fns/locale'

const TYPE_COLORS: Record<string, string> = {
  pdf:  '#00c2ff',
  docx: '#a855f7',
  xlsx: '#10b981',
}

function StatCard({
  label, value, icon: Icon, colorClass, sub
}: {
  label: string
  value: number | string
  icon: React.ComponentType<{ className?: string }>
  colorClass: string
  sub?: string
}) {
  return (
    <div className="df-card p-5 relative overflow-hidden group hover:border-[var(--df-border-bright)] transition-colors">
      <div className="relative">
        <div className="flex items-start justify-between mb-3">
          <p className="text-xs font-mono uppercase tracking-widest" style={{ color: 'var(--df-muted)' }}>{label}</p>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colorClass}-bg`}>
            <Icon className={`w-4 h-4 ${colorClass}-icon`} />
          </div>
        </div>
        <p className="text-3xl font-bold tracking-tight" style={{ color: 'var(--df-text)' }}>{value}</p>
        {sub && <p className="text-xs mt-1" style={{ color: 'var(--df-muted)' }}>{sub}</p>}
      </div>
    </div>
  )
}

function DocTypePie({ byType }: { byType: Record<string, number> }) {
  const data = Object.entries(byType)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name: name.toUpperCase(), value }))

  if (data.length === 0) return (
    <div className="flex items-center justify-center h-full">
      <p className="text-xs" style={{ color: 'var(--df-muted)' }}>Sin datos aún</p>
    </div>
  )

  return (
    <ResponsiveContainer width="100%" height={110}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={28}
          outerRadius={44}
          paddingAngle={3}
          dataKey="value"
        >
          {data.map(({ name }) => (
            <Cell
              key={name}
              fill={TYPE_COLORS[name.toLowerCase()] ?? '#5a7a96'}
              stroke="transparent"
            />
          ))}
        </Pie>
        <Legend
          iconType="circle"
          iconSize={7}
          formatter={(v) => (
            <span style={{ color: 'var(--df-muted)', fontSize: 11, fontFamily: 'monospace' }}>{v}</span>
          )}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--df-tooltip-bg)',
            border: '1px solid var(--df-tooltip-border)',
            borderRadius: 8,
            fontSize: 12,
            color: 'var(--df-text)',
          }}
          formatter={(v: number, name: string) => [v, name]}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}

export default function StatsCards() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [activity, setActivity] = useState<ActivityData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([fetchStats(), fetchActivity(14)])
      .then(([s, a]) => { setStats(s); setActivity(a) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[0,1,2,3].map(i => <CardSkeleton key={i} />)}
      </div>
    </div>
  )

  if (!stats) return null

  const successRate = stats.total > 0 ? Math.round((stats.done / stats.total) * 100) : 0

  // Build chart data: use real activity if available, format labels
  const chartData = activity?.points?.map(p => ({
    d: format(parseISO(p.date), 'dd/MM', { locale: es }),
    v: p.count,
  })) ?? []

  const totalActivity = activity?.total ?? 0

  return (
    <div className="space-y-4">
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total docs"
          value={stats.total}
          icon={FileText}
          colorClass="cyan"
          sub="Todos los tiempos"
        />
        <StatCard
          label="Procesados hoy"
          value={stats.today ?? 0}
          icon={CheckCircle}
          colorClass="emerald"
          sub={`${successRate}% tasa de éxito`}
        />
        <StatCard
          label="Tiempo promedio"
          value={stats.avg_processing_time ? `${stats.avg_processing_time}s` : '—'}
          icon={Clock}
          colorClass="amber"
          sub="Por documento"
        />
        <StatCard
          label="Con errores"
          value={stats.failed}
          icon={AlertCircle}
          colorClass="red"
          sub="Requieren atención"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Activity area chart — 2/3 width */}
        <div className="df-card p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-xs font-mono uppercase tracking-widest" style={{ color: 'var(--df-muted)' }}>
                Actividad reciente
              </p>
              <p className="text-sm font-semibold mt-0.5" style={{ color: 'var(--df-text)' }}>
                Documentos por día — últimos 14 días
              </p>
            </div>
            <div className="flex items-center gap-1.5 text-xs font-mono" style={{ color: 'var(--df-green, #10b981)' }}>
              <TrendingUp className="w-3.5 h-3.5" />
              {totalActivity} total
            </div>
          </div>

          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={100}>
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorV" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="var(--df-accent)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="var(--df-accent)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="d"
                  tick={{ fill: 'var(--df-muted)', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--df-tooltip-bg)',
                    border: '1px solid var(--df-tooltip-border)',
                    borderRadius: 8,
                    fontSize: 12,
                    color: 'var(--df-text)',
                  }}
                  labelStyle={{ color: 'var(--df-muted)' }}
                  itemStyle={{ color: 'var(--df-accent)' }}
                  formatter={(v: number) => [v, 'documentos']}
                />
                <Area
                  type="monotone"
                  dataKey="v"
                  stroke="var(--df-accent)"
                  strokeWidth={2}
                  fill="url(#colorV)"
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[100px] flex items-center justify-center">
              <p className="text-xs" style={{ color: 'var(--df-muted)' }}>No hay actividad en los últimos 14 días</p>
            </div>
          )}
        </div>

        {/* Document type breakdown — 1/3 width */}
        <div className="df-card p-5">
          <p className="text-xs font-mono uppercase tracking-widest mb-1" style={{ color: 'var(--df-muted)' }}>
            Por tipo
          </p>
          <p className="text-sm font-semibold mb-3" style={{ color: 'var(--df-text)' }}>
            Distribución de formatos
          </p>
          <DocTypePie byType={stats.by_type} />
          {/* Numeric breakdown */}
          <div className="mt-2 space-y-1.5">
            {Object.entries(stats.by_type).filter(([, v]) => v > 0).map(([type, count]) => (
              <div key={type} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ background: TYPE_COLORS[type] ?? '#5a7a96' }}
                  />
                  <span className="font-mono uppercase" style={{ color: 'var(--df-muted)' }}>{type}</span>
                </div>
                <span className="font-semibold" style={{ color: 'var(--df-text)' }}>{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Category breakdown */}
        {stats.by_category && Object.keys(stats.by_category).length > 0 && (
          <div className="df-card p-5">
            <p className="text-xs font-mono uppercase tracking-widest mb-1" style={{ color: 'var(--df-muted)' }}>
              Por categoría
            </p>
            <p className="text-sm font-semibold mb-3" style={{ color: 'var(--df-text)' }}>
              Distribución IA
            </p>
            <div className="space-y-2">
              {Object.entries(stats.by_category)
                .sort(([,a],[,b]) => (b as number) - (a as number))
                .slice(0, 6)
                .map(([cat, count]) => {
                  const pct = stats.total > 0 ? Math.round(((count as number) / stats.total) * 100) : 0
                  return (
                    <div key={cat}>
                      <div className="flex justify-between text-xs mb-0.5">
                        <span className="capitalize" style={{ color: 'var(--df-muted)' }}>{cat}</span>
                        <span className="font-mono" style={{ color: 'var(--df-text)' }}>{count as number}</span>
                      </div>
                      <div className="h-1 rounded-full bg-[#1e2d40]">
                        <div
                          className="h-1 rounded-full bg-gradient-to-r from-[#00c2ff] to-[#a855f7]"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )
                })
              }
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
