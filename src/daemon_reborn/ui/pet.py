"""Small transparent sprite-rendered companion window."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QCloseEvent, QCursor, QMouseEvent, QPainter, QPaintEvent, QRegion
from PySide6.QtWidgets import QWidget

from daemon_reborn.animation.director import MouthOverlay
from daemon_reborn.animation.player import SpritePlayer
from daemon_reborn.animation.renderer import SpriteRenderer
from daemon_reborn.assets.canonical import CanonicalAssetPack, load_packaged_idle_assets
from daemon_reborn.ui.physics import PetPhysics, PhysicsBounds, Vec2


class PetWindow(QWidget):
    """A passive, compact topmost window rendered by the single SpriteRenderer."""

    def __init__(self, asset_pack: CanonicalAssetPack | None = None) -> None:
        super().__init__()
        self._shutdown = False
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(160, 160)
        self._renderer = SpriteRenderer(
            asset_pack if asset_pack is not None else load_packaged_idle_assets()
        )
        self._clip_name: str | None = self._renderer.pack.fallback
        self._frame_id: int | None = None
        self._frame_key: str | None = None
        self._mouth_overlay: MouthOverlay | None = None
        self._reduced_motion = False
        self._hit_margin = 16
        self._update_hit_mask()
        self._drag_origin: QPoint | None = None
        self._drag_pointer: QPoint | None = None
        self._position_changed: Callable[[], None] | None = None
        self._physics: PetPhysics | None = None

    @property
    def renderer(self) -> SpriteRenderer:
        """Return the single sprite renderer instance owned by this window."""

        return self._renderer

    @property
    def reduced_motion(self) -> bool:
        """Whether reduced-motion stationary rendering is enabled."""

        return self._reduced_motion

    def set_asset_pack(self, asset_pack: CanonicalAssetPack) -> None:
        """Swap the active canonical sprite pack and refresh hit bounds."""

        self._renderer = SpriteRenderer(asset_pack)
        self._clip_name = asset_pack.fallback
        self._frame_id = None
        self._frame_key = None
        self._update_hit_mask()
        self.update()

    def set_reduced_motion(self, enabled: bool) -> None:
        """Toggle stationary reduced-motion frame rendering."""

        self._reduced_motion = bool(enabled)
        self.update()

    def set_sprite_state(
        self,
        *,
        clip_name: str | None = None,
        frame_id: int | None = None,
        frame_key: str | None = None,
        mouth: MouthOverlay | str | None = None,
    ) -> None:
        """Update the active sprite frame and optional mouth overlay without stealing focus."""

        if clip_name is not None:
            self._clip_name = clip_name
        self._frame_id = frame_id
        self._frame_key = frame_key
        if isinstance(mouth, str):
            try:
                self._mouth_overlay = MouthOverlay(mouth)
            except ValueError:
                # External animation intents are untrusted at this UI boundary.
                # Preserve the last valid base frame and omit an invalid overlay.
                self._mouth_overlay = None
        else:
            self._mouth_overlay = mouth
        self.update()

    def sync_from_player(
        self,
        player: SpritePlayer,
        *,
        mouth: MouthOverlay | str | None = None,
    ) -> None:
        """Synchronize window sprite state with the current SpritePlayer frame."""

        current_frame = player.frame
        self.set_sprite_state(
            clip_name=player.clip.name,
            frame_key=current_frame.key,
            mouth=mouth,
        )

    def _update_hit_mask(self) -> None:
        layout = self._renderer.compute_layout(
            self.size(),
            device_pixel_ratio=max(1.0, float(self.devicePixelRatioF())),
            margin_logical=self._hit_margin,
        )
        self.setMask(QRegion(layout.hit_rect))

    def set_position_changed_callback(self, callback: Callable[[], None]) -> None:
        """Set the callback used to remember the screen anchor after dragging."""
        self._position_changed = callback

    @property
    def is_shutdown(self) -> bool:
        """Whether the application has permanently closed this window."""
        return self._shutdown

    @property
    def is_dragging(self) -> bool:
        """Whether a pointer drag is currently in progress."""
        return self._drag_origin is not None and self._drag_pointer is not None

    def set_physics_bounds(self, bounds: QRect) -> None:
        """Update logical physics bounds and synchronize with the visible window."""
        if self._physics is None:
            self._physics = PetPhysics(
                Vec2(float(self.x()), float(self.y())),
                Vec2(float(self.width()), float(self.height())),
                PhysicsBounds(
                    float(bounds.left()),
                    float(bounds.top()),
                    float(bounds.right() + 1),
                    float(bounds.bottom() + 1),
                ),
            )
        else:
            self._physics.set_bounds(
                PhysicsBounds(
                    float(bounds.left()),
                    float(bounds.top()),
                    float(bounds.right() + 1),
                    float(bounds.bottom() + 1),
                )
            )
            self._physics.set_position(Vec2(float(self.x()), float(self.y())))

    def advance_physics(self, delta_seconds: float, target: QPoint | None = None) -> None:
        """Advance physics and apply the logical position to the Qt window."""
        if self._physics is None or self.is_dragging:
            return
        self._physics.set_position(Vec2(float(self.x()), float(self.y())))
        chase_target = target or QCursor.pos()
        self._physics.step(delta_seconds, Vec2(float(chase_target.x()), float(chase_target.y())))
        self.move(round(self._physics.position.x), round(self._physics.position.y))

    def shutdown(self) -> None:
        """Allow the close event through during application shutdown."""
        self._shutdown = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._shutdown:
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = self.pos()
            self._drag_pointer = event.globalPosition().toPoint()
            if self._physics is not None:
                self._physics.begin_drag(
                    Vec2(float(self._drag_pointer.x()), float(self._drag_pointer.y()))
                )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None and self._drag_pointer is not None:
            delta = event.globalPosition().toPoint() - self._drag_pointer
            if self._physics is not None:
                pointer = event.globalPosition().toPoint()
                self._physics.drag_to(Vec2(float(pointer.x()), float(pointer.y())))
                self.move(round(self._physics.position.x), round(self._physics.position.y))
            else:
                self.move(self._drag_origin + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_origin is not None:
            self._drag_origin = None
            self._drag_pointer = None
            if self._physics is not None:
                self._physics.release()
            if self._position_changed is not None:
                self._position_changed()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            self._renderer.render_to_painter(
                painter,
                self.size(),
                clip_name=self._clip_name,
                frame_id=self._frame_id,
                frame_key=self._frame_key,
                mouth=self._mouth_overlay,
                device_pixel_ratio=max(1.0, float(self.devicePixelRatioF())),
                margin_logical=self._hit_margin,
                reduced_motion=self._reduced_motion,
            )
        finally:
            painter.end()
