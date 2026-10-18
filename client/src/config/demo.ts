/** Demo constants — replace with route params when timeline API lands (Owner B). */
export const DEMO_SCENE_ID = 'sentinel_scene_001'

export const TAXONOMY_OPTIONS = [
  {
    value: 'proxy_elevated_plausible' as const,
    label: 'Proxy elevated (plausible)',
    hint: 'Water-color signal looks elevated; not lab chlorophyll.',
  },
  {
    value: 'proxy_elevated_rejected' as const,
    label: 'Proxy elevated (rejected)',
    hint: 'Disagree with ML flag for this scene.',
  },
  {
    value: 'uncertain_quality' as const,
    label: 'Uncertain quality',
    hint: 'Cloud/mask/coverage limits interpretation.',
  },
  {
    value: 'context_only' as const,
    label: 'Context only',
    hint: 'Notes only; no anomaly claim.',
  },
]
