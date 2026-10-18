import { useState } from 'react'
import type { XrayMetadata, XrayObservation } from '@/models/xray'
import { XrayMap } from './XrayMap'

export function XrayBayOverview({ metadata, observations }: { metadata: XrayMetadata; observations: XrayObservation[] }) {
  const [model, setModel] = useState('rf_xysat')
  const [showSamples, setShowSamples] = useState(false)
  const [showSupport, setShowSupport] = useState(true)
  const bay = metadata.bay
  if (!bay) return <div className="card" role="status">The bay overview export is unavailable. Restart the API after generating the map export.</div>
  const layer = model === 'satellite' ? bay.satellite : bay.layers.find(item => item.id === model)
  return <section className="card xray-map-card xray-bay">
    <div className="xray-map-heading"><div><p className="eyebrow">Beyond the boat track</p><h3>Green Bay · continuous reconstruction</h3>
      <p className="muted">Historical imagery · {bay.layers[0]?.acquired_at} · full-survey fit, including extrapolation</p></div>
      <label>Map layer<select value={model} onChange={event => setModel(event.target.value)}>
        <option value="rf_xysat">Satellite-informed gradient</option><option value="rf_xy">Location-only gradient</option>
        {bay.satellite && <option value="satellite">Actual satellite imagery</option>}
      </select></label></div>
    <div className="xray-bay-controls"><label><input type="checkbox" checked={showSupport} onChange={event => setShowSupport(event.target.checked)} />Mark extrapolation beyond the survey</label>
      <label><input type="checkbox" checked={showSamples} onChange={event => setShowSamples(event.target.checked)} />Show boat measurements</label></div>
    <XrayMap training={observations} target={[]} display={[]} focusKey="bay-overview" layer={layer}
      bounds={layer?.bounds} displayMax={layer?.display_max ?? 4} showBins={showSamples} extraLayer={showSupport && model !== 'satellite' ? bay.extrapolation : undefined} />
    {model !== 'satellite' && <div className="xray-shared-legend"><span>Predicted chlorophyll fluorescence</span><div><div className="xray-colorbar" /><div className="xray-scale-ticks">{[0, .25, .5, .75, 1].map(f => <span key={f}>{(f * (layer?.display_max ?? 4)).toFixed(0)}{f === 1 ? '+ RFU' : ''}</span>)}</div></div><span>Diagonal stripes = extrapolation</span></div>}
    <div className="xray-bay-explanation"><p>{bay.note}</p><p className="muted">{bay.training_bins.toLocaleString()} training bins · {bay.resolution_m} m prediction grid · {bay.valid_cells.toLocaleString()} valid water cells. The overview color scale saturates at {layer?.display_max ?? 4} RFU to show lower-level variation; the segment experiment uses 0–16 RFU.</p></div>
    {!!bay.scenes?.length && <details className="xray-surface-note"><summary>Satellite acquisitions and coverage</summary>
      {bay.scenes.map(scene => <p key={scene.id}><a href={scene.url} target="_blank" rel="noreferrer">{scene.id} ↗</a> · {scene.acquired_at}</p>)}
    </details>}
  </section>
}
