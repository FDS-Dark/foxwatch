export type ViewId = 'current' | 'scan' | 'bfi' | 'recovery' | 'replay' | 'review'

const NAV: { id: ViewId; label: string; hint: string; icon: string }[] = [
  {
    id: 'current',
    label: 'Current conditions',
    hint: 'Station readings',
    icon: 'M3 12h3l3-8 4 16 3-8h5',
  },
  {
    id: 'scan',
    label: 'Condition severity',
    hint: 'Water conditions',
    icon: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 3v7M7 12H5M19 12h-2M12 7V5M12 19v-2',
  },
  {
    id: 'bfi',
    label: 'Bloom favorability',
    hint: 'Score and Q&A',
    icon: 'M4 6h16v4H4V6Zm0 6h10v4H4v-4Z',
  },
  {
    id: 'recovery',
    label: 'Incident recovery',
    hint: 'Recovery steps',
    icon: 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  {
    id: 'replay',
    label: 'X-Ray the Bay',
    hint: 'Satellite map',
    icon: 'M9 3 3 7v12l6-3 6 3 6-3V7L9 3zm0 4v13m6-10v13',
  },
  {
    id: 'review',
    label: 'Analyst review',
    hint: 'Model review',
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
        <span className="sidebar__tagline">Green Bay water monitoring</span>
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
