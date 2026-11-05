"""
Question-type registry — every per-type rule lives here, once.

Each question type is a handler with the same seven functions:

- ``validate_structure``  author-side shape of ``config`` / ``answer_data`` (create,
                          update and import all call it, so they can't disagree)
- ``validate_answer``     player-side answer check; raises ``ValueError`` to reject
- ``score``               ACCURACY scoring of one answer
- ``reveal``              client-safe correct-answer facts (ACCURACY)
- ``answer_keys``         buckets for count-based results charts
- ``answer_value``        the raw answer for value-based results charts
- ``client_config``       the ``config`` fields players may see

Callers use the module-level helpers (``score_answer``, ``reveal_answer``, …), which
also handle COMPLETENESS grading and unknown types in one place.
"""

from __future__ import annotations

import math
import re
from typing import Any, NamedTuple, Protocol

from rapidfuzz.distance import Levenshtein

from ..schemas.game import ScoreResult


class QuestionLike(Protocol):
    type: str
    grading_type: str
    config: dict
    answer_data: dict
    points_value: float


class QuestionFacts(NamedTuple):
    """A QuestionLike built from query columns (the summaries don't load ORM objects)."""

    type: str
    grading_type: str
    config: dict
    answer_data: dict
    points_value: float


_NO_SCORE = ScoreResult(points_awarded=0, is_correct=False)


def _normalize_text(text: str | None) -> str:
    """Lower-case and collapse whitespace — how free-text answers are compared and bucketed."""
    return " ".join((text or "").lower().split())


# ---------------------------------------------------------------------------
# Image references (T8 D4/D5)
# ---------------------------------------------------------------------------

_IMAGE_ID = re.compile(r"[0-9a-f]{32}")
#: Types whose options can carry pictures (``optionImages``).
OPTION_IMAGE_TYPES = ("multiple_choice", "multi_select")


def is_image_id(value: object) -> bool:
    """An image id: 32 lower-case hex characters (uuid4().hex)."""
    return isinstance(value, str) and _IMAGE_ID.fullmatch(value) is not None


def _validate_common_config(q_type: str, config: dict) -> None:
    """Image keys every type shares, and where the type-specific ones may appear."""
    prompt = config.get("promptImageId")
    if prompt is not None and not is_image_id(prompt):
        raise ValueError("promptImageId must be an image id or null")
    if "optionImages" in config and q_type not in OPTION_IMAGE_TYPES:
        raise ValueError(f"optionImages isn't available on {q_type} questions")
    if "image" in config and q_type != "pin_drop":
        raise ValueError(f"an image background isn't available on {q_type} questions")


def _validate_option_images(config: dict) -> None:
    images = config.get("optionImages")
    if images is None:
        return
    if not isinstance(images, list) or len(images) != len(config["options"]):
        raise ValueError("optionImages must be a list as long as options")
    if any(i is not None and not is_image_id(i) for i in images):
        raise ValueError("optionImages entries must be image ids or null")


def _with_prompt_image(out: dict, config: dict) -> dict:
    """Add the prompt image to an allow-listed client config, when there is one."""
    if config.get("promptImageId"):
        out["promptImageId"] = config["promptImageId"]
    return out


class QuestionType:
    """Base handler. Subclasses override what their type needs."""

    name: str = ""
    #: Results show every submitted value (``answer_value``) instead of bucket counts.
    value_based: bool = False

    def validate_structure(
        self, grading_type: str, config: dict, answer_data: dict
    ) -> None:
        pass

    def validate_answer(self, question: QuestionLike, answer: dict) -> None:
        pass

    def score(self, question: QuestionLike, answer: dict) -> ScoreResult:
        return _NO_SCORE

    def reveal(self, question: QuestionLike) -> dict:
        return {}

    def answer_keys(self, answer: dict) -> list[str]:
        return []

    def answer_value(self, answer: dict) -> Any:
        return None

    def client_config(self, config: dict) -> dict:
        return config


# ---------------------------------------------------------------------------
# Existing types
# ---------------------------------------------------------------------------


class MultipleChoice(QuestionType):
    name = "multiple_choice"

    def validate_structure(self, grading_type, config, answer_data):
        opts = config.get("options")
        if not isinstance(opts, list) or len(opts) < 2:
            raise ValueError(
                "multiple_choice config must have 'options' list with at least 2 items"
            )
        _validate_option_images(config)
        if grading_type == "ACCURACY":
            pts = answer_data.get("answer_points")
            if not isinstance(pts, list) or len(pts) != len(opts):
                raise ValueError(
                    "ACCURACY multiple_choice answer_data must have 'answer_points' list matching options length"
                )
            if any(not isinstance(p, (int, float)) or p < 0 for p in pts):
                raise ValueError("answer_points values must be non-negative numbers")

    def score(self, question, answer):
        selected = answer.get("selectedIndex")
        if selected is None:
            return _NO_SCORE
        pts_list: list[float] = question.answer_data.get("answer_points", [])
        if not (0 <= selected < len(pts_list)):
            return _NO_SCORE
        points = pts_list[selected]
        return ScoreResult(
            points_awarded=points, is_correct=(points == question.points_value)
        )

    def reveal(self, question):
        pts: list[float] = question.answer_data.get("answer_points", [])
        correct = [i for i, p in enumerate(pts) if p >= question.points_value]
        return {"type": "multiple_choice", "correctIndices": correct}

    def answer_keys(self, answer):
        idx = answer.get("selectedIndex")
        return [str(idx)] if idx is not None else []


class TrueFalse(QuestionType):
    name = "true_false"

    def validate_structure(self, grading_type, config, answer_data):
        if grading_type == "ACCURACY":
            pts = answer_data.get("answer_points")
            if not isinstance(pts, dict) or set(pts.keys()) != {"true", "false"}:
                raise ValueError(
                    "ACCURACY true_false answer_data must have 'answer_points' with 'true' and 'false' keys"
                )

    def score(self, question, answer):
        selected = answer.get("selectedValue")
        if selected is None:
            return _NO_SCORE
        pts_map: dict = question.answer_data.get("answer_points", {})
        points = pts_map.get("true" if selected else "false", 0)
        return ScoreResult(
            points_awarded=points, is_correct=(points == question.points_value)
        )

    def reveal(self, question):
        pts_map: dict = question.answer_data.get("answer_points", {})
        correct_true = pts_map.get("true", 0) >= question.points_value
        return {"type": "true_false", "correctValue": correct_true}

    def answer_keys(self, answer):
        val = answer.get("selectedValue")
        if val is None:
            return []
        return ["true" if val else "false"]


class FillInTheBlank(QuestionType):
    name = "fill_in_the_blank"

    def validate_structure(self, grading_type, config, answer_data):
        if grading_type != "ACCURACY":
            return
        answers = answer_data.get("acceptedAnswers")
        if not isinstance(answers, list) or len(answers) == 0:
            raise ValueError(
                "ACCURACY fill_in_the_blank answer_data must have 'acceptedAnswers' list with at least one item"
            )
        if any(not isinstance(a, str) or not a.strip() for a in answers):
            raise ValueError("acceptedAnswers entries must be non-empty strings")
        pts = answer_data.get("answerPoints")
        if not isinstance(pts, list) or len(pts) != len(answers):
            raise ValueError(
                "ACCURACY fill_in_the_blank answer_data must have 'answerPoints' list matching acceptedAnswers length"
            )
        if any(not isinstance(p, (int, float)) or p < 0 for p in pts):
            raise ValueError("answerPoints values must be non-negative numbers")
        edit_dist = answer_data.get("editDistance", 0)
        if not isinstance(edit_dist, int) or edit_dist < 0:
            raise ValueError("editDistance must be a non-negative integer")

    def score(self, question, answer):
        text = _normalize_text(answer.get("text"))
        if not text:
            return _NO_SCORE
        accepted = [
            _normalize_text(a) for a in question.answer_data.get("acceptedAnswers", [])
        ]
        answer_pts: list[float] = question.answer_data.get("answerPoints", [])
        max_dist = int(question.answer_data.get("editDistance", 0))
        best: float = 0.0
        for i, a in enumerate(accepted):
            if Levenshtein.distance(text, a) <= max_dist:
                pts = answer_pts[i] if i < len(answer_pts) else question.points_value
                best = max(best, pts)
        return ScoreResult(
            points_awarded=best, is_correct=(best >= question.points_value)
        )

    def reveal(self, question):
        return {
            "type": "fill_in_the_blank",
            "acceptedAnswers": question.answer_data.get("acceptedAnswers", []),
            "editDistance": question.answer_data.get("editDistance", 0),
        }

    def answer_keys(self, answer):
        text = _normalize_text(answer.get("text"))
        return [text] if text else []


class MultiSelect(QuestionType):
    name = "multi_select"

    def validate_structure(self, grading_type, config, answer_data):
        opts = config.get("options")
        if not isinstance(opts, list) or len(opts) < 2:
            raise ValueError(
                "multi_select config must have 'options' list with at least 2 items"
            )
        _validate_option_images(config)
        if grading_type == "ACCURACY":
            pts = answer_data.get("answer_points")
            if not isinstance(pts, list) or len(pts) != len(opts):
                raise ValueError(
                    "ACCURACY multi_select answer_data must have 'answer_points' list matching options length"
                )
            if any(not isinstance(p, (int, float)) for p in pts):
                raise ValueError("answer_points values must be numbers")

    def validate_answer(self, question, answer):
        indices = answer.get("selectedIndices")
        if not isinstance(indices, list) or not all(
            isinstance(i, int) for i in indices
        ):
            raise ValueError(
                "multi_select answer must include selectedIndices as a list of integers"
            )
        num_opts = len(question.config.get("options", []))
        if any(not (0 <= i < num_opts) for i in indices):
            raise ValueError("selectedIndices contains an out-of-bounds index")

    def score(self, question, answer):
        selected = answer.get("selectedIndices")
        if not isinstance(selected, list):
            return _NO_SCORE
        pts_list: list[float] = question.answer_data.get("answer_points", [])
        raw = sum(
            pts_list[i]
            for i in selected
            if isinstance(i, int) and 0 <= i < len(pts_list)
        )
        score = max(0.0, raw)
        return ScoreResult(
            points_awarded=score,
            is_correct=(score >= question.points_value and question.points_value > 0),
        )

    def reveal(self, question):
        return {
            "type": "multi_select",
            "answerPoints": question.answer_data.get("answer_points", []),
        }

    def answer_keys(self, answer):
        indices = answer.get("selectedIndices")
        if not isinstance(indices, list):
            return []
        return [str(i) for i in indices if isinstance(i, int)]


# ---------------------------------------------------------------------------
# New types (T7): distance-scored, value-based results
# ---------------------------------------------------------------------------

#: Tolerance for "exactly on the boundary" comparisons (snapped pins, whole numbers).
EPSILON = 1e-9
GRID_LIMIT = 1000
MAX_GRID_CELLS = 20
ESTIMATE_LIMIT = 1e12
MAX_UNIT_LENGTH = 20
#: Largest radius on an image, in image widths: covers the whole picture even at 1:2,
#: whose diagonal is ≈ 1.12 widths (T8 D5).
IMAGE_MAX_RADIUS = 1.5


def falloff_points(
    distance: float, full: float, zero: float, points_value: float
) -> float:
    """Full points within `full`, linear falloff to 0 at `zero`, rounded to 2 dp."""
    if distance <= full + EPSILON:
        points = points_value
    elif distance >= zero:
        points = 0.0
    else:
        points = points_value * (zero - distance) / (zero - full)
    return round(points, 2)


def _is_number(v: object) -> bool:
    """A finite JSON number. bool is an int subclass and json.loads accepts NaN/Infinity."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _is_whole(v: float) -> bool:
    return abs(v - round(v)) <= EPSILON


def _require_number(v: object, what: str, limit: float) -> float:
    if not _is_number(v):
        raise ValueError(f"{what} must be a finite number")
    if abs(v) > limit:
        raise ValueError(f"{what} must be between -{limit:g} and {limit:g}")
    return v


def _optional_bool(config: dict, key: str) -> None:
    if key in config and not isinstance(config[key], bool):
        raise ValueError(f"config '{key}' must be true or false")


def _check_falloff(full: object, zero: object, unit: str) -> None:
    if not _is_number(full) or not _is_number(zero):
        raise ValueError(f"{unit} full and zero distances must be finite numbers")
    if not 0 <= full < zero:
        raise ValueError(f"{unit}: need 0 ≤ full < zero")


class PinDrop(QuestionType):
    """
    Place a point on a coordinate grid, or on an uploaded image (T8); scored by
    distance to the target (canvas). Grid coordinates are grid units; image
    coordinates are fractions of the image (x across, y down), with distances
    measured in image-width units so a circle stays a circle (T7 D1, T8 D5).
    """

    name = "pin_drop"
    value_based = True

    _GRID_KEYS = ("xMin", "xMax", "yMin", "yMax", "step")

    def validate_structure(self, grading_type, config, answer_data):
        has_grid, has_image = "grid" in config, "image" in config
        if has_grid == has_image:
            raise ValueError("pin_drop config needs exactly one of 'grid' or 'image'")
        if has_image:
            self._validate_image(config)
        else:
            self._validate_grid(config)

        if grading_type != "ACCURACY":
            return
        target = answer_data.get("target")
        if not isinstance(target, dict):
            raise ValueError("ACCURACY pin_drop answer_data must have 'target' {x, y}")
        x = _require_number(target.get("x"), "target.x", GRID_LIMIT)
        y = _require_number(target.get("y"), "target.y", GRID_LIMIT)
        if not self._inside(config, x, y):
            raise ValueError(f"target must be inside the {self._surface(config)}")
        _check_falloff(
            answer_data.get("fullRadius"), answer_data.get("zeroRadius"), "radius"
        )
        if has_image and answer_data["zeroRadius"] > IMAGE_MAX_RADIUS:
            raise ValueError(
                f"on an image, radii are fractions of its width (at most {IMAGE_MAX_RADIUS})"
            )

    def _validate_grid(self, config):
        grid = config.get("grid")
        if not isinstance(grid, dict):
            raise ValueError(
                "pin_drop config must have 'grid' with xMin, xMax, yMin, yMax, step"
            )
        for key in self._GRID_KEYS:
            _require_number(grid.get(key), f"grid.{key}", GRID_LIMIT)
        if grid["xMin"] >= grid["xMax"] or grid["yMin"] >= grid["yMax"]:
            raise ValueError("grid needs xMin < xMax and yMin < yMax")
        if grid["step"] <= 0:
            raise ValueError("grid.step must be greater than 0")
        width, height = grid["xMax"] - grid["xMin"], grid["yMax"] - grid["yMin"]
        for axis, span in (("x", width), ("y", height)):
            cells = span / grid["step"]
            if not _is_whole(cells):
                raise ValueError(f"the {axis} range must be a whole number of steps")
            if round(cells) > MAX_GRID_CELLS:
                raise ValueError(
                    f"the {axis} axis has {round(cells)} cells; at most "
                    f"{MAX_GRID_CELLS} fit on a phone"
                )
        if not 0.5 <= width / height <= 2:
            raise ValueError("the grid's x:y range ratio must be between 1:2 and 2:1")
        _optional_bool(config, "snap")

    @staticmethod
    def _validate_image(config):
        image = config.get("image")
        if not isinstance(image, dict) or not is_image_id(image.get("imageId")):
            raise ValueError("pin_drop 'image' must be {imageId: <image id>}")
        for key in ("width", "height"):
            if key in image:
                value = image[key]
                if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                    raise ValueError(f"image.{key} must be a positive whole number")
        if config.get("snap") not in (None, False):
            raise ValueError("snap isn't available on an image background")

    @staticmethod
    def _surface(config) -> str:
        return "image" if "image" in config else "grid"

    @staticmethod
    def _bounds(config) -> tuple[float, float, float, float]:
        """(xMin, xMax, yMin, yMax) of the answer area."""
        if "image" in config:
            return 0.0, 1.0, 0.0, 1.0
        grid = config.get("grid") or {}
        return grid["xMin"], grid["xMax"], grid["yMin"], grid["yMax"]

    @classmethod
    def _inside(cls, config, x: float, y: float) -> bool:
        x_min, x_max, y_min, y_max = cls._bounds(config)
        return (
            x_min - EPSILON <= x <= x_max + EPSILON
            and y_min - EPSILON <= y <= y_max + EPSILON
        )

    @staticmethod
    def _aspect(config) -> float:
        """height / width for an image (distances in width units); 1 on a grid."""
        image = config.get("image")
        if isinstance(image, dict) and image.get("width") and image.get("height"):
            return image["height"] / image["width"]
        return 1.0

    @staticmethod
    def _point(answer: dict) -> tuple[float, float] | None:
        point = answer.get("point")
        if not isinstance(point, dict):
            return None
        x, y = point.get("x"), point.get("y")
        if not (_is_number(x) and _is_number(y)):
            return None
        return x, y

    def validate_answer(self, question, answer):
        point = self._point(answer)
        if point is None:
            raise ValueError(
                "pin_drop answer must be {point: {x, y}} with finite numbers"
            )
        if not self._inside(question.config or {}, *point):
            raise ValueError(
                f"The pin must be inside the {self._surface(question.config or {})}"
            )

    def score(self, question, answer):
        point = self._point(answer)
        target = question.answer_data.get("target") or {}
        if point is None or not _is_number(target.get("x")):
            return _NO_SCORE
        aspect = self._aspect(question.config or {})
        distance = math.hypot(point[0] - target["x"], (point[1] - target["y"]) * aspect)
        full = question.answer_data["fullRadius"]
        return ScoreResult(
            points_awarded=falloff_points(
                distance,
                full,
                question.answer_data["zeroRadius"],
                question.points_value,
            ),
            is_correct=distance <= full + EPSILON,
        )

    def reveal(self, question):
        ad = question.answer_data
        return {
            "type": "pin_drop",
            "target": ad.get("target"),
            "fullRadius": ad.get("fullRadius"),
            "zeroRadius": ad.get("zeroRadius"),
        }

    def answer_value(self, answer):
        point = self._point(answer)
        return {"x": point[0], "y": point[1]} if point else None

    def client_config(self, config):
        if "image" in config:
            image = config["image"]
            out = {
                "image": {
                    "imageId": image.get("imageId"),
                    "width": image.get("width"),
                    "height": image.get("height"),
                },
                "snap": False,
            }
        else:
            out = {"grid": config.get("grid"), "snap": bool(config.get("snap", False))}
        return _with_prompt_image(out, config)


class Estimate(QuestionType):
    """Guess one number; scored by how far off it is (party)."""

    name = "estimate"
    value_based = True

    def validate_structure(self, grading_type, config, answer_data):
        unit = config.get("unit")
        if unit is not None and (
            not isinstance(unit, str) or len(unit.strip()) > MAX_UNIT_LENGTH
        ):
            raise ValueError(
                f"unit must be text of at most {MAX_UNIT_LENGTH} characters"
            )
        _optional_bool(config, "integer")

        if grading_type != "ACCURACY":
            return
        answer = _require_number(answer_data.get("answer"), "answer", ESTIMATE_LIMIT)
        if config.get("integer") and not _is_whole(answer):
            raise ValueError("answer must be a whole number when 'integer' is set")
        tolerance = answer_data.get("tolerance")
        if not isinstance(tolerance, dict) or tolerance.get("mode") not in (
            "relative",
            "absolute",
        ):
            raise ValueError(
                "ACCURACY estimate answer_data must have 'tolerance' with mode "
                "'relative' or 'absolute'"
            )
        _check_falloff(tolerance.get("full"), tolerance.get("zero"), "tolerance")
        if tolerance["mode"] == "relative" and answer == 0:
            raise ValueError("relative tolerance needs a non-zero answer; use absolute")

    def validate_answer(self, question, answer):
        value = answer.get("value")
        if not _is_number(value):
            raise ValueError("estimate answer must be {value: <finite number>}")
        if abs(value) > ESTIMATE_LIMIT:
            raise ValueError("That number is too large")
        if question.config.get("integer") and not _is_whole(value):
            raise ValueError("This question needs a whole number")

    @staticmethod
    def error(answer_data: dict, value: float) -> float:
        """Distance of a guess from the answer: percent (relative) or units (absolute)."""
        true_value = answer_data["answer"]
        diff = abs(value - true_value)
        if answer_data["tolerance"]["mode"] == "relative":
            return diff / abs(true_value) * 100
        return diff

    def score(self, question, answer):
        value = answer.get("value")
        if not _is_number(value):
            return _NO_SCORE
        tolerance = question.answer_data["tolerance"]
        err = self.error(question.answer_data, value)
        return ScoreResult(
            points_awarded=falloff_points(
                err, tolerance["full"], tolerance["zero"], question.points_value
            ),
            is_correct=err <= tolerance["full"] + EPSILON,
        )

    def reveal(self, question):
        return {
            "type": "estimate",
            "answer": question.answer_data.get("answer"),
            "unit": (question.config.get("unit") or "").strip(),
            "tolerance": question.answer_data.get("tolerance"),
        }

    def answer_value(self, answer):
        value = answer.get("value")
        return value if _is_number(value) else None

    def client_config(self, config):
        out = {
            "unit": (config.get("unit") or "").strip(),
            "integer": bool(config.get("integer", False)),
        }
        return _with_prompt_image(out, config)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


HANDLERS: dict[str, QuestionType] = {
    h.name: h
    for h in (
        MultipleChoice(),
        TrueFalse(),
        FillInTheBlank(),
        MultiSelect(),
        PinDrop(),
        Estimate(),
    )
}
QUESTION_TYPES: tuple[str, ...] = tuple(HANDLERS)


def validate_structure(
    q_type: str, grading_type: str, config: dict, answer_data: dict
) -> None:
    """Raise ValueError if config/answer_data don't fit the question type and grading."""
    handler = HANDLERS.get(q_type)
    if handler is None:
        raise ValueError(f"Unknown question type '{q_type}'")
    _validate_common_config(q_type, config)
    handler.validate_structure(grading_type, config, answer_data)


def validate_answer(question: QuestionLike, answer: dict) -> None:
    """Raise ValueError (message safe to show the player) for a malformed answer."""
    handler = HANDLERS.get(question.type)
    if handler is not None:
        handler.validate_answer(question, answer)


def score_answer(question: QuestionLike, answer: dict) -> ScoreResult:
    """
    Points for a player's answer.
    COMPLETENESS: any answer = full points, no answer = 0
    ACCURACY:     the type's own rule
    """
    if not answer:
        return _NO_SCORE
    if question.grading_type == "COMPLETENESS":
        return ScoreResult(points_awarded=question.points_value, is_correct=True)
    handler = HANDLERS.get(question.type)
    return handler.score(question, answer) if handler else _NO_SCORE


def reveal_answer(question: QuestionLike) -> dict:
    """
    Client-safe correct-answer facts derived from answer_data.
    answer_data is NEVER forwarded directly — only derived facts are sent.
    """
    if question.grading_type == "COMPLETENESS":
        return {"type": "completeness"}
    handler = HANDLERS.get(question.type)
    return handler.reveal(question) if handler else {}


def answer_keys(q_type: str, answer: dict | None) -> list[str]:
    """Distribution buckets one answer counts towards (count-based types)."""
    handler = HANDLERS.get(q_type)
    if not answer or handler is None:
        return []
    return handler.answer_keys(answer)


def answer_value(q_type: str, answer: dict | None) -> Any:
    """The raw value of one answer for value-based results; None otherwise."""
    handler = HANDLERS.get(q_type)
    if not answer or handler is None:
        return None
    return handler.answer_value(answer)


def is_value_based(q_type: str) -> bool:
    handler = HANDLERS.get(q_type)
    return bool(handler and handler.value_based)


def client_config(q_type: str, config: dict | None) -> dict:
    """The config fields players may see before the reveal."""
    handler = HANDLERS.get(q_type)
    config = config or {}
    return handler.client_config(config) if handler else config


def referenced_image_ids(config: dict | None) -> dict:
    """
    The image ids a question's config points at (T8 D4/D5), without validating them:
    {"prompt": id | None, "options": [ids], "pin_drop": id | None}. Non-string values
    are skipped, so this is safe on unvalidated or legacy config.
    """
    config = config or {}
    prompt = config.get("promptImageId")
    options = config.get("optionImages")
    image = config.get("image")
    pin = image.get("imageId") if isinstance(image, dict) else None
    return {
        "prompt": prompt if isinstance(prompt, str) else None,
        "options": [i for i in options if isinstance(i, str)]
        if isinstance(options, list)
        else [],
        "pin_drop": pin if isinstance(pin, str) else None,
    }
