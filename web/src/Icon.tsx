// Monochrome 16px line icons (currentColor, 1.5px stroke) so they inherit the text colour of the dark theme.
const PATHS: Record<string, string> = {
  shield: 'M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6l7-3z',
  undo: 'M9 14L4 9l5-5M4 9h10a6 6 0 010 12h-3',
  flag: 'M5 21V4M5 4h12l-2 4 2 4H5',
  scale: 'M12 3v18M4 7h16M6 7l-3 7a3 3 0 006 0L6 7M18 7l-3 7a3 3 0 006 0l-3-7M8 21h8',
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  search: 'M11 4a7 7 0 100 14 7 7 0 000-14zM20 20l-4-4',
  refresh: 'M20 12a8 8 0 01-14 5.3M4 12a8 8 0 0114-5.3M4 4v5h5M20 20v-5h-5',
  plus: 'M12 5v14M5 12h14',
  download: 'M12 4v11M7 10l5 5 5-5M4 19h16',
  check: 'M5 12l5 5L20 7',
  x: 'M6 6l12 12M18 6L6 18',
  ban: 'M12 3a9 9 0 100 18 9 9 0 000-18zM5.5 5.5l13 13',
  arrowUp: 'M12 19V5M5 12l7-7 7 7',
  arrowUpRight: 'M7 17L17 7M8 7h9v9',
  file: 'M14 3H7a1 1 0 00-1 1v16a1 1 0 001 1h10a1 1 0 001-1V8l-5-5zM14 3v5h5M9 13h6M9 17h6',
  pause: 'M8 5v14M16 5v14',
  play: 'M7 4l12 8-12 8z',
  send: 'M21 3L10 14M21 3l-7 18-4-7-7-4 18-7z',
  lock: 'M6 11V8a6 6 0 0112 0v3M5 11h14v10H5z',
  chevron: 'M6 9l6 6 6-6',
  sort: 'M8 4v16M8 20l-3-3M8 20l3-3M16 20V4M16 4l-3 3M16 4l3 3',
  sortAsc: 'M12 19V5M5 12l7-7 7 7',
  sortDesc: 'M12 5v14M5 12l7 7 7-7',
  expand: 'M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7',
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0',
  logout: 'M15 17l5-5-5-5M20 12H9M13 21H5a1 1 0 01-1-1V4a1 1 0 011-1h8',
  login: 'M9 7l-5 5 5 5M4 12h11M11 3h8a1 1 0 011 1v16a1 1 0 01-1 1h-8',
  sparkle: 'M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6zM19 15l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2',
  book: 'M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2V5zM4 19a2 2 0 012-2h13',
  alert: 'M12 3l10 18H2L12 3zM12 10v5M12 18v.5',
  clock: 'M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3 3',
  bolt: 'M13 2L4 14h7l-1 8 9-12h-7l1-8z',
  info: 'M12 3a9 9 0 100 18 9 9 0 000-18zM12 11v5M12 8v.5',
  dots: 'M5 12h.01M12 12h.01M19 12h.01',
  mail: 'M3 6h18v12H3zM3 6l9 7 9-7',
}
const ALIAS: Record<string, string> = { 'arrow-up': 'arrowUpRight', 'sort-asc': 'sortAsc', 'sort-desc': 'sortDesc' }

export function Icon({ name, size = 16, className = '' }: { name: string; size?: number; className?: string }) {
  const d = PATHS[ALIAS[name] ?? name] ?? PATHS.grid
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}



// Icon for a command-bar / pane action: YAML `icon:` wins, otherwise infer from the action id.
export function actionIcon(id: string, icon: string | null, destructive: boolean): string {
  if (icon) return icon
  if (destructive) return 'ban'
  if (/approve|resolve|clear|resume|accept|won/.test(id)) return 'check'
  if (/reject|deny|lost/.test(id)) return 'x'
  if (/escalat/.test(id)) return 'arrowUpRight'
  if (/doc|evidence|info|request/.test(id)) return 'file'
  if (/hold|pause|freeze/.test(id)) return 'pause'
  if (/payout|send|submit|represent/.test(id)) return 'send'
  if (/enable|on\b/.test(id)) return 'bolt'
  if (/disable|off\b/.test(id)) return 'ban'
  return 'check'
}
