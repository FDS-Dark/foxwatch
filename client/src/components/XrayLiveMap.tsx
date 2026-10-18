import { useEffect, useRef, useState } from 'react'
import { ImageOverlay, MapContainer, Popup, TileLayer, useMap, useMapEvents, ZoomControl } from 'react-leaflet'
import type { LiveSample, LiveSnapshot } from '@/models/xrayLive'
import { fetchLiveSample, xrayResourceUrl } from '@/services/xrayService'

const date = (value: string) => new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })

function MapBehavior({ snapshot, focus }: { snapshot: LiveSnapshot; focus: number }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds(snapshot.layers[0].bounds, { padding: [18, 18] })
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

function Inspect({ snapshot }: { snapshot: LiveSnapshot }) {
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
    <span className="eyebrow">Satellite-informed prediction</span>
    {point.sample?.status === 'available' ? <>
      <strong>{point.sample.value!.toFixed(2)} <small>RFU</small></strong>
      <p>Image acquired {date(point.sample.acquired_at!)}</p>
      <p>{point.sample.outside_support ? 'Outside spatial or spectral training support.' : 'Within spatial and spectral training ranges.'} Experimental seasonal transfer.</p>
      <p>Nearest prediction cell · ~{snapshot.resolution_m} m</p>
    </> : <p>{point.error ? 'Could not inspect this location. Try again.' : point.sample ? 'No usable satellite prediction here. Land, clouds, or quality masks may exclude this location.' : 'Reading prediction…'}</p>}
    <span>{point.lat.toFixed(4)}° N · {Math.abs(point.lon).toFixed(4)}° W</span>
  </div></Popup>
}

export function XrayLiveMap({ snapshot, selected, showSupport, opacity, focus }: {
  snapshot: LiveSnapshot; selected: string; showSupport: boolean; opacity: number; focus: number
}) {
  const [failed, setFailed] = useState<string>()
  const layer = snapshot.layers.find(item => item.id === selected)!
  const support = snapshot.layers.find(item => item.id === 'support')!
  return <MapContainer className="live-bay-map" center={[45.15, -87.45]} zoom={8} zoomSnap={0.25}
    zoomDelta={0.5} zoomControl={false} scrollWheelZoom preferCanvas>
    <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors · Copernicus Sentinel-2 / Element 84" />
    <ZoomControl position="bottomright" />
    <MapBehavior snapshot={snapshot} focus={focus} />
    {selected === 'prediction' && <Inspect key={snapshot.run_id} snapshot={snapshot} />}
    <ImageOverlay url={xrayResourceUrl(layer.url)} bounds={layer.bounds} opacity={opacity}
      eventHandlers={{ error: () => setFailed(layer.url), load: () => setFailed(undefined) }} />
    {showSupport && selected === 'prediction' && <ImageOverlay url={xrayResourceUrl(support.url)} bounds={support.bounds} opacity={0.7} />}
    {failed === layer.url && <div className="live-layer-error" role="alert">The map image could not load. Check the API connection and sync again.</div>}
  </MapContainer>
}
