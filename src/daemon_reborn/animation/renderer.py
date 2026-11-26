"""Single Qt nearest-neighbor sprite renderer with pixel-safe scaling."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from daemon_reborn.animation.director import MouthOverlay

if TYPE_CHECKING:
    from daemon_reborn.assets.canonical import CanonicalAssetPack, CanonicalFrame

DEFAULT_FEET_ANCHOR: Final[tuple[float, float]] = (0.5, 1.0)


@dataclass(frozen=True, slots=True)
class SpriteRenderLayout:
    """Pixel-snapped destination geometry in logical and device coordinates."""

    logical_rect: QRectF
    device_rect: QRect
    hit_rect: QRect
    scale: int


@dataclass(frozen=True, slots=True)
class RenderedSpriteInfo:
    """Resolved frame, mouth overlay, and layout applied in a draw pass."""

    frame_id: int
    mouth_frame_id: int | None
    layout: SpriteRenderLayout
    reduced_motion: bool


def _parse_frame_key(frame_key: str) -> int | None:
    if frame_key.startswith("frame-"):
        raw = frame_key[6:]
        if raw.isdigit():
            return int(raw)
    return None


class SpriteRenderer:
    """Render validated canonical sprite packs via nearest-neighbor QPainter draws."""

    def __init__(self, pack: CanonicalAssetPack) -> None:
        from daemon_reborn.assets.canonical import CanonicalAssetPack

        if not isinstance(pack, CanonicalAssetPack):
            raise TypeError("pack must be CanonicalAssetPack")
        self._pack = pack
        self._frames_by_id: dict[int, CanonicalFrame] = {frame.id: frame for frame in pack.frames}
        self._clips_by_name = {clip.name: clip for clip in pack.clips}
        self._mouths_by_name = {mouth.name: mouth.frame_id for mouth in pack.mouth_overlays}
        self._pixmap: QPixmap | None = None

    @property
    def pack(self) -> CanonicalAssetPack:
        return self._pack

    def invalidate_pixmap(self) -> None:
        """Drop any cached GUI pixmap (e.g. if the asset pack is swapped)."""

        self._pixmap = None

    def _get_pixmap(self) -> QPixmap:
        if self._pixmap is None:
            pixmap = self._pack.build_pixmap()
            if not isinstance(pixmap, QPixmap) or pixmap.isNull():
                raise ValueError("failed to construct sprite atlas QPixmap")
            self._pixmap = pixmap
        return self._pixmap

    def resolve_frame_id(
        self,
        *,
        clip_name: str | None = None,
        frame_id: int | None = None,
        frame_key: str | None = None,
        reduced_motion: bool = False,
    ) -> int:
        """Select a valid frame ID, clamping to a stationary frame in reduced motion."""

        if not isinstance(reduced_motion, bool):
            raise TypeError("reduced_motion must be a bool")

        fallback_clip = self._clips_by_name[self._pack.fallback]
        fallback_frame_id = fallback_clip.frame_ids[0]

        if reduced_motion:
            if clip_name is not None and clip_name in self._clips_by_name:
                return self._clips_by_name[clip_name].frame_ids[0]
            return fallback_frame_id

        if (
            frame_id is not None
            and not isinstance(frame_id, bool)
            and frame_id in self._frames_by_id
        ):
            return frame_id

        if frame_key is not None:
            parsed = _parse_frame_key(frame_key)
            if parsed is not None and parsed in self._frames_by_id:
                return parsed

        if clip_name is not None and clip_name in self._clips_by_name:
            return self._clips_by_name[clip_name].frame_ids[0]

        return fallback_frame_id

    def resolve_mouth_frame_id(self, mouth: MouthOverlay | str | None) -> int | None:
        """Resolve an optional mouth overlay pose ID to an atlas frame ID."""

        if mouth is None:
            return None
        pose_id = mouth.pose_id if isinstance(mouth, MouthOverlay) else mouth
        if not isinstance(pose_id, str):
            raise TypeError("mouth pose must be MouthOverlay, str, or None")
        frame_id = self._mouths_by_name.get(pose_id)
        if frame_id is None or frame_id not in self._frames_by_id:
            return None
        return frame_id

    def compute_layout(
        self,
        viewport_size: QSize,
        *,
        device_pixel_ratio: float = 1.0,
        scale: int | None = None,
        margin_logical: int = 0,
    ) -> SpriteRenderLayout:
        """Compute integer-scaled, pixel-snapped bounds anchored at the character's feet."""

        if (
            not isinstance(viewport_size, QSize)
            or viewport_size.width() <= 0
            or viewport_size.height() <= 0
        ):
            raise ValueError("viewport_size must have positive width and height")
        if (
            isinstance(device_pixel_ratio, bool)
            or not isinstance(device_pixel_ratio, (int, float))
            or not math.isfinite(device_pixel_ratio)
            or device_pixel_ratio <= 0.0
        ):
            raise ValueError("device_pixel_ratio must be finite and positive")
        if margin_logical < 0:
            raise ValueError("margin_logical must be non-negative")

        canvas_w, canvas_h = self._pack.canvas
        dpr = float(device_pixel_ratio)
        phys_w = max(1, round(viewport_size.width() * dpr))
        phys_h = max(1, round(viewport_size.height() * dpr))
        phys_margin = round(margin_logical * dpr)
        avail_w = max(1, phys_w - 2 * phys_margin)
        avail_h = max(1, phys_h - 2 * phys_margin)

        if scale is not None:
            if isinstance(scale, bool) or not isinstance(scale, int) or scale < 1:
                raise ValueError("scale must be a positive integer")
            chosen_scale = scale
        else:
            chosen_scale = max(1, min(avail_w // canvas_w, avail_h // canvas_h))

        dest_phys_w = canvas_w * chosen_scale
        dest_phys_h = canvas_h * chosen_scale

        anchor_x = (
            self._pack.feet_anchor.x
            if self._pack.feet_anchor is not None
            else DEFAULT_FEET_ANCHOR[0]
        )
        anchor_y = (
            self._pack.feet_anchor.y
            if self._pack.feet_anchor is not None
            else DEFAULT_FEET_ANCHOR[1]
        )

        # Anchor horizontally around the feet anchor and keep the baseline inside
        # the available viewport so feet never jump or clip across frame sizes.
        target_anchor_x = round(phys_w * anchor_x)
        target_anchor_y = round(phys_margin + avail_h * anchor_y)
        if anchor_y < 0.5:
            target_anchor_y = round(phys_h * anchor_y)
        dest_phys_x = round(target_anchor_x - dest_phys_w * anchor_x)
        dest_phys_y = round(target_anchor_y - dest_phys_h * anchor_y)

        # Clamp within physical viewport when the viewport fits the sprite.
        if dest_phys_w <= phys_w:
            dest_phys_x = max(0, min(dest_phys_x, phys_w - dest_phys_w))
        if dest_phys_h <= phys_h:
            dest_phys_y = max(0, min(dest_phys_y, phys_h - dest_phys_h))

        device_rect = QRect(dest_phys_x, dest_phys_y, dest_phys_w, dest_phys_h)
        logical_rect = QRectF(
            dest_phys_x / dpr,
            dest_phys_y / dpr,
            dest_phys_w / dpr,
            dest_phys_h / dpr,
        )
        hit_x = max(0, math.floor(logical_rect.x()))
        hit_y = max(0, math.floor(logical_rect.y()))
        hit_w = max(1, min(viewport_size.width() - hit_x, math.ceil(logical_rect.width())))
        hit_h = max(1, min(viewport_size.height() - hit_y, math.ceil(logical_rect.height())))
        return SpriteRenderLayout(
            logical_rect=logical_rect,
            device_rect=device_rect,
            hit_rect=QRect(hit_x, hit_y, hit_w, hit_h),
            scale=chosen_scale,
        )

    def render_to_painter(
        self,
        painter: QPainter,
        viewport_size: QSize,
        *,
        clip_name: str | None = None,
        frame_id: int | None = None,
        frame_key: str | None = None,
        mouth: MouthOverlay | str | None = None,
        device_pixel_ratio: float = 1.0,
        scale: int | None = None,
        margin_logical: int = 0,
        reduced_motion: bool = False,
    ) -> RenderedSpriteInfo:
        """Draw the selected sprite frame and optional mouth overlay with nearest-neighbor."""

        resolved_frame_id = self.resolve_frame_id(
            clip_name=clip_name,
            frame_id=frame_id,
            frame_key=frame_key,
            reduced_motion=reduced_motion,
        )
        mouth_frame_id = self.resolve_mouth_frame_id(mouth)
        layout = self.compute_layout(
            viewport_size,
            device_pixel_ratio=device_pixel_ratio,
            scale=scale,
            margin_logical=margin_logical,
        )

        pixmap = self._get_pixmap()
        base_frame = self._frames_by_id[resolved_frame_id]
        src_rect = QRectF(base_frame.x, base_frame.y, base_frame.width, base_frame.height)

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawPixmap(layout.logical_rect, pixmap, src_rect)
            if mouth_frame_id is not None:
                mouth_frame = self._frames_by_id[mouth_frame_id]
                mouth_src = QRectF(
                    mouth_frame.x,
                    mouth_frame.y,
                    mouth_frame.width,
                    mouth_frame.height,
                )
                painter.drawPixmap(layout.logical_rect, pixmap, mouth_src)
        finally:
            painter.restore()

        return RenderedSpriteInfo(
            frame_id=resolved_frame_id,
            mouth_frame_id=mouth_frame_id,
            layout=layout,
            reduced_motion=reduced_motion,
        )

    def render_to_image(
        self,
        viewport_size: QSize,
        *,
        clip_name: str | None = None,
        frame_id: int | None = None,
        frame_key: str | None = None,
        mouth: MouthOverlay | str | None = None,
        device_pixel_ratio: float = 1.0,
        scale: int | None = None,
        margin_logical: int = 0,
        reduced_motion: bool = False,
    ) -> tuple[QImage, RenderedSpriteInfo]:
        """Render onto a transparent RGBA QImage for deterministic snapshot testing."""

        dpr = float(device_pixel_ratio)
        phys_w = max(1, round(viewport_size.width() * dpr))
        phys_h = max(1, round(viewport_size.height() * dpr))
        image = QImage(phys_w, phys_h, QImage.Format.Format_RGBA8888)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)
        try:
            info = self.render_to_painter(
                painter,
                viewport_size,
                clip_name=clip_name,
                frame_id=frame_id,
                frame_key=frame_key,
                mouth=mouth,
                device_pixel_ratio=dpr,
                scale=scale,
                margin_logical=margin_logical,
                reduced_motion=reduced_motion,
            )
        finally:
            painter.end()
        return image, info


__all__ = [
    "DEFAULT_FEET_ANCHOR",
    "RenderedSpriteInfo",
    "SpriteRenderLayout",
    "SpriteRenderer",
]
