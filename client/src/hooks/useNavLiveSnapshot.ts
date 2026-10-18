import { useEffect, useState } from 'react'
import { fetchLatestObservations } from '@/services/observationsService'
import { fetchLatestPrediction } from '@/services/predictionsService'
import { predictionBucket } from '@/models/prediction'

export type NavLiveSnapshot = {
  waterTempC: number | null
  bloomPercent: number | null
  bloomLabel: string | null
}

const BLOOM_LABEL: Record<'low' | 'medium' | 'high', string> = {
  low: 'Low',
  medium: 'Moderate',
  high: 'Elevated',
}

export function useNavLiveSnapshot(pollMs = 30_000): NavLiveSnapshot | null {
  const [snap, setSnap] = useState<NavLiveSnapshot | null>(null)

  useEffect(() => {
    let stopped = false
    let timer: number | undefined

    async function load() {
      if (stopped) return
      try {
        const [obs, pred] = await Promise.allSettled([
          fetchLatestObservations(),
          fetchLatestPrediction(),
        ])
        if (stopped) return
        const readings = obs.status === 'fulfilled' ? obs.value.readings : []
        const tempRow = readings.find((r) => r.parameter_code === '00010')
        let bloomPercent: number | null = null
        let bloomLabel: string | null = null
        if (pred.status === 'fulfilled' && pred.value.status === 'available') {
          bloomPercent = Math.round(pred.value.probability * 100)
          bloomLabel = BLOOM_LABEL[predictionBucket(pred.value.probability)]
        }
        setSnap({
          waterTempC: tempRow?.value ?? null,
          bloomPercent,
          bloomLabel,
        })
      } catch {
        if (!stopped) setSnap(null)
      } finally {
        if (!stopped) timer = window.setTimeout(() => void load(), pollMs)
      }
    }

    void load()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [pollMs])

  return snap
}
