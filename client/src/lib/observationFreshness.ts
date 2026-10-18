// USGS publishes this station in roughly hourly batches. Allow transmission
// and ingestion time before marking an observation overdue.
export const OBSERVATION_STALE_AFTER_SECONDS = 2 * 60 * 60

export function isObservationStale(
  observedAt: string,
  now: number,
  staleAfterSeconds = OBSERVATION_STALE_AFTER_SECONDS,
): boolean {
  // Older API processes still advertise the previous 30-minute threshold.
  const threshold = Math.max(OBSERVATION_STALE_AFTER_SECONDS, staleAfterSeconds)
  return now - Date.parse(observedAt) > threshold * 1000
}
