/** Parses #rgb or #rrggbb into [r, g, b] (0–255). */
export function parseHex(hex: string): [number, number, number] | null {
  let c = hex.trim().replace(/^#/, '');
  if (c.length === 3) c = [...c].map((ch) => ch + ch).join('');
  if (!/^[0-9a-f]{6}$/i.test(c)) return null;
  return [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16)) as [number, number, number];
}

export function relativeLuminance(hex: string): number {
  const rgb = parseHex(hex);
  if (!rgb) return 0;
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const l1 = relativeLuminance(a);
  const l2 = relativeLuminance(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

export type ContrastLevel = 'ok' | 'moderate' | 'low';

/** Same thresholds as the QuickeR app. */
export function contrastLevel(foreground: string, background: string): ContrastLevel {
  const ratio = contrastRatio(foreground, background);
  if (ratio < 2) return 'low';
  if (ratio < 2.5) return 'moderate';
  return 'ok';
}
