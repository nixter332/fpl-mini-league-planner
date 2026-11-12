// Grey outlines of a screen while its data loads, so the page doesn't jump when it arrives.

const Bar = ({ className = "" }: { className?: string }) => <div className={`animate-pulse rounded-lg bg-seg ${className}`} />;

/** The team screen: header, tiles, pitch and bench. */
export function TeamSkeleton({ message = "Loading your team…" }: { message?: string }) {
  const row = (n: number) => (
    <div className="flex justify-center gap-3">
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="flex w-[70px] flex-col items-center gap-1.5">
          <div className="h-9 w-9 animate-pulse rounded-full bg-white/15" />
          <div className="h-7 w-full animate-pulse rounded-md bg-white/15" />
        </div>
      ))}
    </div>
  );
  return (
    <main className="flex flex-col gap-3" role="status" aria-label={message} data-testid="skeleton">
      <Bar className="h-6 w-48" />
      <Bar className="h-4 w-64" />
      <Bar className="h-10 w-full" />
      <div className="grid grid-cols-3 gap-2">
        <Bar className="h-[62px]" />
        <Bar className="h-[62px]" />
        <Bar className="h-[62px]" />
      </div>
      <div className="flex flex-col justify-around gap-4 rounded-2xl bg-[#266B43] px-2 py-6 opacity-70">
        {row(1)}
        {row(4)}
        {row(4)}
        {row(2)}
      </div>
      <Bar className="h-[74px] w-full" />
      <div className="text-center text-xs text-text3">{message}</div>
    </main>
  );
}

/** A screen made of cards (plans, rivals, this week). */
export function CardsSkeleton({ rows = 3, message }: { rows?: number; message: string }) {
  return (
    <div className="flex flex-col gap-3" role="status" aria-label={message} data-testid="skeleton">
      <div className="text-[13px] text-text2">{message}</div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex flex-col gap-2.5 rounded-2xl border border-line bg-surface p-3.5">
          <Bar className="h-5 w-40" />
          <Bar className="h-12 w-full" />
          <Bar className="h-4 w-3/4" />
        </div>
      ))}
    </div>
  );
}
