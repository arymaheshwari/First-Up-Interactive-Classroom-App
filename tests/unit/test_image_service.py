"""
Unit tests for the T8 upload pipeline (backend/app/services/image_service.py).

Scenario ids (U9, U9b, U10, U12, U14) match docs/plans/t8-image-support.md §8.1.
Every image is generated in memory; no Docker needed.

Run with:
    cd tests/unit && PYTHONPATH=../../backend pytest test_image_service.py -v
"""

from __future__ import annotations

import io
import struct
import zlib

import pytest
from PIL import Image

from app.common.exceptions import (
    PayloadTooLargeError,
    UnprocessableError,
    UnsupportedMediaError,
)
from app.services import image_service as svc


def encode(im: Image.Image, fmt: str, **kw) -> bytes:
    buf = io.BytesIO()
    im.save(buf, fmt, **kw)
    return buf.getvalue()


def decode(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def oriented(fmt: str, orientation: int = 6) -> bytes:
    """A 40×20 image, left half red and right half blue, tagged with an orientation."""
    im = Image.new("RGB", (40, 20), "red")
    im.paste((0, 0, 255), (20, 0, 40, 20))
    exif = Image.Exif()
    exif[0x0112] = orientation
    return encode(im, fmt, exif=exif.tobytes())


# ---------------------------------------------------------------------------
# U9 — formats, modes, sizes
# ---------------------------------------------------------------------------


def test_png_rgb_stays_png_rgb():
    out = svc.process_upload(encode(Image.new("RGB", (64, 48), "teal"), "PNG"), "a.png")
    assert (out.content_type, decode(out.data).mode) == ("image/png", "RGB")
    assert (out.width, out.height) == (64, 48)


def test_rgba_with_a_transparent_pixel_keeps_alpha():
    im = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
    im.putpixel((3, 3), (255, 0, 0, 128))
    out = svc.process_upload(encode(im, "PNG"), "a.png")
    assert decode(out.data).mode == "RGBA"


def test_fully_opaque_rgba_drops_alpha():
    out = svc.process_upload(
        encode(Image.new("RGBA", (10, 10), (1, 2, 3, 255)), "PNG"), "a.png"
    )
    assert decode(out.data).mode == "RGB"


def test_palette_with_trns_becomes_rgba():
    im = Image.new("P", (10, 10), 0)
    im.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
    im.paste(1, (0, 0, 5, 10))
    out = svc.process_upload(encode(im, "PNG", transparency=0), "a.png")
    result = decode(out.data)
    assert result.mode == "RGBA"
    assert result.getpixel((8, 5))[3] == 0 and result.getpixel((1, 5))[3] == 255


def test_rgb_colour_key_trns_becomes_rgba():
    im = Image.new("RGB", (10, 10), (0, 255, 0))
    im.paste((9, 9, 9), (0, 0, 5, 10))
    out = svc.process_upload(encode(im, "PNG", transparency=(9, 9, 9)), "a.png")
    result = decode(out.data)
    assert result.mode == "RGBA" and result.getpixel((1, 1))[3] == 0


def test_sixteen_bit_greyscale_is_scaled_not_clipped():
    im = Image.new("I;16", (256, 4))
    for x in range(256):
        for y in range(4):
            im.putpixel((x, y), x * 256)
    out = svc.process_upload(encode(im, "PNG"), "g.png")
    result = decode(out.data).convert("L")
    assert result.getpixel((0, 0)) == 0
    assert result.getpixel((128, 0)) == 128  # a clip would make this 255
    assert result.getpixel((255, 0)) == 255


def test_cmyk_jpeg_becomes_rgb_jpeg():
    out = svc.process_upload(
        encode(Image.new("CMYK", (32, 32), (0, 255, 255, 0)), "JPEG"), "c.jpg"
    )
    assert (out.content_type, decode(out.data).mode) == ("image/jpeg", "RGB")


def test_jpeg_exif_gps_stripped_and_orientation_applied():
    im = Image.new("RGB", (40, 20), "red")
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x8825] = {1: "N", 2: (43.0, 4.0, 30.0)}  # GPSInfo
    out = svc.process_upload(encode(im, "JPEG", exif=exif.tobytes()), "p.jpg")
    result = decode(out.data)
    assert result.size == (20, 40), "orientation 6 rotates 90°"
    assert len(result.getexif()) == 0 and "exif" not in result.info


def test_large_jpeg_is_downscaled_and_small_one_is_not_upscaled():
    big = svc.process_upload(
        encode(Image.new("RGB", (3000, 2000), "red"), "JPEG"), "b.jpg"
    )
    small = svc.process_upload(
        encode(Image.new("RGB", (800, 600), "red"), "JPEG"), "s.jpg"
    )
    assert (big.width, big.height) == (1600, 1067)
    assert (small.width, small.height) == (800, 600)


def test_animated_gif_keeps_first_frame_as_png():
    frames = [Image.new("RGB", (16, 16), c) for c in ("red", "blue", "green")]
    raw = encode(frames[0], "GIF", save_all=True, append_images=frames[1:], loop=0)
    out = svc.process_upload(raw, "anim.gif")
    result = decode(out.data)
    assert out.content_type == "image/png"
    assert getattr(result, "n_frames", 1) == 1
    assert result.convert("RGB").getpixel((5, 5)) == (255, 0, 0)


def test_webp_stays_webp():
    out = svc.process_upload(
        encode(Image.new("RGB", (30, 30), "blue"), "WEBP"), "w.webp"
    )
    assert out.content_type == "image/webp"


@pytest.mark.parametrize(
    "raw, error",
    [
        (b"just some text, not an image", UnsupportedMediaError),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            UnsupportedMediaError,
        ),
        (encode(Image.new("RGB", (8, 8)), "BMP"), UnsupportedMediaError),
    ],
    ids=["text", "svg", "bmp"],
)
def test_unsupported_types_are_415(raw, error):
    with pytest.raises(error):
        svc.process_upload(raw, "x.png")


def test_truncated_png_is_422():
    raw = encode(Image.new("RGB", (200, 200), "red"), "PNG")
    with pytest.raises(UnprocessableError):
        svc.process_upload(raw[: len(raw) // 2], "t.png")


def _png_header_only(width: int, height: int) -> bytes:
    """A PNG whose IHDR claims width×height (no real pixel data needed for the guard)."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = lambda t, d: (  # noqa: E731
        struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    )
    idat = zlib.compress(b"\x00" * 16)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def test_bomb_between_one_and_two_times_pillow_limit_is_rejected():
    # 7000×7000 = 49 MP: Pillow alone would only warn (limit 50 MP); our PNG cap is 25 MP.
    with pytest.raises(UnprocessableError, match="too large"):
        svc.process_upload(_png_header_only(7000, 7000), "bomb.png")


def test_over_five_megabytes_is_413():
    with pytest.raises(PayloadTooLargeError):
        svc.process_upload(b"\x00" * (svc.MAX_UPLOAD_BYTES + 1), "big.png")


# ---------------------------------------------------------------------------
# U9b — orientation on every format, side limit, per-format pixel caps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_orientation_applied_for_every_format(fmt):
    result = decode(svc.process_upload(oriented(fmt), f"o.{fmt.lower()}").data).convert(
        "RGB"
    )
    assert result.size == (20, 40)
    # Orientation 6 means "rotate 90° clockwise to view": the left (red) half ends on top.
    top, bottom = result.getpixel((10, 5)), result.getpixel((10, 35))
    assert top[0] > 200 and top[2] < 60, top
    assert bottom[2] > 200 and bottom[0] < 60, bottom


def test_side_over_12000_is_rejected_even_under_the_pixel_cap():
    with pytest.raises(UnprocessableError, match="12000 px"):
        svc.process_upload(_png_header_only(12_500, 1_000), "wide.png")


def test_png_over_25_megapixels_is_rejected():
    with pytest.raises(UnprocessableError, match="25 megapixels"):
        svc.process_upload(_png_header_only(6000, 5000), "30mp.png")


def test_jpeg_up_to_50_megapixels_is_accepted():
    raw = encode(Image.new("RGB", (8200, 5500), "orange"), "JPEG", quality=30)
    assert len(raw) <= svc.MAX_UPLOAD_BYTES, "test image must fit the upload cap"
    out = svc.process_upload(raw, "45mp.jpg")
    assert max(out.width, out.height) == 1600


# ---------------------------------------------------------------------------
# U10 — deterministic re-encode (dedupe relies on it)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_same_input_gives_same_bytes(fmt):
    raw = encode(Image.new("RGB", (120, 90), (12, 34, 56)), fmt)
    first, second = svc.process_upload(raw, "a"), svc.process_upload(raw, "b")
    assert first.data == second.data and first.sha256 == second.sha256


# ---------------------------------------------------------------------------
# U12 — If-None-Match matching
# ---------------------------------------------------------------------------

H = "ab" * 32


@pytest.mark.parametrize(
    "header, match",
    [
        (f'"{H}"', True),
        (f'W/"{H}"', True),
        (f'"x", "{H}"', True),
        ("*", True),
        ('"other"', False),
        (None, False),
        (H, False),  # unquoted is not a valid entity tag
    ],
)
def test_etag_matching(header, match):
    assert svc.etag_matches(header, H) is match


# ---------------------------------------------------------------------------
# U14 — filename sanitising and Content-Disposition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, clean",
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\photo.png", "photo.png"),
        ("photo\u0000.png", "photo.png"),
        ('résumé "final".png', "résumé final.png"),
        ("", "image"),
        (None, "image"),
        ("x" * 300, "x" * 255),
    ],
)
def test_sanitize_filename(raw, clean):
    assert svc.sanitize_filename(raw) == clean


def test_content_disposition_has_ascii_fallback_and_utf8_name():
    header = svc.content_disposition("résumé final.png")
    assert header.startswith('inline; filename="r_sum_ final.png"; ')
    assert header.endswith("filename*=UTF-8''r%C3%A9sum%C3%A9%20final.png")


# ---------------------------------------------------------------------------
# U13 — per-course quota (unit-only by design: the live stack's quota can't be
# lowered, and filling 200 MB per run would be slow)
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def refresh(self, obj, attrs=None):
        pass


def _processed(size: int, sha: str = "a" * 64) -> svc.ProcessedImage:
    return svc.ProcessedImage(b"x" * size, "image/png", 10, 10, sha, "q.png")


@pytest.fixture
def quota(monkeypatch):
    """Stub the DB work create/replace do; returns a setter for 'used'."""
    state = {"used": 0, "duplicate": None}

    async def used(db, course_id):
        return state["used"]

    async def duplicate(db, course_id, sha256):
        return state["duplicate"]

    async def no_questions(db, image):
        pass

    monkeypatch.setattr(svc, "course_bytes_used", used)
    monkeypatch.setattr(svc, "find_duplicate", duplicate)
    monkeypatch.setattr(svc, "_refresh_pin_drop_sizes", no_questions)
    return state


async def test_u13_upload_just_under_quota_is_stored(quota):
    quota["used"] = svc.COURSE_QUOTA_BYTES - 100
    db = _FakeSession()
    image, created = await svc.create_image(db, 1, None, _processed(100))
    assert created and db.added == [image]


async def test_u13_upload_over_quota_is_409(quota):
    from app.common.exceptions import ConflictError

    quota["used"] = svc.COURSE_QUOTA_BYTES - 99
    with pytest.raises(ConflictError, match="library is full"):
        await svc.create_image(_FakeSession(), 1, None, _processed(100))


async def test_u13_dedupe_hit_in_a_full_course_returns_existing(quota):
    existing = object()
    quota["used"] = svc.COURSE_QUOTA_BYTES
    quota["duplicate"] = existing
    image, created = await svc.create_image(_FakeSession(), 1, None, _processed(100))
    assert image is existing and created is False


async def test_u13_replace_counts_used_minus_old_plus_new(quota):
    from types import SimpleNamespace

    from app.common.exceptions import ConflictError

    image = SimpleNamespace(course_id=1, byte_size=500)
    quota["used"] = svc.COURSE_QUOTA_BYTES  # full, including this image's 500 bytes
    shrunk = await svc.replace_image(_FakeSession(), image, _processed(400))
    assert shrunk.byte_size == 400, "a shrinking replace always passes"
    with pytest.raises(ConflictError):
        await svc.replace_image(_FakeSession(), image, _processed(600))


# ---------------------------------------------------------------------------
# U15 — the export size cap is checked before any image bytes load (D7)
# ---------------------------------------------------------------------------


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _ExportSession:
    """Answers list_questions, then the size query, then records any blob load."""

    def __init__(self, image_bytes: int):
        from types import SimpleNamespace

        image_id = "0123456789abcdef0123456789abcdef"
        question = SimpleNamespace(
            type="true_false",
            grading_type="COMPLETENESS",
            prompt="p",
            config={"promptImageId": image_id},
            answer_data={},
            time_limit_seconds=30,
            points_value=1,
        )
        self.results = [
            _Rows([question]),
            _Rows([SimpleNamespace(id=image_id, byte_size=image_bytes)]),
            _Rows([]),
        ]
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self.results[self.calls - 1]


@pytest.mark.parametrize(
    "image_mb, refused",
    [(44, False), (45, True)],  # 44 → ≈59.7 MB with overhead; 45 → 61 MB
)
async def test_u15_export_refuses_oversized_files_before_loading(image_mb, refused):
    from types import SimpleNamespace

    from app.common.exceptions import ConflictError
    from app.services import content_service

    db = _ExportSession(image_mb * 1024 * 1024)
    game = SimpleNamespace(id=1, title="g", description="", max_players=10, course_id=1)
    if refused:
        with pytest.raises(ConflictError, match="60 MB"):
            await content_service.export_game(db, game)
        assert db.calls == 2, "the blobs must not load"
    else:
        await content_service.export_game(db, game)
        assert db.calls == 3


# ---------------------------------------------------------------------------
# U16 — report thumbnails (D8)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode, size, media_type, width",
    [
        ("RGB", (1600, 800), "image/jpeg", 480),
        ("RGBA", (1000, 500), "image/png", 480),
        ("L", (300, 200), "image/jpeg", 300),  # never upscaled
    ],
)
def test_u16_thumbnail_data_uri(mode, size, media_type, width):
    import base64

    stored = svc.process_upload(encode(Image.new(mode, size, 128), "PNG"), "x.png")
    if mode == "RGBA":
        im = Image.new("RGBA", size, (10, 20, 30, 255))
        im.putpixel((0, 0), (0, 0, 0, 0))
        stored = svc.process_upload(encode(im, "PNG"), "x.png")
    uri = svc.thumbnail_data_uri(stored.data, stored.content_type)
    prefix = f"data:{media_type};base64,"
    assert uri.startswith(prefix)
    thumb = Image.open(io.BytesIO(base64.b64decode(uri[len(prefix) :])))
    assert thumb.width == width
    assert thumb.height == round(size[1] * width / size[0])
