import { useState } from 'react'
import type { SatelliteModel, XrayLayer, XraySegment } from '@/models/xray'
import { XrayMap, type MapGroup } from './XrayMap'

export function XrayComparison({ segment, satelliteModel, bayBounds }: { segment: XraySegment; satelliteModel: SatelliteModel; bayBounds?: XrayLayer['bounds'] }) {
  const [group] = useState<MapGroup>(() => ({ maps: new Set(), syncing: false }))
  const [showBins, setShowBins] = useState(false)
  const [extent, setExtent] = useState<'bay' | 'segment'>('bay')
  const [showSupport, setShowSupport] = useState(true)
  const hasLocation = segment.stage !== 'hidden'
  const hasSatellite = segment.stage === 'satellite' || segment.stage === 'reveal'
  const reveal = segment.stage === 'reveal'
  const panels = [
    { id: 'location', title: 'Coordinates alone', subtitle: 'Location-only random forest', enabled: hasLocation,
      model: 'rf_xy' as const, prompt: 'Predict from location to fill the gap.' },
    { id: 'satellite', title: 'With satellite vision', subtitle: satelliteModel === 'gp_resid' ? 'Satellite trend + spatial GP · diagnostic' : 'Location + satellite RF · primary', enabled: hasSatellite,
      model: satelliteModel, prompt: 'Add satellite to see the second reconstruction.' },
    { id: 'truth', title: 'What the boat measured', subtitle: 'Measured transect · colors interpolate along track', enabled: reveal,
      model: undefined, prompt: 'Reveal the boat measurements to compare.' },
  ]
  const surface = segment.surfaces?.layers[satelliteModel]
  return <section className="card xray-comparison" aria-label="Three aligned model comparison maps">
    <div className="xray-map-heading"><div><h3>Can the model recover the missing plume?</h3>
      <p className="muted">Same place. Same color scale. Pan or zoom any map to move all three.</p></div>
      <div className="xray-map-options"><span className="xray-link-badge">↔ Linked maps · segment {segment.id}</span>
        <label>Map extent<select value={extent} onChange={event => setExtent(event.target.value as typeof extent)}><option value="bay">Whole bay</option><option value="segment">Hidden segment</option></select></label>
        <label><input type="checkbox" checked={showBins} onChange={event => setShowBins(event.target.checked)} />Show individual samples</label>
        <label><input type="checkbox" checked={showSupport} onChange={event => setShowSupport(event.target.checked)} />Mark extrapolation</label></div></div>
    <div className="xray-map-grid">{panels.map((panel, index) => <article key={panel.id} className={`xray-comparison-panel ${panel.enabled ? '' : 'is-sealed'}`} aria-label={panel.title}>
      <header><span className="xray-panel-number">0{index + 1}</span><div><h4>{panel.title}</h4><p>{panel.subtitle}</p></div></header>
      <div className="xray-map-frame">
        <XrayMap training={segment.training} target={segment.target} focusKey={`comparison-${segment.id}-${extent}`}
          bounds={extent === 'bay' ? bayBounds ?? segment.surfaces?.layers.rf_xy?.bounds : undefined}
          targetLabel={extent === 'bay' ? `Segment ${segment.id}` : undefined}
          showBins={showBins} colorTrack={panel.id === 'truth' && reveal && !showBins}
          group={group} layer={panel.enabled && panel.model ? segment.surfaces?.layers[panel.model] : undefined}
          extraLayer={showSupport && panel.enabled && panel.model ? segment.surfaces?.extrapolation : undefined}
          display={segment.points.map(point => ({ ...point,
            value: panel.enabled ? (panel.model ? point.predictions?.[panel.model] : point.value) : undefined,
            description: panel.enabled ? panel.subtitle : 'Withheld; value not revealed',
          }))} />
        {!panel.enabled && <div className="xray-map-seal"><strong>{panel.id === 'truth' ? 'Measurements hidden' : 'Reconstruction hidden'}</strong><span>{panel.prompt}</span></div>}
      </div>
      <footer>{panel.enabled ? panel.model ? 'Continuous gradient: predicted fluorescence · dashed line: hidden track' : 'Gradient along the boat track: measured fluorescence' : 'Dashed track: the missing 5 km segment'}</footer>
    </article>)}</div>
    <div className="xray-shared-legend"><span>Chlorophyll fluorescence</span><div><div className="xray-colorbar" /><div className="xray-scale-ticks"><span>0</span><span>4</span><span>8</span><span>12</span><span>16+ RFU</span></div></div><span>Purple = lower · yellow = higher</span></div>
    <p className="muted xray-caption">The prediction fields cover the expanded satellite footprint. Diagonal stripes mark extrapolation beyond 3 km of training evidence; uncolored water has no valid satellite input. The reveal follows the measured boat track. Choose Hidden segment to inspect the plume.</p>
    {surface && <details className="xray-surface-note"><summary>How to read the reconstructed fields</summary>
      <p>{segment.surfaces?.note} Fields are rendered on a {segment.surfaces?.resolution_m} m grid using the same held-out model fits.</p>
      <p>Continuous satellite field: {surface.scene_id}, acquired {surface.acquired_at}. Track predictions and reported errors retain each observation’s own satellite match.</p>
    </details>}
  </section>
}
