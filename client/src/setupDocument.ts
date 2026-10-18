/** Document metadata (Vite still needs a minimal index.html shell). */

export function setupDocument() {
  document.title = 'FoxWatch'

  const meta = (name: string, content: string) => {
    let el = document.querySelector(`meta[name="${name}"]`)
    if (!el) {
      el = document.createElement('meta')
      el.setAttribute('name', name)
      document.head.appendChild(el)
    }
    el.setAttribute('content', content)
  }

  meta(
    'description',
    'FoxWatch: recent satellite predictions and live river observations for Green Bay.',
  )
  meta('theme-color', '#0e3b43')

  if (!document.querySelector('link[rel="icon"]')) {
    const icon = document.createElement('link')
    icon.rel = 'icon'
    icon.type = 'image/png'
    icon.href = '/foxwatch-emblem.png'
    document.head.appendChild(icon)
  }
}
