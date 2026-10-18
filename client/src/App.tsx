import { useEffect, useState } from 'react'
import { EvidenceProvider } from './components/EvidenceContext'
import { ReplayDataProvider } from './features/replay/ReplayDataContext'
import { Sidebar, type ViewId } from './components/Sidebar'
import { StatusPill } from './components/StatusPill'
import { ReplayView } from './views/ReplayView'
import { ReviewView } from './views/ReviewView'
import { BfiInsightsView } from './views/BfiInsightsView'
import { CurrentView } from './views/CurrentView'
import { InvestigateView } from './views/InvestigateView'
import './App.css'

type RouteId = ViewId | 'investigate'

const VIEWS: ViewId[] = ['current', 'bfi', 'replay', 'review']

function viewFromHash(): RouteId {
  const raw = window.location.hash.replace('#/', '').split('?')[0]
  if (raw === 'investigate') return 'investigate'
  const id = raw as ViewId
  return VIEWS.includes(id) ? id : 'current'
}

const TITLES: Record<RouteId, string> = {
  current: 'Current conditions',
  bfi: 'Bloom favorability',
  replay: 'X-Ray the Bay',
  review: 'Analyst review',
  investigate: 'Model validation',
}

function App() {
  const [view, setView] = useState<RouteId>(viewFromHash)

  useEffect(() => {
    const onHash = () => setView(viewFromHash())
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
        <Sidebar current={view === 'investigate' ? 'replay' : view} />
        <div className="shell__body">
          <header className="topbar">
            <div>
              <p className="topbar__eyebrow">Lower Fox River · Green Bay</p>
              <h1 className="topbar__title">{TITLES[view]}</h1>
            </div>
            {view === 'current' ? (
              <p className="status-pill status-pill--live" role="status">
                <span className="status-pill__dot" aria-hidden="true" />
                USGS observations
              </p>
            ) : view === 'replay' ? (
              <p className="status-pill status-pill--live" role="status">
                <span className="status-pill__dot" aria-hidden="true" />
                Sentinel-2 + USGS
              </p>
            ) : view === 'review' ? (
              <p className="status-pill status-pill--live" role="status">
                <span className="status-pill__dot" aria-hidden="true" />
                Live scoring &amp; review
              </p>
            ) : view === 'bfi' ? (
              <p className="status-pill status-pill--live" role="status">
                <span className="status-pill__dot" aria-hidden="true" />
                USGS + scientific literature
              </p>
            ) : view === 'investigate' ? (
              <p className="status-pill" role="status">
                FLAMe field study · 2025
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
            {view === 'investigate' && <InvestigateView />}
          </main>
          <footer className="shell__footer">
            {view === 'current'
              ? 'Provisional USGS measurements. Fluorescence shows algae pigments—not a confirmed harmful bloom.'
              : view === 'review'
                ? 'Analyst feedback can update the bloom score model. Not a regulatory decision.'
                : view === 'bfi'
                  ? 'Favorability from recent conditions and published references. Not a bloom forecast.'
                  : view === 'replay'
                    ? 'Recent satellite predictions with acquisition dates. Experimental fluorescence estimates, not confirmed harmful blooms.'
                    : view === 'investigate'
                      ? 'Validation against withheld 2025 boat measurements. Not a live bloom assessment.'
                      : 'Experimental estimates · not a bloom advisory.'}
          </footer>
        </div>
      </div>
      </EvidenceProvider>
    </ReplayDataProvider>
  )
}

export default App
