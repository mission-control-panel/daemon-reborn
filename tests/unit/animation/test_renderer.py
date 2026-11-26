"""QImage snapshot and layout tests for the ORC-188 sprite renderer."""

from __future__ import annotations

import os
import struct
import zlib
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from daemon_reborn.animation.director import MouthOverlay
from daemon_reborn.animation.player import SpriteClip, SpriteFrame, SpritePlayer
from daemon_reborn.animation.renderer import SpriteRenderer
from daemon_reborn.assets.canonical import (
    CanonicalAnchor,
    CanonicalAssetPack,
    CanonicalClip,
    CanonicalFrame,
    CanonicalMouthOverlay,
    load_packaged_idle_assets,
)


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app
    app.quit()


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _make_png_bytes(width: int, height: int, draw_fn: Callable[[QImage], None]) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(0)
    draw_fn(image)
    raw_rows = bytearray()
    for y in range(height):
        raw_rows.append(0)
        for x in range(width):
            color = image.pixelColor(x, y)
            r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
            raw_rows.extend((r, g, b, a))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw_rows)))
        + _png_chunk(b"IEND", b"")
    )


def _make_pack() -> CanonicalAssetPack:
    # 4 frames of 4x4 side-by-side (16x4):
    # frame 0: solid red block at (1,1)-(2,2) on transparent background (idle[0])
    # frame 1: solid blue block at (1,1)-(2,2) (idle[1])
    # frame 2: green mouth pixel at (1,2) with transparent surrounding pixels
    # frame 3: yellow mouth pixel at (2,2)
    def paint(img: QImage) -> None:
        # frame 0: (0..3, 0..3)
        for y in (1, 2):
            for x in (1, 2):
                img.setPixelColor(x, y, QColor(255, 0, 0, 255))
        # frame 1: (4..7, 0..3)
        for y in (1, 2):
            for x in (5, 6):
                img.setPixelColor(x, y, QColor(0, 0, 255, 255))
        # frame 2: mouth "open" at x=8..11
        img.setPixelColor(9, 2, QColor(0, 255, 0, 255))
        # frame 3: mouth "closed" at x=12..15
        img.setPixelColor(14, 2, QColor(255, 255, 0, 255))

    atlas_bytes = _make_png_bytes(16, 4, paint)
    return CanonicalAssetPack(
        schema_version=1,
        canvas=(4, 4),
        fps=8,
        frames=(
            CanonicalFrame(id=0, duration_ms=125, x=0, y=0, width=4, height=4),
            CanonicalFrame(id=1, duration_ms=125, x=4, y=0, width=4, height=4),
            CanonicalFrame(id=2, duration_ms=125, x=8, y=0, width=4, height=4),
            CanonicalFrame(id=3, duration_ms=125, x=12, y=0, width=4, height=4),
        ),
        clips=(
            CanonicalClip(name="idle", frame_ids=(0, 1), loop=True, priority=0),
            CanonicalClip(name="chase", frame_ids=(1, 0), loop=True, priority=10),
        ),
        fallback="idle",
        atlas_sha256="0" * 64,
        manifest_sha256="0" * 64,
        provenance_sha256="0" * 64,
        checksum_sha256="0" * 64,
        feet_anchor=CanonicalAnchor(x=0.5, y=1.0),
        mouth_overlays=(
            CanonicalMouthOverlay(name="open", frame_id=2),
            CanonicalMouthOverlay(name="closed", frame_id=3),
        ),
        _atlas_bytes=atlas_bytes,
    )


@pytest.mark.parametrize("scale", [1, 2, 3])
def test_nearest_neighbor_sharp_edges_and_no_halos_at_1x_2x_3x(
    qapp: QApplication, scale: int
) -> None:
    renderer = SpriteRenderer(_make_pack())
    size = QSize(4 * scale, 4 * scale)
    image, info = renderer.render_to_image(size, frame_id=0, scale=scale)

    assert info.layout.scale == scale
    assert image.size() == size

    for y in range(4 * scale):
        for x in range(4 * scale):
            color = image.pixelColor(x, y)
            in_inner = scale <= x < 3 * scale and scale <= y < 3 * scale
            if in_inner:
                assert color.getRgb() == (255, 0, 0, 255)
            else:
                # Zero halo: surrounding pixels stay fully transparent (0, 0, 0, 0).
                assert color.alpha() == 0


def test_mouth_overlay_composites_without_halo(qapp: QApplication) -> None:
    renderer = SpriteRenderer(_make_pack())
    image, info = renderer.render_to_image(
        QSize(8, 8),
        frame_id=0,
        mouth=MouthOverlay("open"),
        scale=2,
    )

    assert info.frame_id == 0
    assert info.mouth_frame_id == 2
    # Source (1,2) scaled 2x -> (2..3, 4..5) becomes pure green from mouth overlay.
    for y in (4, 5):
        for x in (2, 3):
            assert image.pixelColor(x, y).getRgb() == (0, 255, 0, 255)
    # Adjacent body pixel (2,2) stays pure red.
    assert image.pixelColor(2, 2).getRgb() == (255, 0, 0, 255)
    # Outer pixel remains fully transparent.
    assert image.pixelColor(0, 0).alpha() == 0


def test_reduced_motion_pins_stationary_frame(qapp: QApplication) -> None:
    renderer = SpriteRenderer(_make_pack())
    image, info = renderer.render_to_image(
        QSize(8, 8),
        clip_name="chase",
        frame_id=0,
        frame_key="frame-0",
        scale=2,
        reduced_motion=True,
    )
    # First frame of chase clip is frame 1 (blue).
    assert info.frame_id == 1
    assert info.reduced_motion is True
    assert image.pixelColor(2, 2).getRgb() == (0, 0, 255, 255)


def test_device_pixel_ratio_snaps_to_integer_device_pixels(qapp: QApplication) -> None:
    renderer = SpriteRenderer(_make_pack())
    layout = renderer.compute_layout(QSize(16, 16), device_pixel_ratio=1.5, margin_logical=2)

    assert layout.device_rect.width() % 4 == 0
    assert layout.device_rect.height() % 4 == 0
    assert layout.scale >= 1
    assert layout.hit_rect.width() > 0
    assert layout.hit_rect.height() > 0


def test_unknown_frame_or_mouth_fails_closed_to_safe_idle(qapp: QApplication) -> None:
    renderer = SpriteRenderer(_make_pack())
    image, info = renderer.render_to_image(
        QSize(8, 8),
        clip_name="nonexistent",
        frame_id=999,
        frame_key="frame-999",
        mouth="smile",  # not present in test pack
        scale=2,
    )

    assert info.frame_id == 0
    assert info.mouth_frame_id is None
    assert image.pixelColor(2, 2).getRgb() == (255, 0, 0, 255)


def test_pet_window_renders_packaged_idle_and_syncs_with_player(
    qapp: QApplication, tmp_path: Path
) -> None:
    from daemon_reborn.ui.pet import PetWindow

    pack = load_packaged_idle_assets()
    pet = PetWindow(asset_pack=pack)
    pet.set_asset_pack(_make_pack())
    player = SpritePlayer(
        [
            SpriteClip.from_frames(
                "idle",
                [SpriteFrame("frame-1", 0.5)],
            )
        ],
        fallback="idle",
        clock=lambda: 0.0,
    )
    pet.sync_from_player(player, mouth="open")
    rendered = QImage(pet.size(), QImage.Format.Format_RGBA8888)
    rendered.fill(0)
    pet.render(rendered)
    assert not rendered.isNull()
    assert pet.mask().contains(pet.rect().center())
    assert not pet.mask().contains(pet.rect().topLeft())
    pet.shutdown()


def test_pet_window_ignores_invalid_mouth_intent(qapp: QApplication) -> None:
    from daemon_reborn.ui.pet import PetWindow

    pet = PetWindow(asset_pack=_make_pack())
    pet.set_sprite_state(mouth="not-an-authored-pose")

    assert pet._mouth_overlay is None
    pet.shutdown()
