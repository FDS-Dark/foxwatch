import { useEffect } from 'react'
import {
  Circle,
  CircleMarker,
  MapContainer,
  Pane,
  Rectangle,
  TileLayer,
  Tooltip,
  useMap,
  ZoomControl,
} from 'react-leaflet'
import { BLOOM_SEEDS } from '../data/demo/replay'
import type { Scene } from '../data/types/replay'
import { useReplayData } from '../features/replay/ReplayDataContext'
import { proxyColor } from '../lib/format'

const GAUGE: [number, number] = [44.4486, -88.0637]

function Recenter({ center }: { center: [number, number] }) {
  const map = useMap()
  useEffect(() => {
    map.setView(center)
  }, [map, center])
  return null
}

type Props = {
  scene: Scene
  showOverlay: boolean
  opacity: number
}

export function ProxyMap({ scene, showOverlay, opacity }: Props) {
  const { mapCenter } = useReplayData()
  const intensity = scene.overlay_intensity
  const cloudy = scene.quality_flag === 'cloud_limited'

  return (
    <MapContainer
      center={mapCenter}
      zoom={11}
      minZoom={9}
      maxZoom={14}
      scrollWheelZoom={false}
      zoomControl={false}
      className="map"
      attributionControl
    >
      <ZoomControl position="topright" />
      <Recenter center={mapCenter} />
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        attribution="Imagery &copy; Esri, Maxar, Earthstar Geographics"
        maxNativeZoom={17}
      />
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
        attribution="Labels &copy; Esri"
        opacity={0.8}
      />

      {showOverlay ? (
        <Pane name="proxy" className="proxy-pane" style={{ zIndex: 420 }}>
          {BLOOM_SEEDS.map((seed, i) => (
            <Circle
              key={`${scene.scene_id}-${i}`}
              center={[seed.lat, seed.lng]}
              radius={seed.r * (0.55 + intensity * 0.8)}
              pathOptions={{
                stroke: false,
                fillColor: proxyColor(intensity * seed.w + 0.15),
                fillOpacity: opacity * (0.35 + 0.65 * seed.w * intensity),
              }}
            />
          ))}
        </Pane>
      ) : null}

      {cloudy ? (
        <Pane name="clouds" className="cloud-pane" style={{ zIndex: 430 }}>
          <Rectangle
            bounds={[
              [44.57, -88.06],
              [44.68, -87.86],
            ]}
            pathOptions={{
              stroke: false,
              fillColor: '#ffffff',
              fillOpacity: 0.7,
            }}
          />
        </Pane>
      ) : null}

      <CircleMarker
        center={GAUGE}
        radius={7}
        pathOptions={{
          color: '#ffffff',
          weight: 2,
          fillColor: '#c4502a',
          fillOpacity: 1,
        }}
      >
        <Tooltip direction="right" offset={[8, 0]} permanent>
          USGS 04085059 · De Pere
        </Tooltip>
      </CircleMarker>
    </MapContainer>
  )
}
