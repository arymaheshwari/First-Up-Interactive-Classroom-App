/**
 * HTML <canvas> answer area for pin_drop questions: a coordinate grid, or an
 * uploaded picture (T8).
 *
 * Grid mode draws axes, grid lines and labels, in grid units (y points up). Image
 * mode draws the picture letterboxed by its aspect ratio, in fractions of the image
 * (x across, y down); distances there are in image widths, so rings stay round (T8 D5).
 * Both draw pins and (after the reveal) the target with its full- and zero-credit
 * rings. With `onPick` it is interactive: tap/drag or the arrow keys place a pin.
 *
 * Kept identical in behaviour to frontend/host/src/components/question/GridCanvas.tsx
 * (the apps share no package); only the sizes and default height differ.
 *
 * Colours come from the theme's --canvas-* variables on <html> (frontend/shared/theme/
 * tokens.css defines every one, in both themes), and the canvas repaints when the theme
 * changes.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Grid, Point } from '../../types/game';

const SIZES = { label: 11, pin: 6, ownPin: 9, padLeft: 34, padBottom: 24, pad: 10 };
const MIN_LABEL_GAP = 28; // px between neighbouring axis labels
const DEFAULT_MAX_HEIGHT_VH = 0.7; // share of the viewport height — never scrolls
/** Arrow-key step on an image, as a share of its width (the same distance both ways). */
const IMAGE_KEY_STEP = 0.02;

/** The --canvas-* variables this canvas reads (tests/unit checks each is defined). */
const CANVAS_COLOR_NAMES = ['bg', 'grid', 'axis', 'label', 'pin', 'target', 'ring', 'halo'] as const;
type Colors = Record<(typeof CANVAS_COLOR_NAMES)[number], string>;

/** The zero-credit ring's opacity: at 0.9 it stays >= 3:1 on the plot in both themes. */
const ZERO_RING_ALPHA = 0.9;

function readColors(): Colors {
  const style = getComputedStyle(document.documentElement);
  return Object.fromEntries(
    CANVAS_COLOR_NAMES.map(name => [name, style.getPropertyValue(`--canvas-${name}`).trim()]),
  ) as Colors;
}

/** Bumps a counter whenever the colour theme may have changed. */
function useThemeVersion(): number {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const bump = () => setVersion(v => v + 1);
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change', bump);
    const observer = new MutationObserver(bump);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'data-theme', 'style'],
    });
    return () => {
      media.removeEventListener('change', bump);
      observer.disconnect();
    };
  }, []);
  return version;
}

/** A picture to pin on: its URL and stored pixel size (for the aspect ratio). */
export interface CanvasImage {
  url: string;
  width: number;
  height: number;
}

type ImageStatus = 'loading' | 'ready' | 'error';

/** Loads `image.url`; `retry` reloads it after a failure. */
function useImage(image: CanvasImage | undefined) {
  const [status, setStatus] = useState<ImageStatus>('loading');
  const [element, setElement] = useState<HTMLImageElement | null>(null);
  const [attempt, setAttempt] = useState(0);
  const url = image?.url;

  useEffect(() => {
    if (!url) return;
    let live = true;
    setStatus('loading');
    setElement(null);
    const img = new Image();
    img.decoding = 'async';
    img.onload = () => {
      if (!live) return;
      setElement(img);
      setStatus('ready');
    };
    img.onerror = () => live && setStatus('error');
    img.src = attempt ? `${url}${url.includes('?') ? '&' : '?'}retry=${attempt}` : url;
    return () => {
      live = false;
    };
  }, [url, attempt]);

  return { status, element, retry: () => setAttempt(a => a + 1) };
}

/**
 * Where the answer area sits on the canvas, in one shape for both modes. `scale` is
 * px per distance unit: grid units, or image widths.
 */
interface Layout {
  width: number;
  height: number;
  plotX: number;
  plotY: number;
  plotW: number;
  plotH: number;
  scale: number;
}

interface Bounds {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

/** The answer area: the grid's ranges, or [0, 1] × [0, 1] on an image. */
function boundsOf(grid: Grid | undefined): Bounds {
  return grid
    ? { xMin: grid.xMin, xMax: grid.xMax, yMin: grid.yMin, yMax: grid.yMax }
    : { xMin: 0, xMax: 1, yMin: 0, yMax: 1 };
}

function computeLayout(
  grid: Grid | undefined,
  image: CanvasImage | undefined,
  width: number,
  maxHeightVh: number,
): Layout {
  // Image mode needs no axis labels, so it only keeps the outer padding.
  const padLeft = grid ? SIZES.padLeft : SIZES.pad;
  const padBottom = grid ? SIZES.padBottom : SIZES.pad;
  const spanX = grid ? grid.xMax - grid.xMin : 1;
  const spanY = grid ? grid.yMax - grid.yMin : (image?.height ?? 1) / (image?.width ?? 1);
  const availW = Math.max(width - padLeft - SIZES.pad, 40);
  const maxPlotH = window.innerHeight * maxHeightVh - SIZES.pad - padBottom;
  let scale = availW / spanX;
  if (spanY * scale > maxPlotH) scale = Math.max(maxPlotH / spanY, 4); // letterbox
  const plotW = spanX * scale;
  return {
    width,
    height: spanY * scale + SIZES.pad + padBottom,
    plotX: padLeft + (availW - plotW) / 2,
    plotY: SIZES.pad,
    plotW,
    plotH: spanY * scale,
    scale,
  };
}

function trimFloat(n: number): number {
  return Number(n.toFixed(6));
}

function formatLabel(n: number): string {
  return String(trimFloat(n)).replace('-', '−');
}

const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max);

interface GridCanvasProps {
  /** Grid mode: the coordinate grid. Pass this or `image`. */
  grid?: Grid;
  /** Image mode (T8): the picture; points are fractions of it. */
  image?: CanvasImage;
  /** Everyone's pins (host results), drawn small. */
  pins?: Point[];
  /** This player's own pin, drawn large. */
  ownPin?: Point | null;
  target?: Point | null;
  fullRadius?: number;
  zeroRadius?: number;
  /** Makes the canvas interactive; receives the raw (unsnapped) point. */
  onPick?: (p: Point) => void;
  /** Cap on the canvas height as a share of the viewport height. */
  maxHeightVh?: number;
  label: string;
}

export function GridCanvas({
  grid,
  image,
  pins = [],
  ownPin = null,
  target = null,
  fullRadius,
  zeroRadius,
  onPick,
  maxHeightVh = DEFAULT_MAX_HEIGHT_VH,
  label,
}: GridCanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragging = useRef(false);
  const [width, setWidth] = useState(0);
  const themeVersion = useThemeVersion();
  const picture = useImage(grid ? undefined : image);
  const imageMode = !grid && !!image;
  // On an image, picking waits until the picture is on screen.
  const pickable = !!onPick && (!imageMode || picture.status === 'ready');

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const layout = width > 0 ? computeLayout(grid, image, width, maxHeightVh) : null;
  const bounds = boundsOf(grid);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !layout) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(layout.width * dpr);
    canvas.height = Math.round(layout.height * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, layout.width, layout.height);

    const colors = readColors();
    const { plotX, plotY, plotW, plotH, scale } = layout;
    // On a picture no single colour reads everywhere, so each mark is first stroked wider in
    // --canvas-halo (the opposite lightness), then in its own colour on top.
    const onPicture = !grid && !!picture.element;
    const strokeWithHalo = (color: string, width: number) => {
      if (onPicture) {
        ctx.strokeStyle = colors.halo;
        ctx.lineWidth = width + 3;
        ctx.stroke();
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.stroke();
    };
    // Grid y points up; image y points down (fractions of the height).
    const px = (x: number) => plotX + (x - bounds.xMin) * (plotW / (bounds.xMax - bounds.xMin));
    const py = grid
      ? (y: number) => plotY + (grid.yMax - y) * scale
      : (y: number) => plotY + y * plotH;

    ctx.fillStyle = colors.bg;
    ctx.fillRect(plotX, plotY, plotW, plotH);

    if (grid) {
      const cellsX = Math.round((grid.xMax - grid.xMin) / grid.step);
      const cellsY = Math.round((grid.yMax - grid.yMin) / grid.step);
      const every = Math.max(1, Math.ceil(MIN_LABEL_GAP / (grid.step * scale)));
      ctx.strokeStyle = colors.grid;
      ctx.lineWidth = 1;
      ctx.fillStyle = colors.label;
      ctx.font = `${SIZES.label}px system-ui, sans-serif`;
      for (let i = 0; i <= cellsX; i++) {
        const x = trimFloat(grid.xMin + i * grid.step);
        ctx.beginPath();
        ctx.moveTo(px(x), py(grid.yMax));
        ctx.lineTo(px(x), py(grid.yMin));
        ctx.stroke();
        if (i % every === 0) {
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(formatLabel(x), px(x), py(grid.yMin) + 6);
        }
      }
      for (let j = 0; j <= cellsY; j++) {
        const y = trimFloat(grid.yMin + j * grid.step);
        ctx.beginPath();
        ctx.moveTo(px(grid.xMin), py(y));
        ctx.lineTo(px(grid.xMax), py(y));
        ctx.stroke();
        if (j % every === 0) {
          ctx.textAlign = 'right';
          ctx.textBaseline = 'middle';
          ctx.fillText(formatLabel(y), px(grid.xMin) - 6, py(y));
        }
      }

      // Axes at 0 when 0 is in range, otherwise along the left / bottom edge
      const axisX = grid.xMin <= 0 && 0 <= grid.xMax ? 0 : grid.xMin;
      const axisY = grid.yMin <= 0 && 0 <= grid.yMax ? 0 : grid.yMin;
      ctx.strokeStyle = colors.axis;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(px(axisX), py(grid.yMax));
      ctx.lineTo(px(axisX), py(grid.yMin));
      ctx.moveTo(px(grid.xMin), py(axisY));
      ctx.lineTo(px(grid.xMax), py(axisY));
      ctx.stroke();
    } else if (picture.element) {
      ctx.drawImage(picture.element, plotX, plotY, plotW, plotH);
    }

    // Rings and pins stay inside the plot area
    ctx.save();
    ctx.beginPath();
    ctx.rect(plotX, plotY, plotW, plotH);
    ctx.clip();

    if (target) {
      if (zeroRadius !== undefined) {
        ctx.setLineDash([6, 4]);
        ctx.globalAlpha = ZERO_RING_ALPHA;
        ctx.beginPath();
        ctx.arc(px(target.x), py(target.y), zeroRadius * scale, 0, Math.PI * 2);
        strokeWithHalo(colors.target, 2);
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
      }
      if (fullRadius !== undefined) {
        ctx.fillStyle = colors.ring;
        ctx.beginPath();
        ctx.arc(px(target.x), py(target.y), Math.max(fullRadius * scale, 2), 0, Math.PI * 2);
        ctx.fill();
        // A solid outline marks the full-credit zone; the faint fill alone is under 3:1.
        strokeWithHalo(colors.target, 2);
      }
    }

    // Everyone's pins in one pass (no DOM node per pin)
    ctx.fillStyle = colors.pin;
    ctx.globalAlpha = 0.75;
    for (const p of pins) {
      ctx.beginPath();
      ctx.arc(px(p.x), py(p.y), SIZES.pin, 0, Math.PI * 2);
      ctx.fill();
      if (onPicture) {
        ctx.strokeStyle = colors.halo;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
    ctx.restore();

    if (ownPin) {
      ctx.fillStyle = colors.pin;
      ctx.strokeStyle = colors.axis;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(px(ownPin.x), py(ownPin.y), SIZES.ownPin, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }

    // Target last, so it stays visible even under a pin that hit it exactly
    if (target) {
      const tx = px(target.x);
      const ty = py(target.y);
      const r = 8;
      ctx.beginPath();
      ctx.moveTo(tx - r, ty - r);
      ctx.lineTo(tx + r, ty + r);
      ctx.moveTo(tx - r, ty + r);
      ctx.lineTo(tx + r, ty - r);
      strokeWithHalo(colors.target, 3);
    }
  }, [
    layout?.width,
    layout?.height,
    grid,
    image?.url,
    picture.element,
    pins,
    ownPin,
    target,
    fullRadius,
    zeroRadius,
    themeVersion,
  ]);

  const pickAt = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = canvasRef.current;
      if (!canvas || !layout || !onPick || !pickable) return;
      const rect = canvas.getBoundingClientRect();
      const fx = (clientX - rect.left - layout.plotX) / layout.plotW;
      const fy = (clientY - rect.top - layout.plotY) / layout.plotH;
      // Clicks in the margin clamp to the nearest edge of the answer area.
      const x = bounds.xMin + clamp(fx, 0, 1) * (bounds.xMax - bounds.xMin);
      const y = grid
        ? grid.yMax - clamp(fy, 0, 1) * (grid.yMax - grid.yMin)
        : clamp(fy, 0, 1);
      onPick({ x, y });
    },
    [grid, layout, onPick, pickable, bounds.xMin, bounds.xMax],
  );

  function onKeyDown(e: React.KeyboardEvent) {
    if (!onPick || !pickable) return;
    // Grid: one step per press (up = +y). Image: the same on-screen distance both
    // ways, so Δy is scaled by the aspect ratio (down = +y).
    const aspect = image ? image.height / image.width : 1;
    const dx = grid ? grid.step : IMAGE_KEY_STEP;
    const dy = grid ? grid.step : -IMAGE_KEY_STEP / aspect;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-dx, 0],
      ArrowRight: [dx, 0],
      ArrowUp: [0, dy],
      ArrowDown: [0, -dy],
    };
    const move = moves[e.key];
    if (!move) return;
    e.preventDefault();
    const from = ownPin ?? {
      x: (bounds.xMin + bounds.xMax) / 2,
      y: (bounds.yMin + bounds.yMax) / 2,
    };
    onPick({
      x: clamp(from.x + move[0], bounds.xMin, bounds.xMax),
      y: clamp(from.y + move[1], bounds.yMin, bounds.yMax),
    });
  }

  return (
    <div ref={wrapRef} className="w-full relative">
      <canvas
        ref={canvasRef}
        role={onPick ? 'application' : 'img'}
        aria-label={label}
        tabIndex={onPick ? 0 : undefined}
        onKeyDown={onKeyDown}
        onPointerDown={e => {
          if (!pickable) return;
          dragging.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
          pickAt(e.clientX, e.clientY);
        }}
        onPointerMove={e => {
          if (dragging.current) pickAt(e.clientX, e.clientY);
        }}
        onPointerUp={() => {
          dragging.current = false;
        }}
        onPointerCancel={() => {
          dragging.current = false;
        }}
        style={{
          width: layout?.width ?? '100%',
          height: layout?.height ?? 0,
          touchAction: 'none',
          cursor: pickable ? 'crosshair' : 'default',
        }}
        className="block rounded-card"
      />
      {imageMode && picture.status !== 'ready' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-fg-muted">
          {picture.status === 'loading' ? (
            <span role="status">Loading image…</span>
          ) : (
            <>
              <span role="alert">Image unavailable</span>
              <button
                type="button"
                onClick={picture.retry}
                className="rounded-lg border border-line-strong px-3 py-1 text-fg hover:bg-surface-hover"
              >
                Retry
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
