"""
Standalone HTML session report generator.

Produces a self-contained HTML file with aggregate statistics only —
no player names, no individual scores, no personally identifiable information.
Answer distributions are reconstructed from session_scores.answer_data in MySQL
(Redis may have expired for completed sessions).
"""

from __future__ import annotations

import html
import math
import re
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.course import Course
from ..models.game import Game, Question
from ..models.image import Image
from ..models.session import GameSession, SessionScore
from . import feedback_service, image_service, question_types


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _esc(s: object) -> str:
    return html.escape(str(s) if s is not None else "")


def _levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i - 1] == b[j - 1] else 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


# ---------------------------------------------------------------------------
# Histogram helpers (mirrors GameOverPage logic)
# ---------------------------------------------------------------------------

_TARGET_BUCKETS = 8


def _choose_bin_width(ceiling: int) -> int:
    N = ceiling + 1
    best_w, best_diff = 1, float("inf")
    w = 1
    while w * w <= N:
        if N % w == 0:
            for cand in (w, N // w):
                nb = N // cand
                if nb < 2:
                    continue
                d = abs(nb - _TARGET_BUCKETS)
                if d < best_diff:
                    best_diff, best_w = d, cand
        w += 1
    if best_diff > _TARGET_BUCKETS:
        best_w = max(1, -(-N // _TARGET_BUCKETS))
    return best_w


def _build_histogram(scores: list[float], max_possible: float) -> list[dict]:
    ceiling = max(int(max_possible), 1)
    width = _choose_bin_width(ceiling)
    num_buckets = -(-(ceiling + 1) // width)
    buckets = []
    for i in range(num_buckets):
        start = i * width
        end = min(start + width - 1, ceiling)
        label = str(start) if start == end else f"{start}–{end}"
        buckets.append({"label": label, "count": 0})
    for s in scores:
        idx = min(int(s) // width, num_buckets - 1)
        buckets[idx]["count"] += 1
    return buckets


# ---------------------------------------------------------------------------
# HTML rendering helpers
# ---------------------------------------------------------------------------

_OPTION_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


_IMAGE_MISSING = '<span class="image-missing">[image unavailable]</span>'


async def _thumbnails(db: AsyncSession, questions: list[Question]) -> dict[str, str]:
    """
    {image id: data URI} for every image the questions use (D8). One image at a
    time: each blob is loaded, thumbnailed in the threadpool and dropped.
    """
    wanted: dict[str, None] = {}
    for q in questions:
        refs = question_types.referenced_image_ids(q.config)
        for image_id in (refs["prompt"], *refs["options"], refs["pin_drop"]):
            if image_id:
                wanted.setdefault(image_id, None)
    thumbs: dict[str, str] = {}
    for image_id in wanted:
        row = (
            await db.execute(
                select(Image.data, Image.content_type).where(Image.id == image_id)
            )
        ).one_or_none()
        if row is not None:
            thumbs[image_id] = await image_service.run_image_job(
                image_service.thumbnail_data_uri, row.data, row.content_type
            )
    return thumbs


def _img(thumbs: dict[str, str], image_id: str | None, css_class: str) -> str:
    """An embedded thumbnail, the 'unavailable' note, or nothing (no image)."""
    if not image_id:
        return ""
    uri = thumbs.get(image_id)
    if uri is None:
        return _IMAGE_MISSING
    return f'<img class="{css_class}" src="{uri}" alt="">'


def _render_bar_chart(
    q: Question,
    dist: dict[str, int],
    reveal: dict,
    total_players: int,
    thumbs: dict[str, str] | None = None,
) -> str:
    options = q.config.get("options", [])
    option_images = q.config.get("optionImages") or []

    if q.type == "multiple_choice":
        bars = [
            {
                "label": f"{_OPTION_LETTERS[i]} {_esc(opt)}",
                "image": option_images[i] if i < len(option_images) else None,
                "count": dist.get(str(i), 0),
                "correct": (i in reveal.get("correctIndices", []))
                if reveal.get("type") == "multiple_choice"
                else None,
            }
            for i, opt in enumerate(options)
        ]
    elif q.type == "multi_select":
        # An option is correct when choosing it earns points (as on the host screen).
        pts = (
            reveal.get("answerPoints", [])
            if reveal.get("type") == "multi_select"
            else None
        )
        bars = [
            {
                "label": f"{_OPTION_LETTERS[i]} {_esc(opt)}",
                "image": option_images[i] if i < len(option_images) else None,
                "count": dist.get(str(i), 0),
                "correct": (i < len(pts) and pts[i] > 0) if pts is not None else None,
            }
            for i, opt in enumerate(options)
        ]
    elif q.type == "true_false":
        cv = reveal.get("correctValue") if reveal.get("type") == "true_false" else None
        bars = [
            {"label": "True", "count": dist.get("true", 0), "correct": cv is True},
            {"label": "False", "count": dist.get("false", 0), "correct": cv is False},
        ]
    else:
        bars = []

    if not bars:
        return ""

    max_count = max((b["count"] for b in bars), default=0) or 1
    MAX_BAR_W = 100  # percentage

    rows = []
    for bar in bars:
        pct = int((bar["count"] / max_count) * MAX_BAR_W)
        min_pct = 3 if bar["count"] > 0 else 0
        display_pct = max(pct, min_pct)

        if bar["correct"] is True:
            fill_col = "#166534"
            mark = '<span class="bar-correct-mark">✓ Correct</span>'
        elif bar["correct"] is False:
            fill_col = "#1e293b"
            mark = '<span class="bar-correct-mark"></span>'
        else:
            fill_col = "#3730a3"
            mark = ""

        count_inner = (
            f'<span class="bar-count">{bar["count"]}</span>' if bar["count"] > 0 else ""
        )
        thumb = _img(thumbs or {}, bar.get("image"), "opt-thumb")
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{thumb}{bar["label"]}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill" style="width:{display_pct}%;background:{fill_col}">{count_inner}</div>'
            f"</div>"
            f"{mark}"
            f"</div>"
        )

    return '<div class="bar-chart">' + "".join(rows) + "</div>"


def _render_word_cloud(q: Question, dist: dict[str, int], reveal: dict) -> str:
    entries = sorted(dist.items(), key=lambda kv: -kv[1])
    accepted = [a.lower() for a in reveal.get("acceptedAnswers", [])]
    edit_dist = reveal.get("editDistance", 0)

    # Build the correct-answer note first — shown regardless of whether anyone answered
    parts = []
    if accepted and reveal.get("type") == "fill_in_the_blank":
        answer_str = " / ".join(_esc(a) for a in reveal["acceptedAnswers"])
        edit_note = (
            f' <span style="color:#64748b;font-size:0.85em">(±{edit_dist})</span>'
            if edit_dist > 0
            else ""
        )
        parts.append(
            f'<p class="wc-answer-note">Correct answer: '
            f'<span class="wc-answer">{answer_str}</span>{edit_note}</p>'
        )

    if not entries:
        parts.append('<p class="wc-empty">No answers submitted</p>')
        return "\n".join(parts)

    max_count = max(c for _, c in entries) or 1

    def is_correct(word: str) -> bool:
        return any(_levenshtein(word.lower(), a) <= edit_dist for a in accepted)

    def font_size(count: int) -> str:
        f = count / max_count
        if f > 0.75:
            return "2.4rem"
        if f > 0.5:
            return "1.9rem"
        if f > 0.25:
            return "1.4rem"
        if f > 0.1:
            return "1.1rem"
        return "0.9rem"

    parts.append('<div class="word-cloud">')
    for word, count in entries:
        css_class = "wc-word correct" if is_correct(word) else "wc-word"
        s = "s" if count != 1 else ""
        parts.append(
            f'<span class="{css_class}" style="font-size:{font_size(count)}" '
            f'title="{count} player{s}">{_esc(word)}</span>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def _num(v: float) -> str:
    """Compact display number: 2005, 3.5, 0.333333."""
    return str(int(v)) if float(v).is_integer() else f"{v:.6g}"


_PLOT_W = 520  # px, grid area of the pin plot
_PLOT_PAD = 30
_LABEL_GAP = 28  # min px between axis labels


def _render_image_pin_plot(
    q: Question, values: list[dict], reveal: dict, thumbs: dict[str, str]
) -> str:
    """
    The pins over the question's picture (D5): coordinates are fractions of the
    image, distances are in image widths, so the radii are drawn as true circles.
    """
    image = q.config["image"]
    width, height = image.get("width") or 1, image.get("height") or 1
    aspect = height / width
    plot_w, plot_h = _PLOT_W, round(_PLOT_W * aspect, 1)
    pad = 10

    def px(x: float) -> float:
        return round(pad + x * plot_w, 1)

    def py(y: float) -> float:
        return round(pad + y * plot_h, 1)

    uri = thumbs.get(image.get("imageId"))
    if uri:
        parts = [
            f'<image href="{uri}" x="{pad}" y="{pad}" width="{plot_w}" '
            f'height="{plot_h}" preserveAspectRatio="none"/>'
        ]
    else:
        parts = [
            f'<rect x="{pad}" y="{pad}" width="{plot_w}" height="{plot_h}" fill="#1e293b"/>'
            f'<text x="{px(0.5)}" y="{py(0.5)}" fill="#94a3b8" font-size="14" '
            f'text-anchor="middle">[image unavailable]</text>'
        ]
    parts.append(
        f'<rect x="{pad}" y="{pad}" width="{plot_w}" height="{plot_h}" fill="none" '
        f'stroke="#334155" stroke-width="1"/>'
    )

    note = f"{len(values)} pin{'s' if len(values) != 1 else ''}"
    target = reveal.get("target") if reveal.get("type") == "pin_drop" else None
    if target:
        tx, ty = target["x"], target["y"]
        full, zero = reveal["fullRadius"], reveal["zeroRadius"]
        parts.append(
            f'<circle cx="{px(tx)}" cy="{py(ty)}" r="{round(zero * plot_w, 1)}" fill="none" stroke="#4ade80" stroke-opacity="0.6" stroke-dasharray="6 4" stroke-width="2"/>'
            f'<circle cx="{px(tx)}" cy="{py(ty)}" r="{round(full * plot_w, 1)}" fill="#4ade80" fill-opacity="0.2" stroke="#4ade80" stroke-width="2"/>'
        )
        dists = [math.hypot(v["x"] - tx, (v["y"] - ty) * aspect) for v in values]
        inside_full = sum(1 for d in dists if d <= full + 1e-9)
        inside_zero = sum(1 for d in dists if d < zero)
        note += (
            f" · {inside_full} within full credit · {inside_zero} earned points"
            f" · target {_num(round(tx * 100, 1))}% across, "
            f"{_num(round(ty * 100, 1))}% down"
        )
    for v in values:
        parts.append(
            f'<circle cx="{px(v["x"])}" cy="{py(v["y"])}" r="5" fill="#818cf8" fill-opacity="0.9" stroke="#0f172a" stroke-width="1"/>'
        )
    if target:
        cx, cy = px(target["x"]), py(target["y"])
        parts.append(
            f'<path d="M{cx - 7} {cy - 7}L{cx + 7} {cy + 7}M{cx - 7} {cy + 7}L{cx + 7} {cy - 7}" stroke="#4ade80" stroke-width="3"/>'
        )

    w, h = round(plot_w + 2 * pad), round(plot_h + 2 * pad)
    return (
        f'<div class="pin-plot"><svg viewBox="0 0 {w} {h}" width="100%" '
        f'style="max-width:{w}px" role="img" aria-label="Pin plot">'
        + "".join(parts)
        + f'</svg></div><p class="plot-note">{_esc(note)}</p>'
    )


def _render_pin_plot(
    q: Question, values: list[dict], reveal: dict, thumbs: dict[str, str] | None = None
) -> str:
    """Inline SVG: the question's grid, every pin, and the target with both radii."""
    if isinstance(q.config.get("image"), dict):
        return _render_image_pin_plot(q, values, reveal, thumbs or {})
    grid = q.config.get("grid") or {}
    try:
        x0, x1, y0, y1, step = (
            float(grid[k]) for k in ("xMin", "xMax", "yMin", "yMax", "step")
        )
    except (KeyError, TypeError, ValueError):
        return ""
    scale = _PLOT_W / (x1 - x0)
    height = (y1 - y0) * scale
    pad = _PLOT_PAD

    def px(x: float) -> float:
        return round(pad + (x - x0) * scale, 1)

    def py(y: float) -> float:
        return round(pad + (y1 - y) * scale, 1)

    every = max(1, math.ceil(_LABEL_GAP / (step * scale)))
    axis_x = 0.0 if x0 <= 0 <= x1 else x0
    axis_y = 0.0 if y0 <= 0 <= y1 else y0
    parts: list[str] = []
    for i in range(round((x1 - x0) / step) + 1):
        x = x0 + i * step
        parts.append(
            f'<line x1="{px(x)}" y1="{py(y1)}" x2="{px(x)}" y2="{py(y0)}" stroke="#334155" stroke-width="1"/>'
        )
        if i % every == 0:
            parts.append(
                f'<text x="{px(x)}" y="{py(y0) + 18}" fill="#64748b" font-size="11" text-anchor="middle">{_num(round(x, 6))}</text>'
            )
    for j in range(round((y1 - y0) / step) + 1):
        y = y0 + j * step
        parts.append(
            f'<line x1="{px(x0)}" y1="{py(y)}" x2="{px(x1)}" y2="{py(y)}" stroke="#334155" stroke-width="1"/>'
        )
        if j % every == 0:
            parts.append(
                f'<text x="{px(x0) - 8}" y="{py(y) + 4}" fill="#64748b" font-size="11" text-anchor="end">{_num(round(y, 6))}</text>'
            )
    parts.append(
        f'<line x1="{px(axis_x)}" y1="{py(y1)}" x2="{px(axis_x)}" y2="{py(y0)}" stroke="#94a3b8" stroke-width="2"/>'
        f'<line x1="{px(x0)}" y1="{py(axis_y)}" x2="{px(x1)}" y2="{py(axis_y)}" stroke="#94a3b8" stroke-width="2"/>'
    )

    note = f"{len(values)} pin{'s' if len(values) != 1 else ''}"
    target = reveal.get("target") if reveal.get("type") == "pin_drop" else None
    if target:
        tx, ty = target["x"], target["y"]
        full, zero = reveal["fullRadius"], reveal["zeroRadius"]
        parts.append(
            f'<circle cx="{px(tx)}" cy="{py(ty)}" r="{round(zero * scale, 1)}" fill="none" stroke="#4ade80" stroke-opacity="0.35" stroke-dasharray="6 4" stroke-width="2"/>'
            f'<circle cx="{px(tx)}" cy="{py(ty)}" r="{round(full * scale, 1)}" fill="#4ade80" fill-opacity="0.15" stroke="#4ade80" stroke-width="2"/>'
        )
        dists = [math.hypot(v["x"] - tx, v["y"] - ty) for v in values]
        inside_full = sum(1 for d in dists if d <= full + 1e-9)
        inside_zero = sum(1 for d in dists if d < zero)
        note += (
            f" · {inside_full} within full credit · {inside_zero} earned points"
            f" · target ({_num(tx)}, {_num(ty)})"
        )
    for v in values:
        parts.append(
            f'<circle cx="{px(v["x"])}" cy="{py(v["y"])}" r="5" fill="#818cf8" fill-opacity="0.8" stroke="#0f172a" stroke-width="1"/>'
        )
    if target:
        cx, cy = px(target["x"]), py(target["y"])
        parts.append(
            f'<path d="M{cx - 7} {cy - 7}L{cx + 7} {cy + 7}M{cx - 7} {cy + 7}L{cx + 7} {cy - 7}" stroke="#4ade80" stroke-width="3"/>'
        )

    w, h = round(_PLOT_W + 2 * pad), round(height + 2 * pad)
    return (
        f'<div class="pin-plot"><svg viewBox="0 0 {w} {h}" width="100%" '
        f'style="max-width:{w}px" role="img" aria-label="Pin plot">'
        + "".join(parts)
        + f'</svg></div><p class="plot-note">{_esc(note)}</p>'
    )


def _render_estimate_summary(q: Question, values: list[float], reveal: dict) -> str:
    """True value, median/mean/closest guess, and an inline SVG number line."""
    unit = (q.config.get("unit") or "").strip()
    suffix = f" {_esc(unit)}" if unit else ""
    answer = reveal.get("answer") if reveal.get("type") == "estimate" else None

    parts: list[str] = []
    if answer is not None:
        parts.append(
            f'<p class="wc-answer-note">Answer: <span class="wc-answer">{_num(answer)}{suffix}</span></p>'
        )
    if not values:
        parts.append('<p class="wc-empty">No answers submitted</p>')
        return "\n".join(parts)

    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    mean = sum(ordered) / len(ordered)
    stats = [("Guesses", str(len(values))), ("Median", _num(median) + suffix)]
    stats.append(("Mean", _num(round(mean, 6)) + suffix))
    closest = None
    if answer is not None:
        closest = min(values, key=lambda v: abs(v - answer))
        stats.append(("Closest guess", _num(closest) + suffix))
    parts.append(
        '<div class="est-stats">'
        + "".join(
            f'<div class="est-stat"><div class="stat-label">{label}</div>'
            f'<div class="est-value">{value}</div></div>'
            for label, value in stats
        )
        + "</div>"
    )

    lo = min(ordered + ([answer] if answer is not None else []))
    hi = max(ordered + ([answer] if answer is not None else []))
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    width, pad, base = 600, 30, 70

    def px(v: float) -> float:
        return round(pad + (v - lo) / (hi - lo) * (width - 2 * pad), 1)

    svg = [
        f'<line x1="{pad}" y1="{base}" x2="{width - pad}" y2="{base}" stroke="#475569" stroke-width="2"/>',
        f'<text x="{pad}" y="{base + 22}" fill="#64748b" font-size="11" text-anchor="middle">{_num(round(lo, 6))}</text>',
        f'<text x="{width - pad}" y="{base + 22}" fill="#64748b" font-size="11" text-anchor="middle">{_num(round(hi, 6))}</text>',
    ]
    stacks: dict[float, int] = defaultdict(int)
    for v in ordered:
        x = px(v)
        bucket = round(x / 6)
        y = base - 8 - stacks[bucket] * 9
        stacks[bucket] += 1
        fill = "#fbbf24" if closest is not None and v == closest else "#818cf8"
        svg.append(f'<circle cx="{x}" cy="{max(y, 6)}" r="4" fill="{fill}"/>')
    if answer is not None:
        ax = px(answer)
        svg.append(
            f'<line x1="{ax}" y1="{base - 50}" x2="{ax}" y2="{base + 8}" stroke="#4ade80" stroke-width="3"/>'
        )
    parts.append(
        f'<div class="number-line"><svg viewBox="0 0 {width} {base + 30}" width="100%" '
        f'role="img" aria-label="Number line of guesses">'
        + "".join(svg)
        + "</svg></div>"
    )
    return "\n".join(parts)


def _render_histogram(buckets: list[dict]) -> str:
    max_count = max((b["count"] for b in buckets), default=0) or 1
    MAX_H = 160  # max bar height px

    bar_cols, label_cols = [], []
    for b in buckets:
        bar_h = max(int((b["count"] / max_count) * MAX_H), 2 if b["count"] > 0 else 0)
        count_str = str(b["count"]) if b["count"] > 0 else ""
        bar_cols.append(
            f'<div class="hist-col">'
            f'<span class="hist-count">{count_str}</span>'
            f'<div class="hist-bar" style="height:{bar_h}px"></div>'
            f"</div>"
        )
        label_cols.append(f'<div class="hist-label">{_esc(b["label"])}</div>')

    return (
        '<div class="histogram">'
        + "".join(bar_cols)
        + "</div>"
        + '<div class="hist-labels">'
        + "".join(label_cols)
        + "</div>"
        + '<p class="hist-axis">Score (points) →</p>'
    )


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',sans-serif;
  background:#0f172a;color:#e2e8f0;line-height:1.6;padding:48px 24px;
}
.container{max-width:980px;margin:0 auto}

/* ── Header ── */
.rpt-header{text-align:center;margin-bottom:56px;padding-bottom:40px;border-bottom:1px solid #1e293b}
.rpt-header h1{font-size:2.4rem;font-weight:900;color:#f1f5f9;margin-bottom:12px}
.rpt-meta{color:#64748b;font-size:0.9rem}
.rpt-meta .sep{margin:0 10px;color:#1e293b}

/* ── Section label ── */
.section-label{
  font-size:0.65rem;text-transform:uppercase;letter-spacing:0.15em;
  color:#334155;margin-bottom:20px;
}

/* ── Question cards ── */
.q-card{
  background:#1e293b;border:1px solid #334155;border-radius:16px;
  padding:32px 36px;margin-bottom:24px;
}
.q-meta{display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.q-num{color:#475569;font-size:0.75rem;font-family:monospace;font-weight:700}
.badge{font-size:0.65rem;font-weight:700;padding:3px 9px;border-radius:20px;letter-spacing:0.04em}
.badge-mc{background:#1e3a5f;color:#93c5fd}
.badge-tf{background:#1a3a2a;color:#86efac}
.badge-fitb{background:#3b2f1e;color:#fbbf24}
.badge-ms{background:#25234a;color:#a5b4fc}
.badge-pin{background:#3b1e33;color:#f9a8d4}
.badge-est{background:#1e3b3a;color:#5eead4}
.badge-accuracy{background:#2e1b3d;color:#c084fc}
.badge-completeness{background:#2d2d1a;color:#fde68a}
.q-timing{margin-left:auto;color:#475569;font-size:0.78rem}
.prompt{font-size:1.2rem;font-weight:600;color:#f1f5f9;margin-bottom:28px;line-height:1.5}
.q-stats{margin-top:16px;font-size:0.78rem;color:#475569;text-align:right}
.pct-correct{color:#4ade80;font-weight:700}

/* ── Bar chart ── */
.bar-chart{display:flex;flex-direction:column;gap:10px}
.bar-row{display:flex;align-items:center;gap:12px}
.bar-label{
  font-size:0.88rem;font-weight:500;color:#cbd5e1;
  width:210px;flex-shrink:0;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.bar-track{flex:1;height:44px;background:#0f172a;border-radius:8px;overflow:hidden}
.bar-fill{height:100%;border-radius:8px;display:flex;align-items:center;justify-content:flex-end;padding-right:12px}
.bar-count{font-size:0.85rem;font-weight:700;color:#fff}
.bar-correct-mark{font-size:0.72rem;color:#4ade80;font-weight:700;width:68px;flex-shrink:0}

/* ── Word cloud ── */
.wc-answer-note{text-align:center;color:#64748b;font-size:0.88rem;margin-bottom:14px}
.wc-answer{color:#4ade80;font-weight:700}
.word-cloud{
  display:flex;flex-wrap:wrap;gap:10px 18px;
  justify-content:center;align-items:center;
  min-height:80px;padding:20px;
  background:#0f172a;border-radius:12px;
}
.wc-word{font-weight:700;color:#64748b}
.wc-word.correct{color:#4ade80}
.wc-empty{color:#334155;font-size:0.9rem;text-align:center;padding:20px}

/* ── Pin plot / number line ── */
.pin-plot,.number-line{background:#0f172a;border-radius:12px;padding:12px;text-align:center}
.q-image{display:block;max-width:480px;width:100%;border-radius:10px;margin-bottom:16px}
.opt-thumb{height:36px;width:auto;max-width:64px;object-fit:contain;vertical-align:middle;margin-right:8px;border-radius:4px}
.image-missing{display:block;color:#94a3b8;font-style:italic;font-size:0.85rem;margin-bottom:8px}
.plot-note{text-align:center;color:#64748b;font-size:0.82rem;margin-top:10px}
.est-stats{display:flex;justify-content:center;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.est-stat{background:#0f172a;border-radius:10px;padding:10px 18px;text-align:center;min-width:110px}
.est-value{font-size:1.15rem;font-weight:800;color:#f1f5f9}

/* ── Histogram ── */
.summary-card{
  background:#1e293b;border:1px solid #334155;border-radius:16px;
  padding:36px;margin-bottom:24px;
}
.summary-card h2{font-size:1.4rem;font-weight:800;color:#f1f5f9;margin-bottom:32px;text-align:center}
.histogram{display:flex;align-items:flex-end;gap:8px;margin-bottom:0}
.hist-col{flex:1;display:flex;flex-direction:column;align-items:center}
.hist-count{font-size:0.72rem;font-weight:700;color:#94a3b8;margin-bottom:4px;min-height:18px}
.hist-bar{width:100%;background:#6366f1;border-radius:4px 4px 0 0}
.hist-labels{display:flex;gap:8px;margin-top:6px}
.hist-label{flex:1;text-align:center;font-size:0.68rem;color:#475569}
.hist-axis{text-align:center;font-size:0.7rem;color:#334155;margin-top:6px}

/* ── Summary stats ── */
.stats-row{
  display:flex;justify-content:center;
  margin-top:32px;padding-top:28px;border-top:1px solid #334155;
}
.stat-box{flex:1;text-align:center;padding:0 16px}
.stat-box+.stat-box{border-left:1px solid #334155}
.stat-label{font-size:0.65rem;text-transform:uppercase;letter-spacing:0.12em;color:#64748b;margin-bottom:6px}
.stat-value{font-size:2rem;font-weight:900;color:#f1f5f9}

/* ── Footer ── */
.rpt-footer{text-align:center;margin-top:56px;color:#1e293b;font-size:0.72rem}
"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def build_session_report(db: AsyncSession, session_id: str) -> tuple[str, bytes]:
    """
    Return (filename, html_bytes) for a standalone session report.
    Aggregate statistics only — no player names or individual scores.
    """
    session = await db.get(GameSession, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    game = await db.get(Game, session.game_id)
    course = await db.get(Course, session.course_id)

    q_result = await db.execute(
        select(Question)
        .where(Question.game_id == session.game_id)
        .order_by(Question.order_index)
    )
    questions = q_result.scalars().all()
    thumbs = await _thumbnails(db, list(questions))

    s_result = await db.execute(
        select(SessionScore).where(SessionScore.session_id == session_id)
    )
    all_scores = s_result.scalars().all()

    # Group by question
    by_question: dict[int, list[SessionScore]] = defaultdict(list)
    for s in all_scores:
        by_question[s.question_id].append(s)

    # Unique players and totals for histogram
    player_totals: dict[str, float] = defaultdict(float)
    for s in all_scores:
        player_totals[s.user_id] += float(s.points_awarded)
    final_scores = list(player_totals.values())
    total_players = len(player_totals)

    max_possible = sum(q.points_value for q in questions)
    game_title = game.title if game else "Unknown Game"
    course_name = f"{course.name} — {course.semester}" if course else "Unknown Course"

    ts = session.completed_at or session.created_at
    date_played = ts.strftime("%B %d, %Y") if ts else "Unknown Date"

    # Players' thumbs and flags: counts only, like everything else in this report.
    feedback = await feedback_service.feedback_counts(db, session_id)

    # ── Question sections ──────────────────────────────────────────────────
    q_sections: list[str] = []
    for idx, q in enumerate(questions):
        q_scores = by_question.get(q.id, [])
        answered = len(q_scores)
        correct_count = sum(1 for s in q_scores if s.is_correct)

        dist: dict[str, int] = defaultdict(int)
        for s in q_scores:
            for key in question_types.answer_keys(q.type, s.answer_data):
                dist[key] += 1
        values = [
            v
            for s in q_scores
            if (v := question_types.answer_value(q.type, s.answer_data)) is not None
        ]

        reveal = question_types.reveal_answer(q)
        is_accuracy = q.grading_type == "ACCURACY"
        prompt_image = question_types.referenced_image_ids(q.config)["prompt"]

        type_badge = {
            "multiple_choice": ("Multiple Choice", "badge-mc"),
            "true_false": ("True / False", "badge-tf"),
            "fill_in_the_blank": ("Fill in the Blank", "badge-fitb"),
            "multi_select": ("Multi-Select", "badge-ms"),
            "pin_drop": ("Pin It", "badge-pin"),
            "estimate": ("Estimate", "badge-est"),
        }.get(q.type, (q.type, ""))
        type_label, type_class = type_badge

        grading_label = "Accuracy" if is_accuracy else "Completeness"
        grading_class = "badge-accuracy" if is_accuracy else "badge-completeness"

        pts_val = f"{q.points_value:g}"
        pts_label = f"{pts_val} pt{'s' if q.points_value != 1 else ''}"

        if q.type in ("multiple_choice", "true_false", "multi_select"):
            chart = _render_bar_chart(q, dict(dist), reveal, total_players, thumbs)
        elif q.type == "fill_in_the_blank":
            chart = _render_word_cloud(q, dict(dist), reveal)
        elif q.type == "pin_drop":
            chart = _render_pin_plot(q, values, reveal, thumbs)
        elif q.type == "estimate":
            chart = _render_estimate_summary(q, values, reveal)
        else:
            chart = ""

        if is_accuracy and answered > 0:
            pct = round(correct_count / answered * 100)
            stats = (
                f'<div class="q-stats">'
                f"{answered} / {total_players} answered"
                f' · <span class="pct-correct">{pct}% correct</span>'
                f"</div>"
            )
        else:
            stats = f'<div class="q-stats">{answered} / {total_players} answered</div>'
        fb = feedback.get(q.id)
        if fb and any(fb.values()):
            stats += (
                f'<div class="q-stats q-feedback">'
                f"Feedback: &#128077; {fb['up']} · &#128078; {fb['down']}"
                f" · &#128681; {fb['flagged']} flagged as hard"
                f"</div>"
            )

        # Prompt was already bleach-sanitised on write; embed as HTML
        q_sections.append(
            f'<div class="q-card">'
            f'<div class="q-meta">'
            f'<span class="q-num">Q{idx + 1} of {len(questions)}</span>'
            f'<span class="badge {type_class}">{_esc(type_label)}</span>'
            f'<span class="badge {grading_class}">{_esc(grading_label)}</span>'
            f'<span class="q-timing">{q.time_limit_seconds}s · {_esc(pts_label)}</span>'
            f"</div>"
            f"{_img(thumbs, prompt_image, 'q-image')}"
            f'<p class="prompt">{q.prompt}</p>'
            f"{chart}"
            f"{stats}"
            f"</div>"
        )

    # ── Histogram ─────────────────────────────────────────────────────────
    buckets = _build_histogram(final_scores, max_possible)
    histogram = _render_histogram(buckets)
    avg = round(sum(final_scores) / len(final_scores), 1) if final_scores else 0
    high = max(final_scores) if final_scores else 0

    # ── Assemble document ─────────────────────────────────────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    safe = re.sub(r"[^a-zA-Z0-9-]", "_", game_title)  # spaces and special chars → _
    safe = re.sub(r"_+", "_", safe).strip("_")  # collapse runs, trim edges
    date_str = ts.strftime("%Y-%m-%d") if ts else "unknown"
    filename = f"report_{safe}_{date_str}_{session_id[:8]}.html"

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1024">
<title>{_esc(game_title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">

<div class="rpt-header">
  <h1>{_esc(game_title)}</h1>
  <div class="rpt-meta">
    <span>{_esc(course_name)}</span>
    <span class="sep">·</span>
    <span>{_esc(date_played)}</span>
    <span class="sep">·</span>
    <span>{total_players} player{"s" if total_players != 1 else ""}</span>
    <span class="sep">·</span>
    <span>Max {max_possible:g} pts</span>
  </div>
</div>

<p class="section-label">Questions &amp; Results</p>

{"".join(q_sections)}

<div class="summary-card">
  <h2>Score Distribution</h2>
  {histogram}
  <div class="stats-row">
    <div class="stat-box">
      <div class="stat-label">Players</div>
      <div class="stat-value">{total_players}</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">Average Score</div>
      <div class="stat-value">{avg:g}</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">High Score</div>
      <div class="stat-value">{high:g}</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">Max Possible</div>
      <div class="stat-value">{max_possible:g}</div>
    </div>
  </div>
</div>

<div class="rpt-footer">Generated by Buzzer · {_esc(timestamp)}</div>

</div>
</body>
</html>"""

    return filename, doc.encode()
