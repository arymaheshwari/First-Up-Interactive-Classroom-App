"""
T9 contrast check (docs/plans/t9-theming.md §6.1): every text/background and
graphic/background pair the UI uses meets WCAG 2.1 AA, in both themes, computed from
frontend/shared/theme/tokens.css.

Text needs 4.5:1; control boundaries, focus outlines and graphics (bars, pins, rings)
need 3:1 (WCAG 1.4.11).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
THEME = ROOT / "frontend" / "shared" / "theme"
TOKENS_CSS = (THEME / "tokens.css").read_text(encoding="utf-8")
PRESET = (THEME / "tailwind-preset.ts").read_text(encoding="utf-8")

TEXT, GRAPHIC = 4.5, 3.0
THEMES = ("light", "dark")
SURFACES = ("canvas", "surface", "surface-raised", "surface-sunken")
SUBTLES = ("accent-subtle", "success-subtle", "danger-subtle", "warning-subtle")
FILLS = ("accent", "accent-hover", "success", "danger", "warning") + tuple(
    f"answer-{n}" for n in range(1, 9)
)
PRESS_ALPHA = 0.12  # boxShadow.press in tailwind-preset.ts

RGB = tuple[float, float, float]


def _blocks() -> dict[str, str]:
    light = re.search(r":root\s*\{(.*?)\n\}", TOKENS_CSS, re.S).group(1)
    dark = re.search(
        r":root\[data-theme='dark'\]\s*\{(.*?)\n\}", TOKENS_CSS, re.S
    ).group(1)
    return {"light": light, "dark": dark}


def _parse(block: str) -> tuple[dict[str, RGB], dict[str, tuple[RGB, float]]]:
    tokens = {
        name: (float(r), float(g), float(b))
        for name, r, g, b in re.findall(
            r"--c-([\w-]+):\s*(\d+)\s+(\d+)\s+(\d+)\s*;", block
        )
    }
    canvas: dict[str, tuple[RGB, float]] = {}
    for name, body in re.findall(r"--canvas-([\w-]+):\s*rgba?\(([^)]*)\)\s*;", block):
        parts = [p for p in re.split(r"[\s,/]+", body.strip()) if p]
        alpha = float(parts[3]) if len(parts) == 4 else 1.0
        canvas[name] = ((float(parts[0]), float(parts[1]), float(parts[2])), alpha)
    return tokens, canvas


BLOCKS = _blocks()
PARSED = {theme: _parse(BLOCKS[theme]) for theme in THEMES}


def tok(theme: str, name: str) -> RGB:
    return PARSED[theme][0][name]


def over(fg: RGB, alpha: float, bg: RGB) -> RGB:
    """`fg` at `alpha` composited over an opaque `bg`."""
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg, bg))


def luminance(c: RGB) -> float:
    def channel(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: RGB, b: RGB) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def pairs() -> list[tuple[str, str, str, float]]:
    """(theme, foreground token, background token, minimum)."""
    out = []
    for theme in THEMES:
        for fg in ("fg", "fg-muted", "fg-subtle"):
            for bg in SURFACES + ("surface-hover",) + SUBTLES:
                out.append((theme, fg, bg, TEXT))
        for status in ("accent", "success", "danger", "warning"):
            for bg in SURFACES + ("surface-hover",) + SUBTLES:
                out.append((theme, f"{status}-fg", bg, TEXT))
        for fill in FILLS:
            out.append((theme, "on-color", fill, TEXT))
        # Host login's primary action gradients from accent to scene-blue.
        out.append((theme, "on-color", "scene-blue", TEXT))
        for bg in ("surface", "surface-raised", "surface-sunken"):
            out.append((theme, "line-strong", bg, GRAPHIC))
        for bg in ("canvas", "surface", "surface-raised"):
            out.append((theme, "focus", bg, GRAPHIC))
        for bg in ("surface", "surface-raised", "accent-subtle"):
            out.append((theme, "accent-fg", bg, GRAPHIC))  # the selection bar
        for fill in ("success", "accent", "line-strong", "warning", "danger"):
            out.append(
                (theme, fill, "surface-sunken", GRAPHIC)
            )  # results bars, TimerBar
        # The player's selected multi-select badge inverts the fill: accent text on white.
        # (accent-fg is a light tint in dark, so it can't be the badge text.)
        out.append((theme, "accent", "on-color", TEXT))
        out.append((theme, "fg", "canvas", GRAPHIC))  # the picture-option selection ring
    return out


@pytest.mark.parametrize("theme, fg, bg, minimum", pairs())
def test_token_pair(theme, fg, bg, minimum):
    ratio = contrast(tok(theme, fg), tok(theme, bg))
    assert ratio >= minimum, f"{theme}: {fg} on {bg} is {ratio:.2f}, needs {minimum}"


# Pixel Cats is an optional visual skin over either required color mode. Check its
# merged tokens against the same UI roles, except Aurora's unused blue gradient end.
PIXEL_CSS = (THEME / "pixel-cats.css").read_text(encoding="utf-8")


def pixel_tokens(theme: str) -> dict[str, RGB]:
    block = re.search(
        rf":root\[data-visual-theme='pixel-cats'\]\[data-theme='{theme}'\]\s*\{{(.*?)\n\}}",
        PIXEL_CSS,
        re.S,
    ).group(1)
    return PARSED[theme][0] | _parse(block)[0]


@pytest.mark.parametrize("theme, fg, bg, minimum", [p for p in pairs() if p[2] != "scene-blue"])
def test_pixel_cat_token_pair(theme, fg, bg, minimum):
    tokens = pixel_tokens(theme)
    ratio = contrast(tokens[fg], tokens[bg])
    assert ratio >= minimum, f"Pixel Cats {theme}: {fg} on {bg} is {ratio:.2f}, needs {minimum}"


CLASSROOM_CSS = (THEME / "pixel-classroom.css").read_text(encoding="utf-8")


def classroom_tokens(theme: str) -> dict[str, RGB]:
    block = re.search(
        rf":root\[data-visual-theme='pixel-classroom'\]\[data-theme='{theme}'\]\s*\{{(.*?)\n\}}",
        CLASSROOM_CSS,
        re.S,
    ).group(1)
    return PARSED[theme][0] | _parse(block)[0]


@pytest.mark.parametrize("theme, fg, bg, minimum", [p for p in pairs() if p[2] != "scene-blue"])
def test_pixel_classroom_token_pair(theme, fg, bg, minimum):
    tokens = classroom_tokens(theme)
    ratio = contrast(tokens[fg], tokens[bg])
    assert ratio >= minimum, f"Pixel Classroom {theme}: {fg} on {bg} is {ratio:.2f}, needs {minimum}"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("fill", FILLS)
def test_on_color_survives_the_press_overlay(theme, fill):
    pressed = over(tok(theme, "shadow"), PRESS_ALPHA, tok(theme, fill))
    ratio = contrast(tok(theme, "on-color"), pressed)
    assert ratio >= TEXT, f"{theme}: on-color on pressed {fill} is {ratio:.2f}"


@pytest.mark.parametrize("theme", THEMES)
def test_canvas_colours(theme):
    canvas = PARSED[theme][1]
    bg, bg_alpha = canvas["bg"]
    assert bg_alpha == 1.0
    assert bg == tok(theme, "surface-sunken"), "the plot area is surface-sunken"
    for name, minimum in (
        ("label", TEXT),
        ("axis", TEXT),
        ("pin", GRAPHIC),
        ("target", GRAPHIC),
        ("highlight", GRAPHIC),
    ):
        colour, alpha = canvas[name]
        ratio = contrast(over(colour, alpha, bg), bg)
        assert ratio >= minimum, (
            f"{theme}: --canvas-{name} is {ratio:.2f} on the plot, needs {minimum}"
        )


def test_both_themes_define_the_same_names():
    light, dark = PARSED["light"], PARSED["dark"]
    assert set(light[0]) == set(dark[0])
    assert set(light[1]) == set(dark[1])


def test_preset_tokens_exist_in_tokens_css():
    block = re.search(r"export const TOKENS = \[(.*?)\] as const;", PRESET, re.S).group(
        1
    )
    names = re.findall(r"'([\w-]+)'", block)
    assert names, "TOKENS not found in tailwind-preset.ts"
    assert set(names) == set(PARSED["light"][0]), "TOKENS and tokens.css differ"


def test_canvas_names_read_by_the_canvases_are_defined():
    defined = set(PARSED["light"][1])
    sources = [
        ROOT / "frontend" / app / "src" / "components" / "question" / name
        for app in ("host", "player")
        for name in ("GridCanvas.tsx",)
    ] + [
        ROOT
        / "frontend"
        / "host"
        / "src"
        / "components"
        / "question"
        / "NumberLine.tsx"
    ]
    read: set[str] = set()
    for path in sources:
        text = path.read_text(encoding="utf-8")
        read |= set(re.findall(r"--canvas-([a-z]+)", text))
        names = re.search(r"CANVAS_COLOR_NAMES = \[(.*?)\]", text, re.S)
        if names:
            read |= set(re.findall(r"'([a-z]+)'", names.group(1)))
        fallback = re.search(r"FALLBACK_COLORS = \{(.*?)\};", text, re.S)
        if fallback:
            read |= set(re.findall(r"^\s*(\w+):", fallback.group(1), re.M))
    assert read, "no canvas colour names found"
    assert read <= defined, f"read but not defined: {sorted(read - defined)}"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("mark", ("target", "pin"))
def test_marks_on_a_picture_contrast_with_their_halo(theme, mark):
    """On a picture, each mark sits on its halo, so it reads over any photo."""
    canvas = PARSED[theme][1]
    halo, halo_alpha = canvas["halo"]
    colour, alpha = canvas[mark]
    assert halo_alpha == 1.0
    ratio = contrast(over(colour, alpha, halo), halo)
    assert ratio >= GRAPHIC, f"{theme}: --canvas-{mark} on its halo is {ratio:.2f}"


ZERO_RING = re.compile(r"^const ZERO_RING_ALPHA = (\d*\.?\d+);$", re.M)


@pytest.mark.parametrize("theme", THEMES)
def test_zero_credit_ring(theme):
    """The dashed zero-credit ring, drawn at ZERO_RING_ALPHA, is >= 3:1 on the plot."""
    alphas = []
    for app in ("host", "player"):
        source = (
            ROOT
            / "frontend"
            / app
            / "src"
            / "components"
            / "question"
            / "GridCanvas.tsx"
        ).read_text(encoding="utf-8")
        found = ZERO_RING.findall(source)
        assert len(found) == 1, f"{app} GridCanvas must declare ZERO_RING_ALPHA once"
        alphas.append(float(found[0]))
    assert alphas == [0.9, 0.9]
    canvas = PARSED[theme][1]
    bg, _ = canvas["bg"]
    target, _ = canvas["target"]
    ratio = contrast(over(target, alphas[0], bg), bg)
    assert ratio >= GRAPHIC, f"{theme}: zero-credit ring is {ratio:.2f}"
