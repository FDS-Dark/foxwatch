import { useEffect, useState } from 'react'
import { EvidenceProvider } from './components/EvidenceContext'
import { ReplayDataProvider } from './features/replay/ReplayDataContext'
import { Sidebar, type ViewId } from './components/Sidebar'
import { InvestigateView } from './views/InvestigateView'
import { ReplayView } from './views/ReplayView'
import { ReviewView } from './views/ReviewView'
import { BfiInsightsView } from './views/BfiInsightsView'
import { CurrentView } from './views/CurrentView'
import './App.css'

const VIEWS: ViewId[] = ['current', 'replay', 'investigate', 'bfi', 'review']

function viewFromHash(): ViewId {
  const id = window.location.hash.replace('#/', '').split('?')[0] as ViewId
  return VIEWS.includes(id) ? id : 'replay'
}

const TITLES: Record<ViewId, string> = {
  current: 'Current conditions',
  replay: 'X-Ray the Bay',
  investigate: 'Model validation',
  bfi: 'Bloom conditions',
  review: 'Review & retrain',
}

function App() {
  const [view, setView] = useState<ViewId>(viewFromHash)

  useEffect(() => {
    const onHash = () => setView(viewFromHash())
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
            <p className="status-pill">{{
              current: 'USGS observations',
              replay: 'Sentinel-2 + USGS',
              investigate: 'FLAMe · June 30–July 1, 2025',
              bfi: 'USGS + scientific literature',
              review: 'Station model',
            }[view]}</p>
          </header>
          <main id="main" tabIndex={-1} className="shell__main">
            {view === 'current' && <CurrentView />}
            {view === 'replay' && <ReplayView />}
            {view === 'investigate' && <InvestigateView />}
            {view === 'bfi' && <BfiInsightsView />}
            {view === 'review' && <ReviewView />}
          </main>
          <footer className="shell__footer">Experimental estimates · not a bloom advisory.</footer>
        </div>
      </div>
      </EvidenceProvider>
    </ReplayDataProvider>
  )
}

export default App
