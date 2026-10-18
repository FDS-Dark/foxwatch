import { useEffect, useRef, useState } from 'react'
import { ImageOverlay, MapContainer, Popup, TileLayer, useMap, useMapEvents, ZoomControl } from 'react-leaflet'
import type { ExplanationSelection, LiveSample, LiveSnapshot } from '@/models/xrayLive'
import { fetchLiveSample, xrayResourceUrl } from '@/services/xrayService'

const date = (value: string) => new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })

function MapBehavior({ snapshot, focus }: { snapshot: LiveSnapshot; focus: number }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds(snapshot.region?.bounds ?? snapshot.layers[0].bounds, { padding: [18, 18] })
    // Updating a snapshot preserves the user's current view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, focus])
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}

function Inspect({ snapshot, onExplain }: { snapshot: LiveSnapshot; onExplain: (selection: ExplanationSelection) => void }) {
  const map = useMap()
  const [point, setPoint] = useState<{ lat: number; lon: number; sample?: LiveSample; error?: boolean }>()
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  useMapEvents({ click(event) {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    const { lat, lng: lon } = event.latlng
    setPoint({ lat, lon })
    fetchLiveSample(snapshot.run_id, lat, lon, request.signal).then(sample => {
      if (!request.signal.aborted) setPoint({ lat, lon, sample })
    }).catch(() => { if (!request.signal.aborted) setPoint({ lat, lon, error: true }) })
  } })
  if (!point) return null
  return <Popup position={[point.lat, point.lon]}><div className="live-map-popup">
    <span className="eyebrow">Predicted fluorescence</span>
    {point.sample?.status === 'available' ? <>
      <strong>{point.sample.value!.toFixed(2)} <small>RFU</small></strong>
      <p>Image acquired {date(point.sample.acquired_at!)}</p>
      <p>{point.sample.outside_support ? 'Outside training support.' : 'Within training ranges.'}</p>
      <p>~{snapshot.resolution_m} m grid</p>
      <button className="btn live-explain-trigger" onClick={() => { map.closePopup(); onExplain({ runId: snapshot.run_id, lat: point.lat, lon: point.lon, sample: point.sample! }) }}>Explain this location ↗</button>
    </> : <p>{point.error ? 'Could not inspect this location. Try again.' : point.sample ? 'No usable prediction at this location.' : 'Reading prediction…'}</p>}
    <span>{point.lat.toFixed(4)}° N · {Math.abs(point.lon).toFixed(4)}° W</span>
  </div></Popup>
}

export function XrayLiveMap({ snapshot, selected, showSupport, opacity, focus, onExplain }: {
  snapshot: LiveSnapshot; selected: string; showSupport: boolean; opacity: number; focus: number
  onExplain: (selection: ExplanationSelection) => void
}) {
  const [failed, setFailed] = useState<string>()
  const layer = snapshot.layers.find(item => item.id === selected)!
  const support = snapshot.layers.find(item => item.id === 'support')!
  return <MapContainer className="live-bay-map" center={[45.15, -87.45]} zoom={8} zoomSnap={0.25}
    zoomDelta={0.5} zoomControl={false} scrollWheelZoom preferCanvas>
    <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors · Copernicus Sentinel-2 / Element 84" />
    <ZoomControl position="bottomright" />
    <MapBehavior snapshot={snapshot} focus={focus} />
    {selected === 'prediction' && <Inspect key={snapshot.run_id} snapshot={snapshot} onExplain={onExplain} />}
    <ImageOverlay url={xrayResourceUrl(layer.url)} bounds={layer.bounds} opacity={opacity}
      eventHandlers={{ error: () => setFailed(layer.url), load: () => setFailed(undefined) }} />
    {showSupport && selected === 'prediction' && <ImageOverlay url={xrayResourceUrl(support.url)} bounds={support.bounds} opacity={0.7} />}
    {failed === layer.url && <div className="live-layer-error" role="alert">Could not load the map. Try refreshing.</div>}
  </MapContainer>
}
