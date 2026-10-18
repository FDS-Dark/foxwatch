import type { ObservationReading } from '@/models/observations'

export type HeatmapLevel = 'good' | 'caution' | 'elevated' | 'missing'

export type HeatmapCell = {
  id: string
  label: string
  level: HeatmapLevel
  detail: string
  valueText?: string
}

const DRIVER_ORDER = [
  'Water temperature',
  'Orthophosphate, water, filtered',
  'Nitrate plus nitrite, water, filtered',
  'Discharge',
  'Precipitation (7-day total)',
  'Solar radiation',
] as const

const SHORT_LABEL: Record<string, string> = {
  'Water temperature': 'Temperature',
  'Orthophosphate, water, filtered': 'Phosphorus',
  'Nitrate plus nitrite, water, filtered': 'Nitrogen',
  Discharge: 'Streamflow',
  'Precipitation (7-day total)': 'Rain (7-day)',
  'Solar radiation': 'Sunlight',
}

const BLOOM_INDICATORS: Record<
  string,
  { label: string; high: number; unitHint: string }
> = {
  '32319': { label: 'Phycocyanin', high: 125, unitHint: 'RFU or ug/L' },
  '32316': { label: 'Chlorophyll', high: 100, unitHint: 'RFU or ug/L' },
}

function levelFromBfiPoints(points: number | undefined): HeatmapLevel {
  if (points === undefined || Number.isNaN(points)) return 'missing'
  if (points >= 2) return 'elevated'
  if (points === 1) return 'caution'
  return 'good'
}

function levelFromHighThreshold(value: number, high: number): HeatmapLevel {
  if (value >= high) return 'elevated'
  if (value >= high * 0.6) return 'caution'
  return 'good'
}

function formatFactorValue(factor: Record<string, unknown>): string | undefined {
  const v = factor.value
  if (v === null || v === undefined) return undefined
  const unit = String(factor.unit ?? '').trim()

  if (typeof v === 'number') {
    return `${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`
  }

  if (typeof v === 'string') {
    return `${v}${unit ? ` ${unit}` : ''}`
  }

  if (typeof v === 'object' && !Array.isArray(v)) {
    const obj = v as Record<string, unknown>
    const discharge = obj.discharge_cfs
    const median = obj.seasonal_median_cfs
    if (discharge != null && median != null) {
      const flow = Number(discharge)
      const med = Number(median)
      if (!Number.isNaN(flow) && !Number.isNaN(med)) {
        return `${flow.toLocaleString(undefined, { maximumFractionDigits: 1 })} cfs (seasonal median ${med.toLocaleString(undefined, { maximumFractionDigits: 0 })} cfs)`
      }
    }
  }

  return undefined
}

function bfiDetail(level: HeatmapLevel, points: number | undefined): string {
  if (level === 'missing') return 'No live reading for this driver'
  if (level === 'good') return 'Lower bloom favorability from this driver'
  if (level === 'caution') return 'Moderately bloom-favorable conditions'
  return `Higher bloom favorability (${points ?? 0}/2 driver points)`
}

function indicatorDetail(level: HeatmapLevel, high: number): string {
  if (level === 'missing') return 'No recent reading'
  if (level === 'good') return 'Below typical elevated-pigment range'
  if (level === 'caution') return `Approaching reference level (${high})`
  return `Above reference level (${high})`
}

export function buildConditionHeatmapCells(
  factors: Array<Record<string, unknown>> | undefined,
  readings: Map<string, ObservationReading>,
): HeatmapCell[] {
  const byFactor = new Map(factors?.map((f) => [String(f.factor ?? ''), f]))

  const driverCells: HeatmapCell[] = DRIVER_ORDER.map((factorLabel) => {
    const row = byFactor.get(factorLabel)
    const points = row ? Number(row.points) : undefined
    const level = row ? levelFromBfiPoints(points) : 'missing'
    return {
      id: factorLabel,
      label: SHORT_LABEL[factorLabel] ?? factorLabel,
      level,
      detail: bfiDetail(level, points),
      valueText: row ? formatFactorValue(row) : undefined,
    }
  })

  const indicatorCells: HeatmapCell[] = Object.entries(BLOOM_INDICATORS).map(
    ([code, meta]) => {
      const reading = readings.get(code)
      if (reading?.value == null) {
        return {
          id: code,
          label: meta.label,
          level: 'missing',
          detail: indicatorDetail('missing', meta.high),
        }
      }
      const level = levelFromHighThreshold(reading.value, meta.high)
      const unit = reading.unit?.trim()
      return {
        id: code,
        label: meta.label,
        level,
        detail: indicatorDetail(level, meta.high),
        valueText: `${reading.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`,
      }
    },
  )

  return [...driverCells, ...indicatorCells]
}
