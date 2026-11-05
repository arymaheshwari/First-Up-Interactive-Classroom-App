"""
T9 token enforcement (docs/plans/t9-theming.md §4.12, §6.2).

Runs scripts/check_theme_tokens.py over the three apps, and unit-tests its rules on
sample lines so a pattern can't silently stop matching.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_theme_tokens.py"

spec = importlib.util.spec_from_file_location("check_theme_tokens", SCRIPT)
check = importlib.util.module_from_spec(spec)
sys.modules["check_theme_tokens"] = check
spec.loader.exec_module(check)


def rules(line: str, suffix: str = ".tsx", small_text_scope: bool = False) -> list[int]:
    return sorted(rule for rule, _ in check.scan_line(line, suffix, small_text_scope))


def test_check_script_passes():
    """No app above its baseline (while converting) / no violation at all (after)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stdout[-3000:]


@pytest.mark.parametrize(
    "line",
    [
        'className="bg-slate-800 p-4"',
        "className='border-t border-t-slate-700'",
        "`hover:bg-indigo-500/20 text-white`",
        '"ring-offset-white from-slate-900 divide-y-slate-800"',
        "md:group-hover:text-red-400",
    ],
)
def test_palette_classes_are_caught(line):
    assert 1 in rules(line)


@pytest.mark.parametrize(
    "line",
    [
        'className="bg-surface text-fg border-line hover:bg-surface-hover"',
        'className="font-black whitespace-nowrap text-on-color"',
        "const answerColour = 'answer-3';",
    ],
)
def test_token_classes_pass(line):
    assert rules(line) == []


def test_dark_variants_and_focus_utilities():
    assert rules('"dark:bg-surface"') == [2]
    assert rules('"focus:outline-none focus:ring-2 focus-visible:ring-focus"') == [
        3,
        3,
        3,
    ]
    assert rules('"outline-none"') == [3]
    assert rules('"focus:border-focus ring-2 ring-fg"') == []


@pytest.mark.parametrize(
    "line",
    [
        "fill: '#94a3b8',",
        "ctx.fillStyle = 'white';",
        "background: rgba(0, 0, 0, 0.5)",
        "color: oklch(70% 0.1 200)",
        'stroke="black"',
    ],
)
def test_colour_literals_are_caught(line):
    assert 4 in rules(line)


@pytest.mark.parametrize(
    "line",
    [
        'href="#add"',
        "fill: 'rgb(var(--c-fg))',",
        "style={{ background: 'rgb(var(--c-accent) / 0.5)' }}",
        "ctx.fillStyle = 'currentColor';",
    ],
)
def test_allowed_colour_forms(line):
    assert 4 not in rules(line)


def test_named_colours_in_css_values():
    assert 4 in rules("  color: white;", ".css")
    assert rules("  color: rgb(var(--c-fg));", ".css") == []


def test_small_text_on_host_game_screens():
    assert rules('className="text-sm"', small_text_scope=True) == [6]
    assert rules('className="text-[14px]"', small_text_scope=True) == [6]
    assert (
        rules(
            '<p /* theme-check: small-text breakdown */ className="text-base">',
            small_text_scope=True,
        )
        == []
    )
    assert rules('className="text-sm"', small_text_scope=False) == []
    assert rules('className="text-host-lg"', small_text_scope=True) == []


FRONTEND = ROOT / "frontend"


def _quoted(block: str) -> list[str]:
    return re.findall(r"'([\w-]+)'", block)


def test_tailwind_merge_knows_the_custom_classes():
    """Each app's cn() registers exactly the preset's custom classes (§4.1, §4.3)."""
    preset = (FRONTEND / "shared" / "theme" / "tailwind-preset.ts").read_text(
        encoding="utf-8"
    )
    custom = re.search(
        r"export const CUSTOM_CLASSES = \{(.*?)\} as const;", preset, re.S
    ).group(1)
    expected = {
        group: sorted(_quoted(re.search(rf"{key}: \[(.*?)\]", custom).group(1)))
        for group, key in (
            ("font-size", "fontSize"),
            ("shadow", "boxShadow"),
            ("rounded", "borderRadius"),
        )
    }
    for app in ("host", "player", "admin"):
        utils = (FRONTEND / app / "src" / "lib" / "utils.ts").read_text(
            encoding="utf-8"
        )
        groups = re.search(r"const THEME_CLASS_GROUPS = \{(.*?)\};", utils, re.S).group(
            1
        )
        actual = {
            group: sorted(
                _quoted(re.search(rf"{re.escape(key)}: \[(.*?)\]", groups).group(1))
            )
            for group, key in (
                ("font-size", "'font-size'"),
                ("shadow", "shadow"),
                ("rounded", "rounded"),
            )
        }
        assert actual == expected, f"{app}/src/lib/utils.ts"


def test_host_canvas_text_is_projector_sized():
    """Canvas text isn't a class, so §4.9's sizes are checked here."""
    question = FRONTEND / "host" / "src" / "components" / "question"
    grid = (question / "GridCanvas.tsx").read_text(encoding="utf-8")
    label = int(re.search(r"const SIZES = \{ label: (\d+),", grid).group(1))
    assert label >= 18
    line = (question / "NumberLine.tsx").read_text(encoding="utf-8")
    full_sizes = [
        int(m) for m in re.findall(r"fontSize=\{compact \? \d+ : (\d+)\}", line)
    ]
    full_sizes += [int(m) for m in re.findall(r"fontSize=\{(\d+)\}", line)]
    assert full_sizes and min(full_sizes) >= 18, full_sizes
