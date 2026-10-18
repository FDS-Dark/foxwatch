export type ViewId = 'current' | 'replay' | 'investigate' | 'bfi' | 'review'

const NAV: { id: ViewId; label: string; hint: string; icon: string }[] = [
  {
    id: 'current',
    label: 'Current conditions',
    hint: 'Latest station readings',
    icon: 'M3 12h3l3-8 4 16 3-8h5',
  },
  {
    id: 'replay',
    label: 'X-Ray the Bay',
    hint: 'Latest satellite predictions',
    icon: 'M3 12h3l3-8 4 16 3-8h5',
  },
  {
    id: 'investigate',
    label: 'Investigate',
    hint: 'Ask with cited evidence',
    icon: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm9 16-4.3-4.3',
  },
  {
    id: 'bfi',
    label: 'BFI insights',
    hint: 'Drivers + RAG + Gemini',
    icon: 'M4 6h16v4H4V6Zm0 6h10v4H4v-4Z',
  },
  {
    id: 'review',
    label: 'Review & retrain',
    hint: 'Human-in-the-loop',
    icon: 'M4 12l5 5L20 6',
  },
]

export function Sidebar({ current }: { current: ViewId }) {
  return (
    <aside className="sidebar">
      <a href="#/replay" className="sidebar__brand" aria-label="FoxWatch home">
        <img
          className="sidebar__emblem"
          src="/foxwatch-emblem.png"
          alt=""
          width={463}
          height={440}
        />
        <img
          className="sidebar__wordmark"
          src="/foxwatch-wordmark.png"
          alt="FoxWatch"
          width={480}
          height={86}
        />
        <span className="sidebar__tagline">
          Watershed intelligence &amp; incident response
        </span>
      </a>

      <nav aria-label="Primary">
        <ul className="nav">
          {NAV.map((item, i) => (
            <li key={item.id}>
              <a
                href={`#/${item.id}`}
                className="nav__link"
                aria-current={current === item.id ? 'page' : undefined}
              >
                <span className="nav__step" aria-hidden="true">
                  {i + 1}
                </span>
                <svg
                  className="nav__icon"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path d={item.icon} />
                </svg>
                <span className="nav__text">
                  <span className="nav__label">{item.label}</span>
                  <span className="nav__hint">{item.hint}</span>
                </span>
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {current === 'investigate' && <div className="sidebar__event">
        <p className="sidebar__event-label">Active event</p>
        <p className="sidebar__event-title">June 30–July 1, 2025</p>
        <span className="chip chip--candidate">FLAMe · historical research</span>
      </div>}

      <svg
        className="sidebar__waves"
        viewBox="0 0 400 120"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          className="wave wave--1"
          d="M0 60 Q 50 40 100 60 T 200 60 T 300 60 T 400 60 V120 H0Z"
        />
        <path
          className="wave wave--2"
          d="M0 75 Q 50 55 100 75 T 200 75 T 300 75 T 400 75 V120 H0Z"
        />
        <path
          className="wave wave--3"
          d="M0 90 Q 50 72 100 90 T 200 90 T 300 90 T 400 90 V120 H0Z"
        />
      </svg>
    </aside>
  )
}
