"""
Unit tests: PUT /api/admin/games/{game_id}/questions/{question_id} must enforce the
same structural rules as question creation, evaluated on the merged (stored + update)
question rather than the partial request body.

Runs against the FastAPI app with mocked DB and auth — no Docker stack required.

Run with:
    cd tests/unit && PYTHONPATH=../../backend pytest test_question_update_validation.py -v
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

URL = "/api/admin/games/1/questions/1"


def _question(**overrides):
    from app.models.game import Question

    fields = {
        "id": 1,
        "game_id": 1,
        "type": "multiple_choice",
        "grading_type": "ACCURACY",
        "prompt": "Pick one",
        "config": {"options": ["A", "B", "C", "D"]},
        "answer_data": {"answer_points": [1, 0, 0, 0]},
        "time_limit_seconds": 30,
        "points_value": 1.0,
        "order_index": 0,
        "created_at": datetime(2026, 1, 1),
    }
    fields.update(overrides)
    return Question(**fields)


@pytest.fixture
def stored():
    return {"question": _question()}


@pytest_asyncio.fixture
async def client(stored):
    from app.common.dependencies import require_admin
    from app.database import get_db
    from app.main import app

    mock_db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = lambda: stored["question"]
    mock_db.execute = AsyncMock(return_value=result)
    mock_db.get = AsyncMock(return_value=MagicMock())

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: MagicMock(role="ADMIN")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


class TestStructuralUpdates:
    async def test_partial_type_change_validated_against_stored_fields(
        self, client, stored
    ):
        stored["question"] = _question(
            type="true_false",
            config={},
            answer_data={"answer_points": {"true": 1, "false": 0}},
        )

        r = await client.put(URL, json={"type": "multi_select"})

        assert r.status_code == 422
        assert "multi_select config must have 'options'" in r.text
        assert stored["question"].type == "true_false"

    async def test_answer_points_must_match_stored_options(self, client, stored):
        r = await client.put(URL, json={"answer_data": {"answer_points": [1, 0]}})

        assert r.status_code == 422
        assert "matching options length" in r.text
        assert stored["question"].answer_data == {"answer_points": [1, 0, 0, 0]}

    async def test_switching_to_accuracy_requires_answer_data(self, client, stored):
        stored["question"] = _question(grading_type="COMPLETENESS", answer_data={})

        r = await client.put(URL, json={"grading_type": "ACCURACY"})

        assert r.status_code == 422
        assert stored["question"].grading_type == "COMPLETENESS"

    async def test_valid_structural_update_is_applied(self, client, stored):
        r = await client.put(
            URL,
            json={
                "config": {"options": ["Yes", "No"]},
                "answer_data": {"answer_points": [0, 1]},
            },
        )

        assert r.status_code == 200
        assert r.json()["config"] == {"options": ["Yes", "No"]}
        assert stored["question"].answer_data == {"answer_points": [0, 1]}


class TestNonStructuralUpdates:
    async def test_prompt_edit_allowed_on_previously_invalid_row(self, client, stored):
        stored["question"] = _question(config={"options": ["only one"]})

        r = await client.put(URL, json={"prompt": "Renamed"})

        assert r.status_code == 200
        assert stored["question"].prompt == "Renamed"


class TestErrorShape:
    async def test_update_error_matches_create_error_shape(self, client):
        invalid = {
            "type": "multiple_choice",
            "grading_type": "ACCURACY",
            "prompt": "Pick one",
            "config": {"options": ["A"]},
        }
        create = await client.post("/api/admin/games/1/questions", json=invalid)
        update = await client.put(URL, json={"config": {"options": ["A"]}})

        assert create.status_code == update.status_code == 422
        c, u = create.json(), update.json()
        assert c["error"] == u["error"] == "VALIDATION_ERROR"
        assert c["detail"][0]["msg"] == u["detail"][0]["msg"]
        assert c["detail"][0]["loc"] == u["detail"][0]["loc"] == ["body"]
