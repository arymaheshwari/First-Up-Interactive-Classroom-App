#!/usr/bin/env python3
"""
Theme-token check for the three frontend apps.

Fails on anything that bypasses the semantic tokens in frontend/shared/theme/:

  1. a Tailwind class ending in a default palette colour (`bg-slate-800`,
     `border-t-white/10`, `hover:text-indigo-400`, ...);
  2. a `dark:` variant;
  3. a focus utility that would compete with the global outline (`outline-none`,
     `focus:ring-*`, `focus-visible:outline-*`, ...);
  4. a colour literal: hex, a colour function without var(), or a quoted CSS colour
     name;
  5. the theme storage key outside its four homes (exact quoted string);
  6. small text on the host game screens without a named exemption.

A line containing `theme-check: ignore` is skipped (and listed). Rule 6 exemptions
use `theme-check: small-text <exemption>` on the same line.

While the apps are being converted, scripts/theme_tokens_baseline.json may hold a
per-app count (rules 1-4 and 6) that must not rise; rule 5 is always enforced.

Usage:
  python scripts/check_theme_tokens.py                  # check (exit 1 on failure)
  python scripts/check_theme_tokens.py --write-baseline # store current counts (never higher)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
APPS = ("host", "player", "admin")
THEME_TS = FRONTEND / "shared" / "theme" / "theme.ts"
BASELINE = ROOT / "scripts" / "theme_tokens_baseline.json"
KEY = "buzzer-theme"

PALETTE = (
    "slate gray zinc neutral stone red orange amber yellow lime green emerald teal cyan "
    "sky blue indigo violet purple fuchsia pink rose white black"
).split()

# 1. A class token ending in a palette colour, with optional shade and opacity.
PALETTE_CLASS = re.compile(
    r"(?<![\w-])(?:[\w\[\]&>*-]+:)*[a-z]+(?:-[a-z0-9]+)*-(?:"
    + "|".join(PALETTE)
    + r")(?:-\d{2,3})?(?:/\d{1,3})?(?![\w-])"
)
# Utilities that end in a palette word but aren't colours.
NOT_A_COLOUR = re.compile(r"(?:^|:)font-(?:black|white)$")
# 2. dark: variants.
DARK_VARIANT = re.compile(r"(?<![\w-])(?:[\w-]+:)*dark:")
# 3. Focus utilities that would out-rank the global outline.
FOCUS_UTILITY = re.compile(
    r"(?<![\w-])(?:(?:[\w-]+:)*outline-none|(?:[\w-]+:)*(?:focus|focus-visible|focus-within):(?:ring|outline)[\w/.-]*)(?![\w-])"
)
# 4a. Hex colours (not href="#add" / to="#top").
HEX = re.compile(
    r"(?<![\w&/#])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])"
)
HREF_BEFORE = re.compile(r"(?:href|to)=\{?[\"'`]$")
# 4b. Colour functions; allowed only when they wrap var().
COLOR_FN = re.compile(
    r"(?<![\w-])(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix|color)\(", re.IGNORECASE
)
# 4c. CSS named colours as a whole quoted string (TS/TSX) or a CSS value.
NAMED_COLORS = set(
    """aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue
    blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk
    crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki
    darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
    darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue
    dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite
    gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
    lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
    lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen
    lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen
    magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
    mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream
    mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid
    palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum
    powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown
    seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen
    steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow
    yellowgreen""".split()
)
QUOTED = re.compile(r"([\"'`])([A-Za-z]+)\1")
CSS_VALUE_NAMED = re.compile(r":\s*([A-Za-z]+)\b")
# 5. The storage key as an exact quoted string.
KEY_LITERAL = re.compile(r"([\"'])" + re.escape(KEY) + r"\1")
# 6. Small text on host game screens.
SMALL_TEXT = re.compile(
    r"(?<![\w-])(?:[\w-]+:)*text-(?:xs|sm|base|lg|\[[^\]]+\])(?![\w-])"
)
EXEMPTIONS = ("controls", "qr-caption", "breakdown", "histogram", "wordcloud")
SMALL_TEXT_OK = re.compile(
    r"theme-check: small-text (?:" + "|".join(EXEMPTIONS) + r")\b"
)
SMALL_TEXT_DIRS = (
    FRONTEND / "host" / "src" / "pages" / "game",
    FRONTEND / "host" / "src" / "components" / "question",
)
IGNORE = "theme-check: ignore"


@dataclass
class Finding:
    app: str
    rule: int
    path: Path
    line: int
    text: str

    def __str__(self) -> str:
        return f"{self.path.relative_to(ROOT).as_posix()}:{self.line}: rule {self.rule}: {self.text}"


def app_files(app: str) -> list[Path]:
    root = FRONTEND / app
    files = [root / "index.html"]
    for pattern in ("*.ts", "*.tsx", "*.css"):
        files += sorted((root / "src").rglob(pattern))
    return files


def color_function_findings(line: str) -> list[str]:
    hits = []
    for m in COLOR_FN.finditer(line):
        inner = line[m.end() :]
        close = inner.find(")")
        head = inner if close == -1 else inner[:close]
        if "var(" not in head:
            hits.append(m.group(0))
    return hits


def scan_line(line: str, suffix: str, small_text_scope: bool) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    # `font-black` is a weight, not a colour.
    found += [
        (1, m.group(0))
        for m in PALETTE_CLASS.finditer(line)
        if not NOT_A_COLOUR.search(m.group(0))
    ]
    found += [(2, m.group(0)) for m in DARK_VARIANT.finditer(line)]
    found += [(3, m.group(0)) for m in FOCUS_UTILITY.finditer(line)]
    for m in HEX.finditer(line):
        if not HREF_BEFORE.search(line[: m.start()]):
            found.append((4, m.group(0)))
    found += [(4, hit) for hit in color_function_findings(line)]
    if suffix in (".ts", ".tsx"):
        found += [
            (4, m.group(0))
            for m in QUOTED.finditer(line)
            if m.group(2).lower() in NAMED_COLORS
        ]
    elif suffix == ".css":
        found += [
            (4, m.group(0))
            for m in CSS_VALUE_NAMED.finditer(line)
            if m.group(1).lower() in NAMED_COLORS
        ]
    if small_text_scope and not SMALL_TEXT_OK.search(line):
        found += [(6, m.group(0)) for m in SMALL_TEXT.finditer(line)]
    return found


def scan() -> tuple[list[Finding], list[str], list[str]]:
    """(findings for rules 1-4 and 6, rule-5 problems, ignored lines)."""
    findings: list[Finding] = []
    ignored: list[str] = []
    key_homes: Counter[Path] = Counter()
    for app in APPS:
        for path in app_files(app):
            small_scope = any(d in path.parents for d in SMALL_TEXT_DIRS)
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                key_homes[path] += len(KEY_LITERAL.findall(line))
                if IGNORE in line:
                    ignored.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
                    continue
                for rule, text in scan_line(line, path.suffix, small_scope):
                    findings.append(Finding(app, rule, path, number, text))

    problems: list[str] = []
    required = [FRONTEND / app / "index.html" for app in APPS]
    for path in required:
        if key_homes[path] == 0:
            problems.append(
                f"{path.relative_to(ROOT).as_posix()}: missing the '{KEY}' key (rule 5)"
            )
    if not KEY_LITERAL.search(THEME_TS.read_text(encoding="utf-8")):
        problems.append(
            f"{THEME_TS.relative_to(ROOT).as_posix()}: missing the '{KEY}' key (rule 5)"
        )
    for path, count in key_homes.items():
        if count and path not in required:
            problems.append(
                f"{path.relative_to(ROOT).as_posix()}: repeats the '{KEY}' key; import THEME_KEY (rule 5)"
            )
    return findings, problems, ignored


def counts(findings: list[Finding]) -> dict[str, int]:
    per_app = Counter(f.app for f in findings)
    return {app: per_app.get(app, 0) for app in APPS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--write-baseline", action="store_true", help="store the current per-app counts"
    )
    args = parser.parse_args()

    findings, problems, ignored = scan()
    current = counts(findings)
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else None

    if args.write_baseline:
        if baseline is not None:
            higher = {
                app: (baseline.get(app, 0), n)
                for app, n in current.items()
                if n > baseline.get(app, 0)
            }
            if higher:
                print(f"refusing to raise the baseline: {higher}")
                return 1
        # Bytes, so Windows doesn't turn the newlines into CRLF.
        BASELINE.write_bytes((json.dumps(current, indent=2) + "\n").encode())
        print(f"baseline written: {current}")
        return 0

    for line in ignored:
        print(f"ignored ({IGNORE}): {line}")
    for problem in problems:
        print(problem)

    if baseline is None:
        for finding in findings:
            print(finding)
        ok = not findings and not problems
        print(
            f"{len(findings)} token violation(s), {len(problems)} key problem(s), {len(ignored)} ignored line(s)"
        )
        return 0 if ok else 1

    over = {
        app: (n, baseline.get(app, 0))
        for app, n in current.items()
        if n > baseline.get(app, 0)
    }
    for app in over:
        for finding in findings:
            if finding.app == app:
                print(finding)
    print(f"converting: {current} (baseline {baseline})")
    if over:
        print(f"over the baseline: {over}")
    return 0 if not over and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
