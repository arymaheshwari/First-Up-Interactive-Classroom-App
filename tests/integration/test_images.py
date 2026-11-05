"""
T8 image library — upload, serving, access control, replace/delete, limits.

Scenario ids (I1…I19) match docs/plans/t8-image-support.md §8.2.
Runs against the live stack, like the rest of tests/integration. Every image a test
uploads is deleted again by the `t` fixture (images outlive games: they belong to
the course library).
"""

from __future__ import annotations

import base64
import io
import json
import pathlib

import httpx
import pytest
from PIL import Image

from .engine.socket_client import TestSocketClient
from .helpers import Tracker
from .test_question_types import LiveGame, _no_answer_in

MB = 1024 * 1024


class ImageTracker(Tracker):
    """Tracker that also deletes uploaded images (as admin) on cleanup."""

    image_ids: list[str]
    course_ids: list[int]

    def upload(self, course_id: int, data: bytes, name: str, token: str | None = None):
        r = self.call(
            "POST",
            f"/host/courses/{course_id}/images",
            token or self.admin_token,
            files={"file": (name, data, "application/octet-stream")},
        )
        if r.status_code in (200, 201):
            self.image_ids.append(r.json()["id"])
        return r

    def replace(self, image_id: str, data: bytes, name: str, token: str | None = None):
        return self.call(
            "PUT",
            f"/host/images/{image_id}",
            token or self.admin_token,
            files={"file": (name, data, "application/octet-stream")},
        )

    def course(self, guest_policy: str = "OPEN") -> int:
        course_id = super().course(guest_policy)
        self.course_ids.append(course_id)
        return course_id

    def cleanup(self) -> None:
        # Games first: an image still used by a question can't be deleted (409).
        super().cleanup()
        for course_id in self.course_ids:  # includes images that imports created
            listed = self.admin("GET", f"/host/courses/{course_id}/images")
            self.image_ids += [i["id"] for i in listed.json()]
        for image_id in dict.fromkeys(self.image_ids):
            self.admin("DELETE", f"/host/images/{image_id}")


@pytest.fixture
def t(docker_stack, base_url, admin_token):
    tracker = ImageTracker(base_url, admin_token)
    tracker.image_ids = []
    tracker.course_ids = []
    yield tracker
    tracker.cleanup()


def encode(im: Image.Image, fmt: str, **kw) -> bytes:
    buf = io.BytesIO()
    im.save(buf, fmt, **kw)
    return buf.getvalue()


def decode(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def png(w: int = 64, h: int = 48, colour="teal") -> bytes:
    return encode(Image.new("RGB", (w, h), colour), "PNG")


def public_get(t: Tracker, image_id: str, **headers) -> httpx.Response:
    return httpx.get(f"{t.base_url}/api/images/{image_id}", headers=headers, timeout=30)


# ---------------------------------------------------------------------------
# I1 — uploads of every supported format
# ---------------------------------------------------------------------------


def test_i1_host_uploads_every_format(t):
    course = t.course()
    _, host = t.host(course)
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (43.0, 4.0, 30.0)}  # GPS
    files = {
        "a.png": (encode(Image.new("RGB", (64, 48), "teal"), "PNG"), "image/png"),
        "b.jpg": (
            encode(Image.new("RGB", (2400, 1200), "red"), "JPEG", exif=exif.tobytes()),
            "image/jpeg",
        ),
        "c.webp": (encode(Image.new("RGB", (30, 30), "blue"), "WEBP"), "image/webp"),
        "d.gif": (encode(Image.new("RGB", (16, 16), "green"), "GIF"), "image/png"),
    }
    for name, (data, content_type) in files.items():
        r = t.upload(course, data, name, host)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["content_type"] == content_type
        assert body["filename"] == name and body["deduplicated"] is False
        assert body["url"] == f"/api/images/{body['id']}" and body["used_by"] == []
        served = public_get(t, body["id"])
        assert served.status_code == 200
        assert served.headers["content-type"] == content_type
        im = decode(served.content)
        assert im.size == (body["width"], body["height"])
        assert body["byte_size"] == len(served.content)
        if name == "b.jpg":
            assert im.size == (1600, 800)
            assert len(im.getexif()) == 0, "EXIF (GPS) must be stripped"


# ---------------------------------------------------------------------------
# I2 — invalid uploads
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data, name, status",
    [
        (b"\x89PNG" + b"\x00" * (6 * MB), "huge.png", 413),
        (b"not an image at all", "fake.png", 415),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "x.svg", 415),
        (png(200, 200)[:300], "cut.png", 422),
    ],
    ids=["too-large", "text-as-png", "svg", "truncated"],
)
def test_i2_invalid_uploads_are_rejected(t, data, name, status):
    course = t.course()
    r = t.upload(course, data, name)
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) >= {"error", "message"}
    listed = t.admin("GET", f"/host/courses/{course}/images").json()
    assert listed == [], "nothing is stored"


# ---------------------------------------------------------------------------
# I3 — dedupe
# ---------------------------------------------------------------------------


def test_i3_same_file_twice_is_deduplicated(t):
    course = t.course()
    data = png(colour="purple")
    first = t.upload(course, data, "original.png")
    second = t.upload(course, data, "renamed.png")
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["deduplicated"] is True
    assert second.json()["filename"] == "original.png"
    assert len(t.admin("GET", f"/host/courses/{course}/images").json()) == 1


# ---------------------------------------------------------------------------
# I4 — access control
# ---------------------------------------------------------------------------


def test_i4_access_control(t):
    course, other = t.course(), t.course()
    _, host = t.host(course)
    _, other_host = t.host(other)
    image_id = t.upload(course, png(), "mine.png", host).json()["id"]

    game = t.game(course)
    t.question(game)
    guest = t.guest(t.room(game)).json()["access_token"]

    for token, status in ((other_host, 403), (guest, 403), (None, 401)):
        assert (
            t.call("GET", f"/host/courses/{course}/images", token).status_code == status
        )
        assert (
            t.call(
                "POST",
                f"/host/courses/{course}/images",
                token,
                files={"file": ("x.png", png(), "image/png")},
            ).status_code
            == status
        )
        assert (
            t.call(
                "PUT",
                f"/host/images/{image_id}",
                token,
                files={"file": ("x.png", png(), "image/png")},
            ).status_code
            == status
        )
        assert t.call("DELETE", f"/host/images/{image_id}", token).status_code == status

    assert t.admin("GET", f"/host/courses/{course}/images").status_code == 200
    assert public_get(t, image_id).status_code == 200, "serving needs no login"
    assert public_get(t, "0" * 32).status_code == 404
    assert public_get(t, "not-a-valid-id").status_code == 404
    assert t.admin("DELETE", f"/host/images/{'0' * 32}").status_code == 404


# ---------------------------------------------------------------------------
# I5 — serving headers and revalidation
# ---------------------------------------------------------------------------


def test_i5_serving_headers_and_304(t):
    course = t.course()
    body = t.upload(course, png(), "résumé photo.png").json()

    r = public_get(t, body["id"])
    etag = f'"{body["sha256"]}"'
    assert r.headers["etag"] == etag
    assert r.headers["cache-control"] == "public, no-cache"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"] == (
        'inline; filename="r_sum_ photo.png"; '
        "filename*=UTF-8''r%C3%A9sum%C3%A9%20photo.png"
    )

    for header in (etag, f"W/{etag}", f'"nope", {etag}', "*"):
        cached = public_get(t, body["id"], **{"If-None-Match": header})
        assert cached.status_code == 304, header
        assert cached.content == b"" and cached.headers["etag"] == etag
    assert public_get(t, body["id"], **{"If-None-Match": '"nope"'}).status_code == 200


# ---------------------------------------------------------------------------
# I14 — repeated upload / replace / delete
# ---------------------------------------------------------------------------


def test_i14_repeated_upload_replace_delete(t):
    course = t.course()
    for i in range(5):
        r = t.upload(course, png(20 + i, 20, "red"), f"round{i}.png")
        assert r.status_code == 201, r.text
        image_id = r.json()["id"]
        replaced = t.replace(image_id, png(40, 30 + i, "blue"), f"new{i}.png")
        assert replaced.status_code == 200, replaced.text
        assert replaced.json()["id"] == image_id
        assert (replaced.json()["width"], replaced.json()["height"]) == (40, 30 + i)
        assert replaced.json()["filename"] == f"new{i}.png"
        assert t.admin("DELETE", f"/host/images/{image_id}").status_code == 204
        assert public_get(t, image_id).status_code == 404
    assert t.admin("GET", f"/host/courses/{course}/images").json() == []


# ---------------------------------------------------------------------------
# I15 (size half) — import file limit
# ---------------------------------------------------------------------------


def test_i15_import_over_60_mb_is_413(t):
    course = t.course()
    r = t.admin(
        "POST",
        "/admin/games/import",
        files={"file": ("big.json", b" " * (60 * MB + 1), "application/json")},
        data={"course_id": str(course)},
    )
    assert r.status_code == 413, r.text


# ---------------------------------------------------------------------------
# Question references (step 3)
# ---------------------------------------------------------------------------

GRID = {"xMin": -5, "xMax": 5, "yMin": -5, "yMax": 5, "step": 1}


def questions_with_prompt_image(image_id: str) -> list[dict]:
    """One question of every type, each with a prompt image."""
    base = {
        "time_limit_seconds": 30,
        "points_value": 1,
        "prompt": "Look at the picture",
    }
    cfg = {"promptImageId": image_id}
    return [
        {
            **base,
            "type": "multiple_choice",
            "grading_type": "ACCURACY",
            "config": {**cfg, "options": ["a", "b"]},
            "answer_data": {"answer_points": [1, 0]},
        },
        {
            **base,
            "type": "true_false",
            "grading_type": "ACCURACY",
            "config": cfg,
            "answer_data": {"answer_points": {"true": 1, "false": 0}},
        },
        {
            **base,
            "type": "fill_in_the_blank",
            "grading_type": "COMPLETENESS",
            "config": cfg,
            "answer_data": {},
        },
        {
            **base,
            "type": "multi_select",
            "grading_type": "COMPLETENESS",
            "config": {**cfg, "options": ["a", "b"]},
            "answer_data": {},
        },
        {
            **base,
            "type": "pin_drop",
            "grading_type": "COMPLETENESS",
            "config": {**cfg, "grid": GRID},
            "answer_data": {},
        },
        {
            **base,
            "type": "estimate",
            "grading_type": "COMPLETENESS",
            "config": cfg,
            "answer_data": {},
        },
    ]


def mc_with_option_images(prompt_id: str | None, option_ids: list) -> dict:
    config = {"options": ["Cat", "Dog", "Fish"], "optionImages": option_ids}
    if prompt_id:
        config["promptImageId"] = prompt_id
    return {
        "type": "multiple_choice",
        "grading_type": "ACCURACY",
        "prompt": "Which is a cat?",
        "config": config,
        "answer_data": {"answer_points": [1, 0, 0]},
        "time_limit_seconds": 30,
        "points_value": 1,
    }


def image_pin(image_id: str, **image_extra) -> dict:
    return {
        "type": "pin_drop",
        "grading_type": "ACCURACY",
        "prompt": "Where is the lake?",
        "config": {"image": {"imageId": image_id, **image_extra}},
        "answer_data": {
            "target": {"x": 0.25, "y": 0.5},
            "fullRadius": 0.05,
            "zeroRadius": 0.2,
        },
        "time_limit_seconds": 30,
        "points_value": 1,
    }


def add(
    t: Tracker, game_id: int, question: dict, token: str | None = None, prefix="/admin"
):
    return t.call(
        "POST",
        f"{prefix}/games/{game_id}/questions",
        token or t.admin_token,
        json=question,
    )


def import_v1(t: Tracker, course: int, questions: list[dict]):
    bundle = {
        "format": "buzzer/game",
        "version": 1,
        "game": {"title": "img import", "description": "", "max_players": 50},
        "questions": questions,
    }
    r = t.admin(
        "POST",
        "/admin/games/import",
        files={"file": ("g.json", json.dumps(bundle), "application/json")},
        data={"course_id": str(course)},
    )
    if r.status_code == 201:
        t.game_ids.append(r.json()["game_id"])
    return r


def test_i6_references_on_create_update_and_import(t):
    course, other = t.course(), t.course()
    _, host = t.host(course)
    mine = t.upload(course, png(colour="red"), "mine.png").json()["id"]
    theirs = t.upload(other, png(colour="blue"), "theirs.png").json()["id"]
    game = t.game(course, token=host, prefix="/host")

    for q in questions_with_prompt_image(mine):
        r = add(t, game, q, host, "/host")
        assert r.status_code == 201, r.text
        assert r.json()["config"]["promptImageId"] == mine

    bad = {
        "length-mismatch": mc_with_option_images(None, [mine]),
        "other-course": mc_with_option_images(theirs, [None, None, None]),
        "nonexistent": mc_with_option_images("f" * 32, [None, None, None]),
    }
    target = add(
        t, game, mc_with_option_images(None, [mine, None, None]), host, "/host"
    ).json()
    for name, q in bad.items():
        created = add(t, game, q, host, "/host")
        updated = t.call(
            "PUT",
            f"/host/games/{game}/questions/{target['id']}",
            host,
            json={"config": q["config"]},
        )
        imported = import_v1(t, course, [q])
        assert (created.status_code, updated.status_code, imported.status_code) == (
            422,
            422,
            422,
        ), (name, created.text, updated.text, imported.text)

    ok = import_v1(t, course, [mc_with_option_images(mine, [mine, None, None])])
    assert ok.status_code == 201, ok.text

    # Removing a reference: send config without the key (config is replaced wholesale).
    r = t.call(
        "PUT",
        f"/host/games/{game}/questions/{target['id']}",
        host,
        json={"config": {"options": ["Cat", "Dog", "Fish"]}},
    )
    assert r.status_code == 200 and "optionImages" not in r.json()["config"]


def test_i7_pin_drop_image_dimensions_come_from_the_image(t):
    course = t.course()
    image = t.upload(course, png(300, 150), "map.png").json()
    game = t.game(course)
    for extra in ({}, {"width": 9, "height": 9}):
        r = add(t, game, image_pin(image["id"], **extra))
        assert r.status_code == 201, r.text
        assert r.json()["config"]["image"] == {
            "imageId": image["id"],
            "width": 300,
            "height": 150,
        }


def test_i8_replace_keeps_id_refreshes_dims_and_respects_live_rooms(t):
    course = t.course()
    _, host = t.host(course)
    image = t.upload(course, png(300, 150), "map.png").json()
    game = t.game(course, token=host, prefix="/host")
    q = add(t, game, image_pin(image["id"]), host, "/host").json()
    old_etag = '"' + image["sha256"] + '"'

    r = t.replace(image["id"], png(200, 200), "map2.png", host)
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["id"] == image["id"] and new["sha256"] != image["sha256"]
    assert public_get(t, image["id"], **{"If-None-Match": old_etag}).status_code == 200
    new_etag = '"' + new["sha256"] + '"'
    assert public_get(t, image["id"], **{"If-None-Match": new_etag}).status_code == 304
    stored = t.call("GET", f"/host/games/{game}/questions", host).json()
    assert next(x for x in stored if x["id"] == q["id"])["config"]["image"] == {
        "imageId": image["id"],
        "width": 200,
        "height": 200,
    }

    title = t.call("GET", f"/host/games/{game}", host).json()["title"]
    t.room(game)  # a LOBBY room counts as live
    for token in (host, t.admin_token):
        blocked = t.replace(image["id"], png(100, 100), "map3.png", token)
        assert blocked.status_code == 409, blocked.text
        assert title in blocked.json()["message"]
        assert [u["question_id"] for u in blocked.json()["used_by"]] == [q["id"]]


def test_i9_delete_blocked_while_in_use(t):
    course = t.course()
    image = t.upload(course, png(), "cat.png").json()["id"]
    game = t.game(course)
    title = t.admin("GET", f"/admin/games/{game}").json()["title"]
    t.question(game)  # Q1 without images
    q = add(t, game, mc_with_option_images(image, [image, image, None])).json()

    r = t.admin("DELETE", f"/host/images/{image}")
    assert r.status_code == 409, r.text
    used_by = r.json()["used_by"]
    assert sorted(u["field"] for u in used_by) == ["option", "prompt"]
    assert {
        (u["game_title"], u["question_number"], u["question_id"]) for u in used_by
    } == {(title, 2, q["id"])}
    listed = t.admin("GET", f"/host/courses/{course}/images").json()
    assert len({u["question_id"] for u in listed[0]["used_by"]}) == 1

    r = t.admin(
        "PUT",
        f"/admin/games/{game}/questions/{q['id']}",
        json={"config": {"options": ["Cat", "Dog", "Fish"]}},
    )
    assert r.status_code == 200, r.text
    assert t.admin("DELETE", f"/host/images/{image}").status_code == 204
    assert public_get(t, image).status_code == 404

    # In use by a game with a live room: still 409 for an admin.
    live_image = t.upload(course, png(colour="pink"), "live.png").json()["id"]
    add(t, game, mc_with_option_images(live_image, [None, None, None]))
    t.room(game)
    assert t.admin("DELETE", f"/host/images/{live_image}").status_code == 409


def test_i13_images_outlive_games_and_uploaders(t):
    course = t.course()
    uploader_id, uploader = t.host(course)
    image = t.upload(course, png(), "kept.png", uploader).json()["id"]
    game = t.game(course)
    add(t, game, mc_with_option_images(image, [None, None, None]))

    assert t.admin("DELETE", f"/admin/games/{game}").status_code == 204
    t.game_ids.remove(game)
    assert t.admin("DELETE", f"/admin/users/{uploader_id}").status_code == 204
    t.user_ids.remove(uploader_id)
    assert public_get(t, image).status_code == 200
    assert [
        i["id"] for i in t.admin("GET", f"/host/courses/{course}/images").json()
    ] == [image]


def test_i16_type_change_rechecks_stored_references(t):
    course = t.course()
    image = t.upload(course, png(), "opt.png").json()["id"]
    game = t.game(course)
    q = add(t, game, mc_with_option_images(None, [image, None, None])).json()

    r = t.admin(
        "PUT",
        f"/admin/games/{game}/questions/{q['id']}",
        json={
            "type": "true_false",
            "answer_data": {"answer_points": {"true": 1, "false": 0}},
        },
    )
    assert r.status_code == 422, r.text
    stored = t.admin("GET", f"/admin/games/{game}/questions").json()[0]
    assert stored["type"] == "multiple_choice"

    # A compatible type change without config keeps the stored config, images included.
    r = t.admin(
        "PUT", f"/admin/games/{game}/questions/{q['id']}", json={"type": "multi_select"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["type"] == "multi_select"
    assert r.json()["config"] == q["config"]


def test_i17_dedupe_goes_to_the_oldest_image(t):
    course = t.course()
    a_bytes = png(colour="olive")
    a = t.upload(course, a_bytes, "a.png").json()["id"]
    b = t.upload(course, png(colour="navy"), "b.png").json()["id"]
    assert t.replace(b, a_bytes, "b-now-a.png").status_code == 200
    again = t.upload(course, a_bytes, "again.png")
    assert again.status_code == 200 and again.json()["id"] == a
    assert again.json()["deduplicated"] is True


# ---------------------------------------------------------------------------
# Export / import version 2 (step 4)
# ---------------------------------------------------------------------------

SAMPLE_GAMES = pathlib.Path(__file__).resolve().parents[2] / "sample_games"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def v2_bundle(questions: list[dict], images, version: int = 2) -> dict:
    return {
        "format": "buzzer/game",
        "version": version,
        "game": {"title": "v2 import", "description": "", "max_players": 50},
        "questions": questions,
        "images": images,
    }


def prompt_question(ref) -> dict:
    """A plain multiple-choice question whose prompt image is `ref`."""
    q = mc_with_option_images(None, [None, None, None])
    q["config"] = {"options": q["config"]["options"], "promptImageId": ref}
    return q


def import_file(t: Tracker, course: int, bundle) -> httpx.Response:
    r = t.admin(
        "POST",
        "/host/games/import",
        files={"file": ("g.json", json.dumps(bundle), "application/json")},
        data={"course_id": str(course)},
    )
    if r.status_code == 201:
        t.game_ids.append(r.json()["game_id"])
    return r


def course_contents(t: Tracker, course: int) -> tuple[list, list]:
    """(game ids, image ids) in a course — both empty after a refused import."""
    games = [
        g["id"]
        for g in t.admin("GET", "/admin/games").json()
        if g["course_id"] == course
    ]
    images = [i["id"] for i in t.admin("GET", f"/host/courses/{course}/images").json()]
    return games, images


def test_i10_export_v2_and_import_into_another_course(t):
    src, dst = t.course(), t.course()
    prompt = t.upload(src, png(colour="red"), "prompt.png").json()
    option = t.upload(src, png(colour="blue"), "option.png").json()
    pin = t.upload(src, png(300, 150, "green"), "map.png").json()
    game = t.game(src)
    add(
        t, game, mc_with_option_images(prompt["id"], [option["id"], None, option["id"]])
    )
    add(t, game, image_pin(pin["id"]))
    t.question(game)  # no images

    r = t.admin("GET", f"/host/games/{game}/export")
    assert r.status_code == 200, r.text
    bundle = r.json()
    assert bundle["version"] == 2
    refs = [e["ref"] for e in bundle["images"]]
    assert refs == [
        prompt["id"],
        option["id"],
        pin["id"],
    ]  # first use first, no repeats
    for entry in bundle["images"]:
        assert base64.b64decode(entry["data"]) == public_get(t, entry["ref"]).content
    assert bundle["images"][2]["filename"] == "map.png"

    r = import_file(t, dst, bundle)
    assert r.status_code == 201, r.text
    questions = t.admin("GET", f"/admin/games/{r.json()['game_id']}/questions").json()
    mc, pin_q = questions[0]["config"], questions[1]["config"]
    new = {
        prompt["id"]: mc["promptImageId"],
        option["id"]: mc["optionImages"][0],
        pin["id"]: pin_q["image"]["imageId"],
    }
    assert mc["optionImages"] == [new[option["id"]], None, new[option["id"]]]
    assert pin_q["image"] == {"imageId": new[pin["id"]], "width": 300, "height": 150}
    assert not set(new) & set(new.values()), "imported images get new ids"
    assert sorted(course_contents(t, dst)[1]) == sorted(new.values())
    for old_id, new_id in new.items():  # PNG re-encodes to the same bytes
        assert public_get(t, new_id).content == public_get(t, old_id).content


def test_i10_games_without_images_still_export_version_1(t):
    course = t.course()
    game = t.game(course)
    t.question(game)
    bundle = t.admin("GET", f"/host/games/{game}/export").json()
    assert bundle["version"] == 1 and "images" not in bundle

    starter = json.loads(
        (SAMPLE_GAMES / "cs_first_day.json").read_text(encoding="utf-8")
    )
    assert starter["version"] == 1
    r = import_file(t, course, starter)
    assert r.status_code == 201, r.text


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'


@pytest.mark.parametrize(
    "questions, images, named",
    [
        ([prompt_question("a")], [{"ref": "a", "data": "!!not base64!!"}], "'a'"),
        ([prompt_question("b")], [{"ref": "a", "data": b64(png())}], "'b'"),
        (
            [prompt_question("a")],
            [{"ref": "a", "data": b64(png())}, {"ref": "a", "data": b64(png())}],
            "'a'",
        ),
        ([prompt_question("a")], [{"ref": "a", "data": b64(SVG)}], "'a'"),
        (
            [prompt_question("a")],
            [{"ref": "a", "data": b64(png() + b"\0" * (5 * MB))}],
            "'a'",
        ),
        ([prompt_question(5)], [{"ref": "a", "data": b64(png())}], "Question 1"),
        (
            [{**image_pin("a"), "config": {"image": {"imageId": 5}}}],
            [{"ref": "a", "data": b64(png())}],
            "Question 1: invalid image reference",
        ),
    ],
    ids=[
        "corrupt-base64",
        "missing-ref",
        "duplicate-ref",
        "svg",
        "over-5-mb",
        "mistyped",
        "mistyped-pin",
    ],
)
def test_i10_bad_version_2_files_create_nothing(t, questions, images, named):
    course = t.course()
    # A valid first question and image, so a failure later proves nothing was kept.
    files_ok = {"ref": "ok", "data": b64(png(colour="gold"))}
    r = import_file(
        t, course, v2_bundle([prompt_question("ok"), *questions], [files_ok, *images])
    )
    assert r.status_code == 422, r.text
    assert named.replace("Question 1", "Question 2") in r.text
    assert course_contents(t, course) == ([], [])


def test_i10_unused_entries_are_not_stored(t):
    course = t.course()
    bundle = v2_bundle(
        [prompt_question("used")],
        [
            {"ref": "used", "data": b64(png(colour="lime"))},
            {"ref": "spare", "data": b64(png(colour="plum"))},
        ],
    )
    r = import_file(t, course, bundle)
    assert r.status_code == 201, r.text
    assert len(course_contents(t, course)[1]) == 1


def test_i15_format_limits(t):
    course = t.course()
    entry = {"ref": "a", "data": b64(png())}
    r = import_file(t, course, v2_bundle([], [entry], version=1))
    assert r.status_code == 422 and "version 2" in r.text, r.text
    many = [{"ref": f"r{i}", "data": "AAAA"} for i in range(101)]
    r = import_file(t, course, v2_bundle([], many))
    assert r.status_code == 422 and "100" in r.text, r.text
    assert course_contents(t, course) == ([], [])


@pytest.mark.parametrize(
    "images, named",
    [
        ({"ref": "a", "data": "AAAA"}, "images must be a list"),
        (["a"], "images[0]"),
        ([{"ref": "a"}], "images[0]"),
        ([{"ref": "a", "data": "AAAA", "filename": 7}], "images[0]"),
    ],
    ids=["object", "string-entry", "no-data", "numeric-filename"],
)
def test_i18_image_entries_of_the_wrong_shape(t, images, named):
    course = t.course()
    r = import_file(t, course, v2_bundle([prompt_question("a")], images))
    assert r.status_code == 422 and named in r.text, r.text
    assert course_contents(t, course) == ([], [])


def test_i18_content_type_is_ignored(t):
    course = t.course()
    jpeg = encode(Image.new("RGB", (40, 30), "orange"), "JPEG")
    entry = {
        "ref": "a",
        "data": b64(jpeg),
        "contentType": "image/png",
        "filename": "x.png",
    }
    r = import_file(t, course, v2_bundle([prompt_question("a")], [entry]))
    assert r.status_code == 201, r.text
    [image] = t.admin("GET", f"/host/courses/{course}/images").json()
    assert image["content_type"] == "image/jpeg"


# ---------------------------------------------------------------------------
# Live games and the report (step 5)
# ---------------------------------------------------------------------------


class ImageGame(LiveGame):
    """LiveGame on questions that reference images already in `course`."""

    def __init__(self, t: Tracker, base_url: str, course: int, questions, players: int):
        self.t, self.base_url = t, base_url
        self.game_id = t.game(course)
        for q in questions:
            r = add(t, self.game_id, q)
            assert r.status_code == 201, r.text
        self.room = t.room(self.game_id)
        self.session_id = t.session_id(self.room)
        self.host = TestSocketClient(base_url, t.admin_token, "host")
        self.players = [
            TestSocketClient(base_url, self.guest_token(), f"p{i}")
            for i in range(players)
        ]
        self.syncs: list[dict] = []

    async def __aenter__(self) -> ImageGame:
        self.syncs.append(await self.join(self.host, "HOST"))
        for p in self.players:
            self.syncs.append(await self.join(p, "PLAYER"))
        return self


def image_game_questions(t: Tracker, course: int) -> tuple[dict, list[dict]]:
    """Q1: MC with a prompt and option images; Q2: pin_drop on a 2:1 map + prompt."""
    ids = {
        "prompt": t.upload(course, png(colour="red"), "prompt.png").json()["id"],
        "option": t.upload(course, png(colour="blue"), "option.png").json()["id"],
        "map": t.upload(course, png(200, 100, "green"), "map.png").json()["id"],
        "prompt2": t.upload(course, png(colour="purple"), "p2.png").json()["id"],
    }
    pin = image_pin(ids["map"])
    pin["config"]["promptImageId"] = ids["prompt2"]
    return ids, [
        mc_with_option_images(ids["prompt"], [ids["option"], None, ids["option"]]),
        pin,
    ]


async def test_i11_i12_live_image_game_and_report(t, base_url):
    course = t.course()
    ids, questions = image_game_questions(t, course)
    async with ImageGame(t, base_url, course, questions, players=1) as game:
        host_q, [player_q] = await game.next_question()
        for payload in (host_q, player_q):
            assert payload["config"]["promptImageId"] == ids["prompt"]
            assert payload["config"]["optionImages"] == [
                ids["option"],
                None,
                ids["option"],
            ]
            _no_answer_in(payload)
        await game.answer(0, player_q["questionId"], {"selectedIndex": 0})
        await game.results()

        host_q, [player_q] = await game.next_question()
        assert player_q["config"]["image"] == {
            "imageId": ids["map"],
            "width": 200,
            "height": 100,
        }
        assert player_q["config"]["snap"] is False
        _no_answer_in(player_q)
        bad, _ = await game.answer(
            0, player_q["questionId"], {"point": {"x": 1.5, "y": 0}}
        )
        assert bad == "error", "image answers are fractions of the picture"
        # 0.1 down on a 2:1 image is 0.05 widths: inside fullRadius 0.05 → full points.
        event, _ = await game.answer(
            0, player_q["questionId"], {"point": {"x": 0.25, "y": 0.6}}
        )
        assert event == "answer_received"
        host_r, [player_r] = await game.results()
        assert player_r["yourPoints"] == pytest.approx(1)
        assert host_r["answerValues"] == [{"x": 0.25, "y": 0.6}]
        await game.finish()

    html = t.admin("GET", f"/host/sessions/{game.session_id}/report").text
    assert html.count('<img class="q-image" src="data:image/') == 2  # both prompts
    assert html.count('<img class="opt-thumb" src="data:image/') == 2  # options A and C
    assert '<image href="data:image/' in html  # the pin plot's map
    assert "[image unavailable]" not in html
    assert "1 within full credit" in html and "target 25% across, 50% down" in html
    # Still PII-free: guests are "Guest <tag>" with an @example.com email.
    assert "Guest " not in html and "@example.com" not in html


async def test_i19_prefetch_hints(t, base_url):
    course = t.course()
    ids, questions = image_game_questions(t, course)
    async with ImageGame(t, base_url, course, questions, players=1) as game:
        host_sync, player_sync = game.syncs
        assert host_sync["prefetchImageIds"] == [ids["prompt"], ids["option"]]
        assert player_sync["prefetchImageIds"] == [ids["option"]]  # no prompt image

        await game.next_question()
        host_r, [player_r] = await game.results()
        assert host_r["prefetchImageIds"] == [ids["prompt2"], ids["map"]]
        assert player_r["prefetchImageIds"] == [ids["map"]]
        for payload in (host_r, player_r):
            assert "answer_data" not in json.dumps(payload)

        await game.next_question()
        host_r, [player_r] = await game.results()
        assert host_r["prefetchImageIds"] == [] and player_r["prefetchImageIds"] == []
        await game.finish()
