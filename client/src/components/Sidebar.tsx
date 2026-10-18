export type ViewId = 'current' | 'bfi' | 'replay' | 'review'

const NAV: { id: ViewId; label: string; hint: string; icon: string }[] = [
  {
    id: 'current',
    label: 'Current conditions',
    hint: 'Live station & bloom score',
    icon: 'M3 12h3l3-8 4 16 3-8h5',
  },
  {
    id: 'bfi',
    label: 'Bloom favorability',
    hint: 'Drivers, summary & Q&A',
    icon: 'M4 6h16v4H4V6Zm0 6h10v4H4v-4Z',
  },
  {
    id: 'replay',
    label: 'X-Ray the Bay',
    hint: 'Latest satellite predictions',
    icon: 'M3 6l6-3 6 3 6-3v12l-6 3-6-3-6 3V6z M9 3v18 M15 6v18',
  },
  {
    id: 'review',
    label: 'Analyst review',
    hint: 'Check & improve scores',
    icon: 'M4 12l5 5L20 6',
  },
]

export function Sidebar({ current }: { current: ViewId }) {
  return (
    <aside className="sidebar">
      <a href="#/current" className="sidebar__brand" aria-label="FoxWatch home">
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
        <span className="sidebar__tagline">Water quality · Green Bay</span>
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
                <svg className="nav__icon" viewBox="0 0 24 24" aria-hidden="true">
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

      {current === 'replay' && (
        <div className="sidebar__event">
          <p className="sidebar__event-label">Live layer</p>
          <p className="sidebar__event-title">Green Bay · satellite + river</p>
          <span className="chip chip--candidate">Experimental · not advisory</span>
        </div>
      )}

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
