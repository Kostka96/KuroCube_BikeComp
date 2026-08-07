from PyQt6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint
from PyQt6.QtGui import QColor


class NotificationBanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(380, 60)
        self.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 2px solid #00aaff;
                border-radius: 10px;
            }
            QLabel {
                color: white;
            }
        """)

        self.title_label = QLabel("Sender")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #00aaff;")

        self.msg_label = QLabel("Message content...")
        self.msg_label.setStyleSheet("font-size: 12px; color: #dddddd;")
        self.msg_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.msg_label)
        layout.setContentsMargins(12, 6, 12, 6)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_banner)

        self.hide()

    def show_notification(self, title, message, timeout_ms=5000):
        self.title_label.setText(title)
        self.msg_label.setText(message[:60] + ("..." if len(message) > 60 else ""))

        # Позиционирование по центру сверху относительно родительского окна
        if self.parent():
            p_width = self.parent().width()
            self.move((p_width - self.width()) // 2, 10)

        self.show()
        self.raise_()
        self.hide_timer.start(timeout_ms)

    def hide_banner(self):
        self.hide()