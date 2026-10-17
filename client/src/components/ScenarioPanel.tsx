import { useId, useState } from 'react'
import type { Scene } from '../data/types/replay'

export function ScenarioPanel({ scene }: { scene: Scene }) {
  const [reduction, setReduction] = useState(25)
  const [sensitivity, setSensitivity] = useState(0.5)
  const rid = useId()
  const sid = useId()

  const baseline = scene.proxy_mean
  const result = baseline * (1 - (sensitivity * reduction) / 100)
  const max = 0.4

  return (
    <section className="card scenario" aria-labelledby="scenario-title">
      <header className="card__header">
        <div>
          <h2 id="scenario-title" className="card__title">
            What-if: runoff reduction
          </h2>
          <p className="card__sub">
            Hypothetical. Uses an assumed linear sensitivity, not a hydrological
            model.
          </p>
        </div>
        <span className="chip chip--warn">Not validated</span>
      </header>

      <div className="slider-field">
        <label htmlFor={rid}>
          Assumed runoff reduction <output htmlFor={rid}>{reduction}%</output>
        </label>
        <input
          id={rid}
          type="range"
          min={0}
          max={60}
          step={5}
          value={reduction}
          onChange={(e) => setReduction(Number(e.target.value))}
        />
      </div>
      <div className="slider-field">
        <label htmlFor={sid}>
          Assumed sensitivity <output htmlFor={sid}>{sensitivity.toFixed(2)}</output>
        </label>
        <input
          id={sid}
          type="range"
          min={0.1}
          max={1}
          step={0.05}
          value={sensitivity}
          onChange={(e) => setSensitivity(Number(e.target.value))}
        />
      </div>

      <div className="scenario__bars" aria-live="polite">
        <div className="scenario__row">
          <span>Observed proxy</span>
          <div className="bar">
            <span
              className="bar__fill bar__fill--observed"
              style={{ width: `${(baseline / max) * 100}%` }}
            />
          </div>
          <strong>{baseline.toFixed(3)}</strong>
        </div>
        <div className="scenario__row">
          <span>Hypothetical</span>
          <div className="bar">
            <span
              className="bar__fill bar__fill--scenario"
              style={{ width: `${(result / max) * 100}%` }}
            />
          </div>
          <strong>{result.toFixed(3)}</strong>
        </div>
      </div>

      <p className="scenario__formula">
        <code>
          proxy × (1 − {sensitivity.toFixed(2)} × {reduction}/100)
        </code>{' '}
        · method <code>illustrative_linear_sensitivity_v1</code>
      </p>
    </section>
  )
}
