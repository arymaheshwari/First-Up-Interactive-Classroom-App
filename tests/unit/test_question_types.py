"""
Unit tests for the question-type registry (backend/app/services/question_types.py).

U6 (registry parity) pins the four pre-existing types to the exact scores, reveals and
chart buckets the scattered per-type code produced before it moved into the registry.

Run with:
    cd tests/unit && PYTHONPATH=../../backend pytest test_question_types.py -v
"""

from __future__ import annotations

import pytest

from app.services import question_types as qt
from app.services.question_types import QuestionFacts


def _q(q_type, answer_data, config=None, points=10.0, grading="ACCURACY"):
    return QuestionFacts(q_type, grading, config or {}, answer_data, points)


MC = _q(
    "multiple_choice",
    {"answer_points": [0, 10, 5, 0]},
    {"options": ["a", "b", "c", "d"]},
)
TF = _q("true_false", {"answer_points": {"true": 10, "false": 0}})
FITB = _q(
    "fill_in_the_blank",
    {
        "acceptedAnswers": ["New York", "NYC"],
        "answerPoints": [10, 6],
        "editDistance": 1,
    },
)
MS = _q(
    "multi_select",
    {"answer_points": [5, 5, -3, 0]},
    {"options": ["a", "b", "c", "d"]},
)


# ---------------------------------------------------------------------------
# U6 — scoring parity with the pre-registry calculate_score
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question, answer, points, correct",
    [
        (MC, {"selectedIndex": 1}, 10, True),
        (MC, {"selectedIndex": 2}, 5, False),
        (MC, {"selectedIndex": 9}, 0, False),
        (MC, {"selectedIndex": None}, 0, False),
        (TF, {"selectedValue": True}, 10, True),
        (TF, {"selectedValue": False}, 0, False),
        (FITB, {"text": "  new   york "}, 10, True),
        (FITB, {"text": "new yrok"}, 0, False),  # transposition = distance 2
        (FITB, {"text": "nyc"}, 6, False),
        (FITB, {"text": "nyx"}, 6, False),  # within editDistance 1
        (FITB, {"text": "   "}, 0, False),
        (MS, {"selectedIndices": [0, 1]}, 10, True),
        (MS, {"selectedIndices": [0, 2]}, 2, False),
        (MS, {"selectedIndices": [2]}, 0, False),  # floored at 0
        (MS, {"selectedIndices": "0"}, 0, False),
    ],
)
def test_accuracy_scoring_parity(question, answer, points, correct):
    result = qt.score_answer(question, answer)
    assert result.points_awarded == points
    assert result.is_correct is correct


@pytest.mark.parametrize("question", [MC, TF, FITB, MS])
def test_empty_answer_scores_zero(question):
    assert qt.score_answer(question, {}).points_awarded == 0


@pytest.mark.parametrize("question", [MC, TF, FITB, MS])
def test_completeness_gives_full_points(question):
    q = question._replace(grading_type="COMPLETENESS")
    result = qt.score_answer(q, {"anything": 1})
    assert (result.points_awarded, result.is_correct) == (10.0, True)


def test_unknown_type_scores_zero_and_reveals_nothing():
    q = _q("no_such_type", {})
    assert qt.score_answer(q, {"x": 1}).points_awarded == 0
    assert qt.reveal_answer(q) == {}


# ---------------------------------------------------------------------------
# U6 — reveal and chart-bucket parity
# ---------------------------------------------------------------------------


def test_reveals():
    assert qt.reveal_answer(MC) == {"type": "multiple_choice", "correctIndices": [1]}
    assert qt.reveal_answer(TF) == {"type": "true_false", "correctValue": True}
    assert qt.reveal_answer(FITB) == {
        "type": "fill_in_the_blank",
        "acceptedAnswers": ["New York", "NYC"],
        "editDistance": 1,
    }
    assert qt.reveal_answer(MS) == {
        "type": "multi_select",
        "answerPoints": [5, 5, -3, 0],
    }
    assert qt.reveal_answer(MC._replace(grading_type="COMPLETENESS")) == {
        "type": "completeness"
    }


@pytest.mark.parametrize(
    "q_type, answer, keys",
    [
        ("multiple_choice", {"selectedIndex": 2}, ["2"]),
        ("multiple_choice", {}, []),
        ("true_false", {"selectedValue": False}, ["false"]),
        ("true_false", {"selectedValue": True}, ["true"]),
        ("fill_in_the_blank", {"text": "  New   York "}, ["new york"]),
        ("fill_in_the_blank", {"text": ""}, []),
        ("multi_select", {"selectedIndices": [0, 3]}, ["0", "3"]),
        ("multi_select", {"selectedIndices": None}, []),
        ("multi_select", None, []),
    ],
)
def test_answer_keys(q_type, answer, keys):
    assert qt.answer_keys(q_type, answer) == keys


# ---------------------------------------------------------------------------
# Answer validation and client config for the existing types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        {"selectedIndices": "0"},
        {"selectedIndices": [0, "1"]},
        {"selectedIndices": [4]},
        {},
    ],
)
def test_multi_select_answer_rejected(answer):
    with pytest.raises(ValueError):
        qt.validate_answer(MS, answer)


@pytest.mark.parametrize("question", [MC, TF, FITB])
def test_other_existing_types_accept_any_answer(question):
    qt.validate_answer(question, {"whatever": "x"})


def test_existing_types_send_config_unchanged():
    config = {"options": ["a", "b"], "extra": 1}
    for q_type in (
        "multiple_choice",
        "true_false",
        "fill_in_the_blank",
        "multi_select",
    ):
        assert qt.client_config(q_type, config) == config


def test_unknown_type_rejected_by_structure_validation():
    with pytest.raises(ValueError, match="Unknown question type"):
        qt.validate_structure("no_such_type", "ACCURACY", {}, {})


# ===========================================================================
# New types (T7 spec §8.1)
# ===========================================================================

GRID = {"xMin": -5, "xMax": 5, "yMin": -5, "yMax": 5, "step": 1}
PIN = _q(
    "pin_drop",
    {"target": {"x": 0, "y": 0}, "fullRadius": 1, "zeroRadius": 5},
    {"grid": GRID, "snap": True},
)
EST_ABS = _q(
    "estimate",
    {"answer": 2005, "tolerance": {"mode": "absolute", "full": 1, "zero": 10}},
    {"unit": "year", "integer": True},
)
EST_REL = _q(
    "estimate",
    {"answer": 200, "tolerance": {"mode": "relative", "full": 10, "zero": 50}},
    {"unit": " m "},
)


# ---------------------------------------------------------------------------
# U1 — the shared falloff formula
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "distance, points",
    [(0, 10), (1, 10), (3, 5), (5, 0), (9, 0), (1 + 1e-12, 10), (2, 7.5), (4.9, 0.25)],
)
def test_u1_falloff_points(distance, points):
    assert qt.falloff_points(distance, 1, 5, 10) == points


def test_u1_falloff_rounds_to_two_places():
    assert qt.falloff_points(2, 1, 4, 1) == 0.67


# ---------------------------------------------------------------------------
# U2 / U3 — scoring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "point, points, correct",
    [
        ({"x": 0, "y": 0}, 10, True),
        ({"x": 0.6, "y": 0.8}, 10, True),  # d = 1, on the full-credit boundary
        ({"x": 3, "y": 0}, 5, False),
        ({"x": 3, "y": 4}, 0, False),  # d = 5
        ({"x": -5, "y": -5}, 0, False),
    ],
)
def test_u2_pin_drop_scoring(point, points, correct):
    result = qt.score_answer(PIN, {"point": point})
    assert (result.points_awarded, result.is_correct) == (points, correct)


@pytest.mark.parametrize(
    "question, value, points, correct",
    [
        (EST_ABS, 2005, 10, True),
        (EST_ABS, 2006, 10, True),
        (EST_ABS, 2015, 0, False),  # the year example: 0.5% off, but 10 years
        (EST_ABS, 1999.5, 5, False),  # 5.5 away: 10 * (10 - 5.5) / 9
        (EST_REL, 220, 10, True),  # 10%
        (EST_REL, 140, 5, False),  # 30%, halfway between 10 and 50
        (EST_REL, 0, 0, False),
    ],
)
def test_u3_estimate_scoring(question, value, points, correct):
    result = qt.score_answer(question, {"value": value})
    assert result.points_awarded == pytest.approx(points, abs=0.01)
    assert result.is_correct is correct


@pytest.mark.parametrize(
    "question, answer",
    [(PIN, {"point": {"x": 5, "y": 5}}), (EST_ABS, {"value": 1})],
)
def test_u2_u3_completeness_any_valid_answer(question, answer):
    q = question._replace(grading_type="COMPLETENESS", answer_data={})
    qt.validate_structure(q.type, q.grading_type, q.config, q.answer_data)
    assert qt.score_answer(q, answer).points_awarded == 10


# ---------------------------------------------------------------------------
# U4 — structure validation
# ---------------------------------------------------------------------------


def _grid(**kw):
    return {**GRID, **kw}


PIN_AD = {"target": {"x": 0, "y": 0}, "fullRadius": 1, "zeroRadius": 3}
EST_AD = {"answer": 10, "tolerance": {"mode": "absolute", "full": 1, "zero": 5}}


@pytest.mark.parametrize(
    "config, answer_data",
    [
        ({}, PIN_AD),
        ({"grid": _grid(xMin=5, xMax=-5)}, PIN_AD),
        ({"grid": _grid(step=0)}, PIN_AD),
        ({"grid": _grid(step=-1)}, PIN_AD),
        ({"grid": _grid(xMin=-15, xMax=15, yMin=-10, yMax=10)}, PIN_AD),  # 30 cells
        ({"grid": _grid(step=0.3)}, PIN_AD),  # 10 / 0.3 is not whole
        ({"grid": _grid(yMin=-1, yMax=1)}, PIN_AD),  # ratio 5:1
        ({"grid": _grid(xMax=True)}, PIN_AD),
        ({"grid": _grid(xMax=float("nan"))}, PIN_AD),
        ({"grid": _grid(xMin=-2000)}, PIN_AD),
        ({"grid": _grid(xMax="5")}, PIN_AD),
        ({"grid": GRID, "snap": "yes"}, PIN_AD),
        ({"grid": GRID}, {**PIN_AD, "target": {"x": 6, "y": 0}}),
        ({"grid": GRID}, {**PIN_AD, "target": {"x": 0}}),
        ({"grid": GRID}, {**PIN_AD, "fullRadius": 3}),  # full == zero
        ({"grid": GRID}, {**PIN_AD, "fullRadius": -1}),
        ({"grid": GRID}, {**PIN_AD, "zeroRadius": float("inf")}),
        ({"grid": GRID}, {}),
    ],
)
def test_u4_pin_drop_bad_structure(config, answer_data):
    with pytest.raises(ValueError):
        qt.validate_structure("pin_drop", "ACCURACY", config, answer_data)


@pytest.mark.parametrize(
    "config, answer_data",
    [
        ({"unit": "x" * 21}, EST_AD),
        ({"unit": 5}, EST_AD),
        ({"integer": 1}, EST_AD),
        ({"integer": True}, {**EST_AD, "answer": 10.5}),
        ({}, {**EST_AD, "answer": True}),
        ({}, {**EST_AD, "answer": float("nan")}),
        ({}, {**EST_AD, "answer": 2e12}),
        ({}, {**EST_AD, "tolerance": {"mode": "percent", "full": 1, "zero": 5}}),
        ({}, {**EST_AD, "tolerance": {"mode": "absolute", "full": 5, "zero": 5}}),
        ({}, {**EST_AD, "tolerance": {"mode": "absolute", "full": 1}}),
        ({}, {"answer": 0, "tolerance": {"mode": "relative", "full": 1, "zero": 5}}),
        ({}, {}),
    ],
)
def test_u4_estimate_bad_structure(config, answer_data):
    with pytest.raises(ValueError):
        qt.validate_structure("estimate", "ACCURACY", config, answer_data)


def test_u4_valid_shapes_accepted():
    qt.validate_structure("pin_drop", "ACCURACY", {"grid": GRID, "snap": True}, PIN_AD)
    # 0.1 steps over a range of 2 are 20 cells, despite float error
    tenth = {"xMin": 0, "xMax": 2, "yMin": 0, "yMax": 1.5, "step": 0.1}
    tenth_ad = {**PIN_AD, "target": {"x": 1, "y": 1}}
    qt.validate_structure("pin_drop", "ACCURACY", {"grid": tenth}, tenth_ad)
    qt.validate_structure(
        "estimate", "ACCURACY", {"unit": "kg", "integer": True}, EST_AD
    )
    qt.validate_structure(
        "estimate", "ACCURACY", {"integer": True}, {**EST_AD, "answer": 10.0}
    )


# ---------------------------------------------------------------------------
# U5 — answer validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"point": None},
        {"point": {"x": 1}},
        {"point": {"x": "1", "y": 1}},
        {"point": {"x": True, "y": 1}},
        {"point": {"x": float("nan"), "y": 1}},
        {"point": {"x": 1, "y": float("inf")}},
        {"point": {"x": 5.5, "y": 0}},
        {"point": {"x": 0, "y": -6}},
    ],
)
def test_u5_pin_drop_bad_answers(answer):
    with pytest.raises(ValueError):
        qt.validate_answer(PIN, answer)


@pytest.mark.parametrize(
    "question, answer",
    [
        (EST_REL, {}),
        (EST_REL, {"value": "12"}),
        (EST_REL, {"value": False}),
        (EST_REL, {"value": float("nan")}),
        (EST_REL, {"value": float("-inf")}),
        (EST_REL, {"value": 1e13}),
        (EST_ABS, {"value": 2005.5}),
    ],
)
def test_u5_estimate_bad_answers(question, answer):
    with pytest.raises(ValueError):
        qt.validate_answer(question, answer)


def test_u5_good_answers_accepted():
    qt.validate_answer(PIN, {"point": {"x": 5, "y": -5}})  # on the edge
    qt.validate_answer(PIN, {"point": {"x": 0.25, "y": 1.5}})
    qt.validate_answer(EST_ABS, {"value": 2005.0})  # 5.0 counts as whole
    qt.validate_answer(EST_REL, {"value": -3.75})


# ---------------------------------------------------------------------------
# U7 — boundary is_correct; U8 — client config allow-list
# ---------------------------------------------------------------------------


def test_u7_snapped_pin_exactly_on_full_radius():
    q = PIN._replace(
        answer_data={"target": {"x": 0, "y": 0}, "fullRadius": 5, "zeroRadius": 6}
    )
    result = qt.score_answer(q, {"point": {"x": 3, "y": 4}})
    assert (result.points_awarded, result.is_correct) == (10, True)


def test_u7_estimate_exactly_full_away():
    q = EST_REL._replace(
        answer_data={
            "answer": 0.3,
            "tolerance": {"mode": "absolute", "full": 0.1, "zero": 1},
        }
    )
    result = qt.score_answer(q, {"value": 0.4})  # 0.4 - 0.3 = 0.10000000000000003
    assert (result.points_awarded, result.is_correct) == (10, True)


def test_u8_client_config_allow_list():
    leaky = {"grid": GRID, "snap": True, "target": {"x": 0, "y": 0}, "answer": 1}
    assert qt.client_config("pin_drop", leaky) == {"grid": GRID, "snap": True}
    assert qt.client_config("estimate", {**leaky, "unit": " m ", "integer": True}) == {
        "unit": "m",
        "integer": True,
    }
    assert qt.client_config("estimate", {}) == {"unit": "", "integer": False}


def test_reveals_and_values_for_new_types():
    assert qt.reveal_answer(PIN) == {
        "type": "pin_drop",
        "target": {"x": 0, "y": 0},
        "fullRadius": 1,
        "zeroRadius": 5,
    }
    assert qt.reveal_answer(EST_REL) == {
        "type": "estimate",
        "answer": 200,
        "unit": "m",
        "tolerance": {"mode": "relative", "full": 10, "zero": 50},
    }
    assert qt.answer_value("pin_drop", {"point": {"x": 1, "y": 2}}) == {"x": 1, "y": 2}
    assert qt.answer_value("estimate", {"value": 7}) == 7
    assert qt.answer_value("estimate", {"value": "7"}) is None
    assert qt.answer_keys("pin_drop", {"point": {"x": 1, "y": 2}}) == []
    assert qt.is_value_based("estimate") and not qt.is_value_based("multi_select")


# ===========================================================================
# T8 — image references (docs/plans/t8-image-support.md §8.1 U11)
# ===========================================================================

IMG = "0123456789abcdef0123456789abcdef"
IMAGE_PIN = _q(
    "pin_drop",
    {"target": {"x": 0.5, "y": 0.5}, "fullRadius": 0.05, "zeroRadius": 0.25},
    {"image": {"imageId": IMG, "width": 200, "height": 100}},
)
IMAGE_AD = {"target": {"x": 0.5, "y": 0.5}, "fullRadius": 0.05, "zeroRadius": 0.25}


@pytest.mark.parametrize(
    "config, answer_data",
    [
        # A target valid on both surfaces, so only the one-of rule can reject it.
        ({"grid": GRID, "image": {"imageId": IMG}}, IMAGE_AD),
        ({}, PIN_AD),  # neither
        ({"image": {"imageId": "nope"}}, IMAGE_AD),
        ({"image": {"imageId": IMG, "width": 0}}, IMAGE_AD),
        ({"image": {"imageId": IMG, "height": True}}, IMAGE_AD),
        ({"image": {"imageId": IMG}, "snap": True}, IMAGE_AD),
        ({"image": {"imageId": IMG}}, {**IMAGE_AD, "target": {"x": 1.2, "y": 0.5}}),
        ({"image": {"imageId": IMG}}, {**IMAGE_AD, "zeroRadius": 1.6}),
    ],
    ids=[
        "grid-and-image",
        "neither",
        "bad-id",
        "zero-width",
        "bool-height",
        "snap-on-image",
        "target-outside",
        "radius-too-big",
    ],
)
def test_u11_pin_drop_image_bad_structure(config, answer_data):
    with pytest.raises(ValueError):
        qt.validate_structure("pin_drop", "ACCURACY", config, answer_data)


def test_u11_pin_drop_image_valid_shapes():
    # width/height are optional on input (the server fills them from the image)
    qt.validate_structure("pin_drop", "ACCURACY", {"image": {"imageId": IMG}}, IMAGE_AD)
    qt.validate_structure(
        "pin_drop",
        "ACCURACY",
        {"image": {"imageId": IMG, "width": 3, "height": 2}},
        IMAGE_AD,
    )
    qt.validate_structure("pin_drop", "COMPLETENESS", {"image": {"imageId": IMG}}, {})


@pytest.mark.parametrize("point", [{"x": -0.1, "y": 0.5}, {"x": 0.5, "y": 1.01}])
def test_u11_image_answers_must_be_fractions(point):
    with pytest.raises(ValueError, match="inside the image"):
        qt.validate_answer(IMAGE_PIN, {"point": point})


def test_u11_aspect_aware_scoring():
    # A 2:1 image (200×100): Δy = 0.1 of the height is only 0.05 of the width.
    hit = qt.score_answer(IMAGE_PIN, {"point": {"x": 0.5, "y": 0.6}})
    assert (hit.points_awarded, hit.is_correct) == (10, True)
    # The same Δ across is 0.1 of the width: partial credit, (0.25 - 0.1) / 0.2 = 0.75.
    across = qt.score_answer(IMAGE_PIN, {"point": {"x": 0.6, "y": 0.5}})
    assert (across.points_awarded, across.is_correct) == (7.5, False)


def test_u11_prompt_image_id_null_or_omitted_are_valid():
    for config in (
        {"options": ["a", "b"]},
        {"options": ["a", "b"], "promptImageId": None},
    ):
        qt.validate_structure(
            "multiple_choice", "ACCURACY", config, {"answer_points": [1, 0]}
        )
    qt.validate_structure(
        "true_false",
        "ACCURACY",
        {"promptImageId": IMG},
        {"answer_points": {"true": 1, "false": 0}},
    )
    with pytest.raises(ValueError):
        qt.validate_structure("true_false", "COMPLETENESS", {"promptImageId": "x"}, {})


@pytest.mark.parametrize(
    "q_type, config, answer_data",
    [
        (
            "multiple_choice",
            {"options": ["a", "b"], "optionImages": [IMG]},
            {"answer_points": [1, 0]},
        ),
        (
            "multi_select",
            {"options": ["a", "b"], "optionImages": [IMG, "bad"]},
            {"answer_points": [1, 0]},
        ),
        (
            "true_false",
            {"optionImages": [IMG, None]},
            {"answer_points": {"true": 1, "false": 0}},
        ),
        ("estimate", {"image": {"imageId": IMG}}, EST_AD),
    ],
    ids=["length-mismatch", "bad-entry", "option-images-on-tf", "image-on-estimate"],
)
def test_u11_image_keys_only_where_they_belong(q_type, config, answer_data):
    with pytest.raises(ValueError):
        qt.validate_structure(q_type, "ACCURACY", config, answer_data)


def test_u11_option_images_and_unknown_keys_accepted():
    qt.validate_structure(
        "multiple_choice",
        "ACCURACY",
        {"options": ["a", "b"], "optionImages": [IMG, None], "somethingElse": 1},
        {"answer_points": [1, 0]},
    )


def test_u11_client_config_carries_image_references_only():
    assert qt.client_config(
        "pin_drop",
        {"image": {"imageId": IMG, "width": 2, "height": 1}, "promptImageId": IMG},
    ) == {
        "image": {"imageId": IMG, "width": 2, "height": 1},
        "snap": False,
        "promptImageId": IMG,
    }
    assert qt.client_config("estimate", {"unit": "kg", "promptImageId": IMG}) == {
        "unit": "kg",
        "integer": False,
        "promptImageId": IMG,
    }


def test_referenced_image_ids_ignores_malformed_values():
    assert qt.referenced_image_ids(
        {"promptImageId": 5, "optionImages": [IMG, None, 3], "image": {"imageId": IMG}}
    ) == {"prompt": None, "options": [IMG], "pin_drop": IMG}
    assert qt.referenced_image_ids(None) == {
        "prompt": None,
        "options": [],
        "pin_drop": None,
    }
