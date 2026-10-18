const dayFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
})

export function formatDay(iso: string): string {
  return dayFormatter.format(new Date(iso))
}

/** Map normalized proxy intensity to a blue-to-green-to-yellow color ramp. */
export function proxyColor(value: number): string {
  const intensity = Math.max(0, Math.min(1, value))
  const hue = 200 - intensity * 145
  return `hsl(${hue}, 75%, 50%)`
}
