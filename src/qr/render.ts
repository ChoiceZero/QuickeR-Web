import QRCode from 'qrcode';
import jsQR from 'jsqr';

export type ErrorCorrection = 'L' | 'M' | 'Q' | 'H';

export interface RenderOptions {
  text: string;
  errorCorrection: ErrorCorrection;
  foreground: string;
  background: string;
  logo: HTMLImageElement | null;
  /** Pixels per module. */
  boxSize?: number;
  /** Quiet zone, in modules. */
  border?: number;
}

/** Share of the module grid the logo may cover (same as the QuickeR app). */
const LOGO_MODULE_RATIO = 0.22;

/**
 * Draws a QR code on a new canvas. A logo, when given, is centered on a
 * backdrop that is aligned to the module grid, and error correction is
 * raised to H to make up for the covered modules.
 */
export function renderQr(options: RenderOptions): HTMLCanvasElement {
  const boxSize = options.boxSize ?? 10;
  const border = options.border ?? 4;
  const level = options.logo ? 'H' : options.errorCorrection;

  const qr = QRCode.create(options.text, { errorCorrectionLevel: level });
  const count = qr.modules.size;
  const sizePx = (count + border * 2) * boxSize;

  const canvas = document.createElement('canvas');
  canvas.width = sizePx;
  canvas.height = sizePx;
  const ctx = canvas.getContext('2d')!;

  ctx.fillStyle = options.background;
  ctx.fillRect(0, 0, sizePx, sizePx);
  ctx.fillStyle = options.foreground;
  for (let row = 0; row < count; row++) {
    for (let col = 0; col < count; col++) {
      if (qr.modules.get(row, col)) {
        ctx.fillRect((col + border) * boxSize, (row + border) * boxSize, boxSize, boxSize);
      }
    }
  }

  if (options.logo) {
    let logoModules = Math.floor(count * LOGO_MODULE_RATIO);
    if (logoModules % 2 === 0) logoModules -= 1;
    logoModules = Math.max(logoModules, 1);
    const logoPx = logoModules * boxSize;
    const pos = Math.floor((sizePx - logoPx) / 2);

    ctx.fillStyle = options.background;
    ctx.fillRect(pos, pos, logoPx, logoPx);

    // Fit the logo inside the square without squishing it.
    const { naturalWidth: w, naturalHeight: h } = options.logo;
    const scale = Math.min(logoPx / w, logoPx / h);
    const dw = w * scale;
    const dh = h * scale;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(options.logo, pos + (logoPx - dw) / 2, pos + (logoPx - dh) / 2, dw, dh);
  }

  return canvas;
}

/** The number of modules per side for this text and level, or null if it doesn't fit. */
export function qrVersionInfo(text: string, level: ErrorCorrection): { version: number; modules: number } | null {
  try {
    const qr = QRCode.create(text, { errorCorrectionLevel: level });
    return { version: qr.version, modules: qr.modules.size };
  } catch {
    return null;
  }
}

/**
 * Tries to read the QR code back, like a phone camera would.
 * Returns true when the decoded text matches.
 */
export function canBeScanned(canvas: HTMLCanvasElement, expected: string): boolean {
  // Decode a downscaled copy: faster, and closer to what a camera sees.
  const target = 400;
  const scale = Math.min(1, target / canvas.width);
  const w = Math.round(canvas.width * scale);
  const h = Math.round(canvas.height * scale);
  const small = document.createElement('canvas');
  small.width = w;
  small.height = h;
  const ctx = small.getContext('2d', { willReadFrequently: true })!;
  ctx.drawImage(canvas, 0, 0, w, h);
  const { data } = ctx.getImageData(0, 0, w, h);
  const result = jsQR(data, w, h, { inversionAttempts: 'dontInvert' });
  return result !== null && result.data === expected;
}
