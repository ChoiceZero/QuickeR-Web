import { argbFromHex, hexFromArgb, Hct, SchemeTonalSpot } from '@material/material-color-utilities';

/** Accent colors offered by the QuickeR app. */
export const SEED_COLORS = [
  { name: 'Blue', hex: '#1e88e5' },
  { name: 'Green', hex: '#43a047' },
  { name: 'Yellow', hex: '#ffd54c' },
  { name: 'Orange', hex: '#ff9800' },
  { name: 'Red', hex: '#ef5350' },
  { name: 'Purple', hex: '#9c27b0' },
  { name: 'Pink', hex: '#c2185b' },
  { name: 'Cyan', hex: '#00acc1' },
  { name: 'Indigo', hex: '#5c6bc0' },
  { name: 'Teal', hex: '#00897b' },
  { name: 'Lime', hex: '#7cb342' },
] as const;

const ROLES = [
  'primary', 'onPrimary', 'primaryContainer', 'onPrimaryContainer', 'inversePrimary',
  'secondary', 'onSecondary', 'secondaryContainer', 'onSecondaryContainer',
  'tertiary', 'onTertiary', 'tertiaryContainer', 'onTertiaryContainer',
  'error', 'onError', 'errorContainer', 'onErrorContainer',
  'background', 'onBackground', 'surface', 'onSurface', 'surfaceVariant', 'onSurfaceVariant',
  'surfaceDim', 'surfaceBright', 'surfaceContainerLowest', 'surfaceContainerLow',
  'surfaceContainer', 'surfaceContainerHigh', 'surfaceContainerHighest',
  'inverseSurface', 'inverseOnSurface', 'outline', 'outlineVariant', 'shadow', 'scrim', 'surfaceTint',
] as const;

const kebab = (s: string) => s.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

export type Mode = 'light' | 'dark';

/** Writes the Material 3 color roles for `seed` as --md-sys-color-* variables. */
export function applyTheme(seed: string, mode: Mode): void {
  const scheme = new SchemeTonalSpot(Hct.fromInt(argbFromHex(seed)), mode === 'dark', 0);
  const root = document.documentElement;
  for (const role of ROLES) {
    root.style.setProperty(`--md-sys-color-${kebab(role)}`, hexFromArgb(scheme[role]));
  }
  root.dataset.theme = mode;
  root.style.colorScheme = mode;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', hexFromArgb(scheme.surface));
}

const STORAGE_KEY = 'quicker-web:theme';

interface SavedTheme {
  seed?: string;
  mode?: Mode;
}

export function loadSavedTheme(): SavedTheme {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as SavedTheme;
  } catch {
    return {};
  }
}

export function saveTheme(theme: SavedTheme): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...loadSavedTheme(), ...theme }));
  } catch {
    // Storage can be blocked; the theme simply isn't remembered then.
  }
}

export function systemMode(): Mode {
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
