/** This gameweek's price change: green ▲ or red ▼, nothing if unchanged. */
export function PriceMove({ change, long = false }: { change?: number; long?: boolean }) {
  if (!change) return null;
  const amount = `£${(Math.abs(change) / 10).toFixed(1)}m`;
  return (
    <span className={change > 0 ? "text-good" : "text-bad"} title={`Price ${change > 0 ? "rose" : "fell"} ${amount} this gameweek`}>
      {long ? ` · price ${change > 0 ? "▲ up" : "▼ down"} ${amount} this GW` : ` ${change > 0 ? "▲" : "▼"}${(Math.abs(change) / 10).toFixed(1)}`}
    </span>
  );
}
