import clsx from 'clsx'

const LABELS: Record<string, string> = {
  done: 'Listo',
  pending: 'Pendiente',
  processing: 'Procesando',
  failed: 'Error',
}

const DOTS: Record<string, string> = {
  done: 'bg-emerald-400',
  pending: 'bg-amber-400',
  processing: 'bg-cyan-400 animate-pulse',
  failed: 'bg-red-400',
}

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={clsx('status-badge', `status-${status}`)}>
      <span className={clsx('w-1.5 h-1.5 rounded-full', DOTS[status] ?? 'bg-gray-400')} />
      {LABELS[status] ?? status}
    </span>
  )
}
