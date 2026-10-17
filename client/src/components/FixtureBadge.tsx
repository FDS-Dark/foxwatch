export function FixtureBadge({ label = 'Demo fixture' }: { label?: string }) {
  return (
    <span
      className="chip chip--fixture"
      title="Illustrative data until real ingest is connected"
    >
      {label}
    </span>
  )
}
