import { useEffect, useState } from 'react'
import { CircleMarker, ImageOverlay, MapContainer, Polyline, TileLayer, Tooltip, useMap, ZoomControl } from 'react-leaflet'
import type { Map as LeafletMap } from 'leaflet'
import type { XrayLayer, XrayObservation, XrayPosition } from '@/models/xray'
import { xrayResourceUrl } from '@/services/xrayService'
import { fluorescenceColor } from './xrayColors'

export type MapGroup = { maps: Set<LeafletMap>; syncing: boolean }

function LinkedView({ group }: { group: MapGroup }) {
  const map = useMap()
  useEffect(() => {
    group.maps.add(map)
    function sync() {
      if (group.syncing) return
      group.syncing = true
      try {
        for (const other of group.maps) {
          if (other !== map) other.setView(map.getCenter(), map.getZoom(), { animate: false })
        }
      } finally { group.syncing = false }
    }
    map.on('moveend', sync)
    return () => { map.off('moveend', sync); group.maps.delete(map) }
  }, [map, group])
  return null
}

function Bounds({ points, focusKey, bounds }: { points: XrayPosition[]; focusKey: string; bounds?: XrayLayer['bounds'] }) {
  const map = useMap()
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [15, 15] })
    else if (points.length) map.fitBounds(points.map(p => [p.lat, p.lon] as [number, number]), { padding: [65, 65], maxZoom: 13 })
    // Focus changes only when the user changes case or mode; stage updates preserve pan/zoom.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, focusKey])
  return null
}

export function XrayMap({ training, target, display, focusKey, layer, highlightId, group, showBins = true, colorTrack = false, bounds, extraLayer, displayMax = 16, targetLabel }: {
  training: XrayObservation[]
  target: XrayPosition[]
  display: (XrayPosition & { value?: number; description?: string })[]
  focusKey: string
  layer?: XrayLayer
  highlightId?: number
  group?: MapGroup
  showBins?: boolean
  colorTrack?: boolean
  bounds?: XrayLayer['bounds']
  extraLayer?: XrayLayer
  displayMax?: number
  targetLabel?: string
}) {
  const [failedLayer, setFailedLayer] = useState<string>()
  return (
    <MapContainer center={[44.7, -87.85]} zoom={10} zoomSnap={0.25} zoomDelta={0.5} preferCanvas zoomControl={false}
      className="xray-map" scrollWheelZoom={false}>
      <ZoomControl position="topright" />
      <Bounds points={target.length ? target : training} focusKey={focusKey} bounds={bounds} />
      {group && <LinkedView group={group} />}
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors · Observations: USGS FLAMe" />
      {layer && <ImageOverlay url={xrayResourceUrl(layer.url)} bounds={layer.bounds} opacity={layer.scope === 'full_fit_not_holdout' ? 0.65 : 1}
        eventHandlers={{ error: () => setFailedLayer(layer.url), load: () => setFailedLayer(undefined) }} />}
      {layer && failedLayer === layer.url && <div className="xray-layer-error" role="alert">Prediction image could not load. Restart the API and reload this page.</div>}
      {extraLayer && <ImageOverlay url={xrayResourceUrl(extraLayer.url)} bounds={extraLayer.bounds} opacity={1} />}
      {showBins && training.map(p => <CircleMarker key={`train-${p.id}`} center={[p.lat, p.lon]} radius={2.5}
        pathOptions={{ stroke: false, fillColor: fluorescenceColor(p.value, displayMax), fillOpacity: 0.75 }}>
        <Tooltip><strong>Measured: {p.value.toFixed(2)} RFU</strong><br />{p.observed_at}<br />100 m bin · {p.raw_samples} source samples</Tooltip>
      </CircleMarker>)}
      {target.length > 0 && <Polyline positions={target.map(p => [p.lat, p.lon])}
        pathOptions={{ color: '#fff', weight: 2, dashArray: '5 6', opacity: 0.85 }}>
        {targetLabel && <Tooltip permanent direction="top" opacity={0.95}>{targetLabel}</Tooltip>}
      </Polyline>}
      {colorTrack && display.slice(1).flatMap((point, i) => {
        const previous = display[i]
        if (point.value === undefined || previous.value === undefined) return []
        // Subdivide only for visual interpolation along the measured transect.
        return Array.from({ length: 8 }, (_, j) => {
          const a = j / 8, b = (j + 1) / 8
          const at = (f: number): [number, number] => [previous.lat + (point.lat - previous.lat) * f, previous.lon + (point.lon - previous.lon) * f]
          return <Polyline key={`track-${point.id}-${j}`} positions={[at(a), at(b)]}
            pathOptions={{ color: fluorescenceColor(previous.value! + (point.value! - previous.value!) * (a + b) / 2, displayMax), weight: 7, opacity: 1 }}>
            <Tooltip>Measured transect: {previous.value!.toFixed(2)} → {point.value!.toFixed(2)} RFU<br />Colors interpolate between observed bins.</Tooltip>
          </Polyline>
        })
      })}
      {showBins && display.map(p => <CircleMarker key={`point-${p.id}`} center={[p.lat, p.lon]} radius={p.id === highlightId ? 9 : 5}
        pathOptions={{ color: p.id === highlightId ? '#b9461f' : '#fff', weight: 1.5,
          fillColor: p.value === undefined ? '#647478' : fluorescenceColor(p.value, displayMax), fillOpacity: 1 }}>
        <Tooltip><strong>{p.value === undefined ? 'Withheld observation' : `${p.value.toFixed(2)} RFU`}</strong><br />{p.description}<br />{p.observed_at}</Tooltip>
      </CircleMarker>)}
    </MapContainer>
  )
}
