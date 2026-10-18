import { useEffect, useState } from 'react'
import { EvidenceProvider } from './components/EvidenceContext'
import { ReplayDataProvider } from './features/replay/ReplayDataContext'
import { Sidebar, type ViewId } from './components/Sidebar'
import { StatusPill } from './components/StatusPill'
import { ReplayView } from './views/ReplayView'
import { ReviewView } from './views/ReviewView'
import { BfiInsightsView } from './views/BfiInsightsView'
import { CurrentView } from './views/CurrentView'
import './App.css'

const VIEWS: ViewId[] = ['current', 'bfi', 'replay', 'review']

function viewFromHash(): ViewId {
  const raw = window.location.hash.replace('#/', '').split('?')[0]
  if (raw === 'investigate') return 'bfi'
  const id = raw as ViewId
  return VIEWS.includes(id) ? id : 'current'
}

const TITLES: Record<ViewId, string> = {
  current: 'Current conditions',
  bfi: 'Bloom favorability',
  replay: 'Bay survey replay',
  review: 'Analyst review',
}

function App() {
  const [view, setView] = useState<ViewId>(viewFromHash)

  useEffect(() => {
    const onHash = () => {
      const raw = window.location.hash.replace('#/', '').split('?')[0]
      if (raw === 'investigate') {
        const rest = window.location.hash.includes('?') ? window.location.hash.split('?').slice(1).join('?') : ''
        window.location.replace(`#/bfi${rest ? `?${rest}` : ''}`)
        return
      }
      setView(viewFromHash())
    }
    onHash()
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    document.title = `${TITLES[view]} · FoxWatch`
    window.scrollTo(0, 0)
    document.getElementById('main')?.focus({ preventScroll: true })
  }, [view])

  return (
    <ReplayDataProvider>
      <EvidenceProvider>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="shell">
        <Sidebar current={view} />
        <div className="shell__body">
          <header className="topbar">
            <div>
              <p className="topbar__eyebrow">Lower Fox River · Green Bay</p>
              <h1 className="topbar__title">{TITLES[view]}</h1>
            </div>
            {view === 'current' ? (
              <p className="status-pill status-pill--live" role="status">
                <span className="status-pill__dot" aria-hidden="true" />
                Live station data
              </p>
            ) : view === 'replay' ? (
              <p className="status-pill">June 2025 study · archived</p>
            ) : view === 'review' ? (
              <p className="status-pill status-pill--live" role="status">
                <span className="status-pill__dot" aria-hidden="true" />
                Live scoring &amp; review
              </p>
            ) : view === 'bfi' ? (
              <p className="status-pill status-pill--live" role="status">
                <span className="status-pill__dot" aria-hidden="true" />
                Live drivers &amp; summary
              </p>
            ) : (
              <StatusPill />
            )}
          </header>
          <main id="main" tabIndex={-1} className="shell__main">
            {view === 'current' && <CurrentView />}
            {view === 'replay' && <ReplayView />}
            {view === 'bfi' && <BfiInsightsView />}
            {view === 'review' && <ReviewView />}
          </main>
          <footer className="shell__footer">
            {view === 'current'
              ? 'Provisional USGS measurements. Fluorescence shows algae pigments—not a confirmed harmful bloom.'
              : view === 'review'
                ? 'Analyst feedback can update the bloom score model. Not a regulatory decision.'
                : view === 'bfi'
                  ? 'Favorability from recent conditions and published references. Not a bloom forecast.'
                  : view === 'replay'
                    ? 'Archived 2025 survey data for learning—not today’s conditions.'
                    : 'Indicators are not confirmed harmful algal blooms or official advisories.'}
          </footer>
        </div>
      </div>
      </EvidenceProvider>
    </ReplayDataProvider>
  )
}

export default App
