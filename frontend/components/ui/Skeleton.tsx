import clsx from 'clsx'

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        'rounded-md bg-[#1e2d40]/50 animate-pulse',
        className
      )}
    />
  )
}

export function CardSkeleton() {
  return (
    <div className="df-card p-5 space-y-3">
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  )
}

export function TableRowSkeleton() {
  return (
    <tr className="border-b border-[#1e2d40]">
      {[1, 2, 3, 4, 5].map(i => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  )
}
