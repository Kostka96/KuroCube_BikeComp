import os
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath

from ui_utils import load_icon

# Тот же акцентный зелёный, что используется для скорости и активных
# элементов на остальных экранах — чтобы HUD громкости не выглядел
# инородным поверх основного интерфейса.
ACCENT_COLOR = "#39e07a"
MUTED_COLOR = "#6f6f6b"
BG_COLOR = QColor(15, 15, 14, 225)
TRACK_COLOR = QColor(255, 255, 255, 28)


class VolumeHUD(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._volume = 0.5  # Значение от 0.0 до 1.0
        self._target_volume = 0.5

        # Геометрия капсулы — увеличена относительно первой версии
        self.hud_width = 48
        self.hud_height = 180
        self.margin_left = 16

        self.padding_top = 12
        self.track_width = 14
        self.track_height = 100
        self.track_x = (self.hud_width - self.track_width) / 2
        self.track_y = self.padding_top

        self.percent_y = self.track_y + self.track_height + 8
        self.percent_h = 18

        self.icon_size = 26
        self.icon_y = self.percent_y + self.percent_h + 4
        self.icon_x = (self.hud_width - self.icon_size) / 2

        self.resize(self.hud_width, self.hud_height)
        self.hide()

        # Кэш перекрашенных иконок — грузим/красим SVG один раз на комбинацию
        # (имя, цвет), а не на каждый paintEvent во время анимации
        self._icon_cache = {}

        # Таймер автоскрытия
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(1800)
        self.hide_timer.timeout.connect(self.hide)

        # Плавная анимация шкалы (~60 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(16)
        self.anim_timer.timeout.connect(self._animate_step)

    def set_volume(self, val):
        """Принимает громкость (float 0.0-1.0 или int 0-100)."""
        try:
            val = float(val)
        except (ValueError, TypeError):
            return

        if val > 1.0:
            val /= 100.0
        val = max(0.0, min(1.0, val))

        self._target_volume = val
        if not self.anim_timer.isActive():
            self.anim_timer.start()

        self.update_position()
        self.show()
        self.raise_()
        self.hide_timer.start()

    def _animate_step(self):
        diff = self._target_volume - self._volume
        if abs(diff) < 0.004:
            self._volume = self._target_volume
            self.anim_timer.stop()
        else:
            self._volume += diff * 0.25
        self.update()

    def update_position(self):
        if self.parentWidget():
            p_height = self.parentWidget().height()
            y = (p_height - self.hud_height) // 2
            self.move(self.margin_left, y)

    def _icon_name(self):
        if self._volume <= 0.02:
            return "volume_off"
        if self._volume < 0.55:
            return "volume_min"
        return "volume_max"

    def _speaker_icon(self, color):
        name = self._icon_name()
        key = (name, color)
        if key not in self._icon_cache:
            self._icon_cache[key] = load_icon(name, self.icon_size, self.icon_size, color)
        return self._icon_cache[key]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect())
        color = ACCENT_COLOR if self._volume > 0.02 else MUTED_COLOR

        # 1. Фон капсулы — тёмная карточка, как остальные элементы интерфейса
        bg_path = QPainterPath()
        bg_path.addRoundedRect(rect, 20, 20)
        painter.fillPath(bg_path, BG_COLOR)

        # 2. Дорожка (пустой трек) под заливкой
        track_rect = QRectF(self.track_x, self.track_y, self.track_width, self.track_height)
        track_path = QPainterPath()
        track_path.addRoundedRect(track_rect, self.track_width / 2, self.track_width / 2)
        painter.fillPath(track_path, TRACK_COLOR)

        # 3. Заливка громкости снизу вверх, акцентным цветом
        fill_height = self.track_height * self._volume
        if fill_height > 1:
            fill_rect = QRectF(
                self.track_x,
                self.track_y + self.track_height - fill_height,
                self.track_width,
                fill_height,
            )
            fill_path = QPainterPath()
            fill_path.addRoundedRect(fill_rect, self.track_width / 2, self.track_width / 2)
            painter.fillPath(fill_path, QColor(color))

        # 4. Процент громкости
        painter.setPen(QColor("#e8e8e6"))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        percent_rect = QRectF(0, self.percent_y, self.hud_width, self.percent_h)
        painter.drawText(percent_rect, Qt.AlignmentFlag.AlignCenter, f"{int(round(self._volume * 100))}")

        # 5. Иконка динамика — volume_off / volume_min / volume_max по уровню
        icon = self._speaker_icon(color)
        painter.drawPixmap(int(self.icon_x), int(self.icon_y), icon)

        painter.end()