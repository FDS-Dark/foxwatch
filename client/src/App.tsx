import { useEffect, useState } from 'react'
import { EvidenceProvider } from './components/EvidenceContext'
import { ReplayDataProvider } from './features/replay/ReplayDataContext'
import { Sidebar, type ViewId } from './components/Sidebar'
import { StatusPill } from './components/StatusPill'
import { InvestigateView } from './views/InvestigateView'
import { ReplayView } from './views/ReplayView'
import { ReviewView } from './views/ReviewView'
import './App.css'

const VIEWS: ViewId[] = ['replay', 'investigate', 'review']

function viewFromHash(): ViewId {
  const id = window.location.hash.replace('#/', '') as ViewId
  return VIEWS.includes(id) ? id : 'replay'
}

const TITLES: Record<ViewId, string> = {
  replay: 'Historical replay',
  investigate: 'Investigate evidence',
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
            <StatusPill />
          </header>
          <main id="main" tabIndex={-1} className="shell__main">
            {view === 'replay' && <ReplayView />}
            {view === 'investigate' && <InvestigateView />}
            {view === 'review' && <ReviewView />}
          </main>
          <footer className="shell__footer">
            Historical replay for education. Satellite values are
            dimensionless proxies, not confirmed harmful algal blooms. Scenarios
            are assumptions, not forecasts.
          </footer>
        </div>
      </div>
      </EvidenceProvider>
    </ReplayDataProvider>
  )
}

export default App
