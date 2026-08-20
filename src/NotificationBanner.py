from PyQt6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve
from PyQt6.QtGui import QColor

from ui_utils import load_icon

# Тот же акцентный зелёный, что и на остальных экранах / в VolumeHUD
ACCENT_COLOR = "#39e07a"

# Иконка по категории уведомления (ANCS category_id уже приходит строкой
# из BluetoothThread.notification_received). Если для какой-то категории
# файла нет в resources/icons — load_icon просто вернёт пустой пиксель,
# приложение не упадёт.
CATEGORY_ICONS = {
    "IncomingCall": "phone",
    "MissedCall": "phone",
    "VoicemailMessage": "phone",
    "Email": "mail",
    "NewsFlash": "bell",
    "SocialMedia": "message",
    "Other": "bell",
}


class NotificationBanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.banner_width = 460
        self.banner_height = 116
        self.top_margin = 16
        self.setFixedSize(self.banner_width, self.banner_height)
        self.setObjectName("bannerRoot")

        self.setStyleSheet(f"""
            QFrame#bannerRoot {{
                background-color: #161614;
                border: 1px solid #232320;
                border-radius: 22px;
            }}
            QLabel#title {{
                font-weight: 600;
                font-size: 20px;
                color: #ffffff;
            }}
            QLabel#message {{
                font-size: 16px;
                color: #c4c4c0;
            }}
        """)

        # Тень — чтобы баннер визуально "парил" над картой/остальным контентом
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 170))
        self.setGraphicsEffect(shadow)

        # Акцентная полоска слева вместо синей рамки по периметру
        self.accent_bar = QFrame(self)
        self.accent_bar.setStyleSheet(f"background-color: {ACCENT_COLOR}; border-radius: 3px;")
        self.accent_bar.setFixedSize(5, self.banner_height - 32)

        # Круглая "аватарка" с иконкой категории уведомления
        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(56, 56)
        self.icon_label.setStyleSheet("background-color: rgba(57, 224, 122, 0.14); border-radius: 28px;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("Sender")
        self.title_label.setObjectName("title")

        self.msg_label = QLabel("Message content...")
        self.msg_label.setObjectName("message")
        self.msg_label.setWordWrap(True)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.msg_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 16, 20, 16)
        layout.setSpacing(16)
        layout.addWidget(self.accent_bar)
        layout.addWidget(self.icon_label)
        layout.addLayout(text_layout, 1)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._start_slide_out)

        self.slide_anim = QPropertyAnimation(self, b"pos")
        self.slide_anim.setDuration(280)
        self.slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.slide_anim.finished.connect(self._on_anim_finished)
        self._closing = False

        self._icon_cache = {}
        self.hide()

    def show_notification(self, title, message, category="Other", timeout_ms=5000):
        self.title_label.setText(title)
        self.msg_label.setText(message[:70] + ("…" if len(message) > 70 else ""))
        self.icon_label.setPixmap(self._category_icon(category))

        if self.parent():
            p_width = self.parent().width()
            target_x = (p_width - self.width()) // 2
        else:
            target_x = 0
        target_y = self.top_margin

        self._closing = False
        self.slide_anim.stop()
        self.move(target_x, -self.banner_height)
        self.show()
        self.raise_()

        # Слайд сверху вниз вместо мгновенного появления
        self.slide_anim.setStartValue(QPoint(target_x, -self.banner_height))
        self.slide_anim.setEndValue(QPoint(target_x, target_y))
        self.slide_anim.start()

        self.hide_timer.start(timeout_ms)

    def _start_slide_out(self):
        self._closing = True
        start = self.pos()
        end = QPoint(start.x(), -self.banner_height)
        self.slide_anim.stop()
        self.slide_anim.setStartValue(start)
        self.slide_anim.setEndValue(end)
        self.slide_anim.start()

    def _on_anim_finished(self):
        if self._closing:
            self.hide()

    def hide_banner(self):
        """Оставлен для обратной совместимости — теперь тоже уезжает вверх, а не пропадает мгновенно."""
        self.hide_timer.stop()
        self._start_slide_out()

    def _category_icon(self, category):
        icon_name = CATEGORY_ICONS.get(category, "bell")
        if icon_name not in self._icon_cache:
            self._icon_cache[icon_name] = load_icon(icon_name, 28, 28, ACCENT_COLOR)
        return self._icon_cache[icon_name]