from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea,
    QWidget, QPushButton, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QPoint, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics
from PyQt6.QtWidgets import QLabel, QSizePolicy
from ui_utils import load_icon

ACCENT_COLOR = "#39e07a"

CATEGORY_ICONS = {
    "IncomingCall": "phone",
    "MissedCall": "phone",
    "VoicemailMessage": "phone",
    "Email": "mail",
    "NewsFlash": "bell",
    "SocialMedia": "message",
    "Other": "bell",
}


class ElidedLabel(QLabel):
    """QLabel, который автоматически обрезает текст многоточием (...) при нехватке ширины."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text

        # Разрешаем лейблу сжиматься меньше размера полного текста
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str):
        self._full_text = str(text) if text is not None else ""
        self._update_text()

    def resizeEvent(self, event):
        self._update_text()
        super().resizeEvent(event)

    def _update_text(self):
        if not self._full_text or self.width() <= 0:
            super().setText(self._full_text)
            return

        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        super().setText(elided)


class NotificationCard(QFrame):
    """Одна карточка уведомления в списке."""

    def __init__(self, title, message, time_str, category="Other", icon_cache=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #161614;
                border-radius: 14px;
            }
            QLabel#cardTitle { font-weight: 600; font-size: 15px; color: #ffffff; }
            QLabel#cardMessage { font-size: 13px; color: #b0b0ac; }
            QLabel#cardTime { font-size: 11px; color: #6f6f6b; }
        """)

        icon_label = QLabel(self)
        icon_label.setFixedSize(40, 40)
        icon_label.setStyleSheet("background-color: rgba(57, 224, 122, 0.14); border-radius: 20px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_name = CATEGORY_ICONS.get(category, "bell")
        if icon_cache is not None:
            if icon_name not in icon_cache:
                icon_cache[icon_name] = load_icon(icon_name, 20, 20, ACCENT_COLOR)
            icon_label.setPixmap(icon_cache[icon_name])
        else:
            icon_label.setPixmap(load_icon(icon_name, 20, 20, ACCENT_COLOR))

        # Заголовок с авто-обрезанием многоточием
        title_label = ElidedLabel(title)
        title_label.setObjectName("cardTitle")

        time_label = QLabel(time_str)
        time_label.setObjectName("cardTime")

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        # title_label забирает всё свободное пространство (stretch=1)
        header_row.addWidget(title_label, 1)
        header_row.addWidget(time_label, 0, Qt.AlignmentFlag.AlignRight)

        msg_label = QLabel(message)
        msg_label.setObjectName("cardMessage")
        msg_label.setWordWrap(True)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        text_layout.addLayout(header_row)
        text_layout.addWidget(msg_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(icon_label)
        layout.addLayout(text_layout, 1)


class NotificationsPanel(QFrame):
    """Полноэкранная выезжающая сверху панель со списком всех уведомлений."""

    cleared = pyqtSignal()  # пользователь нажал "Очистить всё"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notifPanel")
        self.setStyleSheet("""
            QFrame#notifPanel {
                background-color: #0a0a0a;
                border-bottom-left-radius: 26px;
                border-bottom-right-radius: 26px;
            }
            QLabel#panelHeader { font-weight: 700; font-size: 20px; color: #ffffff; }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

        header_label = QLabel("Уведомления")
        header_label.setObjectName("panelHeader")

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(36, 36)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #161614;
                color: #e8e8e6;
                border-radius: 18px;
                font-size: 15px;
            }
            QPushButton:pressed { background-color: #232320; }
        """)
        self.close_btn.clicked.connect(self.close_panel)

        self.clear_btn = QPushButton("Очистить всё")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #e2665f;
                font-size: 26px;
            }
        """)
        self.clear_btn.clicked.connect(self._on_clear_clicked)

        header_row = QHBoxLayout()
        header_row.addWidget(header_label)
        header_row.addStretch(1)
        header_row.addWidget(self.close_btn)

        self.empty_label = QLabel("Пока нет уведомлений")
        self.empty_label.setStyleSheet("color: #6f6f6b; font-size: 14px;")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(10)
        self.list_layout.addWidget(self.empty_label)
        self.list_layout.addStretch(1)

        list_container = QWidget()
        list_container.setLayout(self.list_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll_area.setWidget(list_container)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 16)
        root_layout.setSpacing(12)
        root_layout.addLayout(header_row)
        root_layout.addWidget(self.clear_btn, alignment=Qt.AlignmentFlag.AlignRight)
        root_layout.addWidget(self.scroll_area, 1)

        self._icon_cache = {}
        self._is_open = False

        self.slide_anim = QPropertyAnimation(self, b"pos")
        self.slide_anim.setDuration(300)
        self.slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.slide_anim.finished.connect(self._on_anim_finished)

        self.hide()

    def _panel_size(self):
        if self.parentWidget():
            w = self.parentWidget().width()
            h = int(self.parentWidget().height() * 0.78)
        else:
            w, h = 480, 620
        return w, h

    def set_notifications(self, entries):
        """entries: список dict {'title','message','time','category'}, самые новые — первыми."""
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget and widget != self.empty_label:
                widget.deleteLater()
            elif widget == self.empty_label:
                self.empty_label.setParent(None)

        if not entries:
            self.list_layout.addWidget(self.empty_label)
            self.empty_label.show()
        else:
            self.empty_label.hide()
            for entry in entries:
                card = NotificationCard(
                    entry.get("title", ""),
                    entry.get("message", ""),
                    entry.get("time", ""),
                    entry.get("category", "Other"),
                    icon_cache=self._icon_cache,
                )
                self.list_layout.addWidget(card)

        self.list_layout.addStretch(1)

    def open_panel(self):
        w, h = self._panel_size()
        self.resize(w, h)

        self._is_open = True
        self.slide_anim.stop()
        self.move(0, -h)
        self.show()
        self.raise_()
        self.slide_anim.setStartValue(QPoint(0, -h))
        self.slide_anim.setEndValue(QPoint(0, 0))
        self.slide_anim.start()

    def close_panel(self):
        if not self._is_open:
            return
        self._is_open = False
        h = self.height()
        self.slide_anim.stop()
        self.slide_anim.setStartValue(self.pos())
        self.slide_anim.setEndValue(QPoint(0, -h))
        self.slide_anim.start()

    def toggle(self):
        self.close_panel() if self._is_open else self.open_panel()

    def _on_anim_finished(self):
        if not self._is_open:
            self.hide()

    def _on_clear_clicked(self):
        self.set_notifications([])
        self.cleared.emit()