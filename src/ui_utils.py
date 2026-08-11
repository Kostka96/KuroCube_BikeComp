import os
from PyQt6.QtGui import QColor, QPixmap, QPainter
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel

def get_colored_pixmap(file_path, width, height, color):
    """
    Загружает SVG или PNG и перекрашивает его в указанный цвет.
    """
    if not os.path.exists(file_path):
        # Если файла нет, возвращаем пустой пиксель, чтобы программа не падала
        print(f"Предупреждение: Иконка не найдена {file_path}")
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        return pixmap

    pixmap = QPixmap(file_path)
    if pixmap.isNull():
        return pixmap

    # Масштабируем до нужного размера
    pixmap = pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)

    # Перекрашиваем
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()

    return pixmap


def load_icon(icon_name, width=24, height=24, color="#CCCCCC"):
    """
    Удобная обертка для загрузки иконок из папки icons/.
    Пример: load_icon("temp") -> ищет icons/temp.svg
    """
    # Ищем файл с расширением .svg или .png
    base_path = os.path.join(os.path.dirname(__file__), "../resources/icons")
    svg_path = os.path.join(base_path, f"{icon_name}.svg")
    png_path = os.path.join(base_path, f"{icon_name}.png")

    # Сначала пробуем SVG, потом PNG
    if os.path.exists(svg_path):
        file_path = svg_path
    elif os.path.exists(png_path):
        file_path = png_path
    else:
        file_path = svg_path  # Просто вернем путь, get_colored_pixmap выдаст предупреждение

    return get_colored_pixmap(file_path, width, height, QColor(color))

class MarqueeLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = ""
        self._display_text = ""
        self._offset = 0
        self._direction = "right_to_left"  # По умолчанию: справа налево (классика)

        self._timer = QTimer(self)
        self._timer.setInterval(200)  # Интервал обновления в миллисекундах (чем меньше, тем быстрее)
        self._timer.timeout.connect(self._update_text)

    def set_speed(self, interval_ms: int):
        """
        Устанавливает скорость прокрутки.
        interval_ms: задержка в мс между шагами.
        Например: 100 — очень быстро, 200 — средне, 300 — медленно, 50 — плавно.
        """
        self._timer.setInterval(interval_ms)

    def set_direction(self, direction: str):
        """
        Направление прокрутки:
        'right_to_left' (или 'rtl') — справа налево (стандартное движение влево)
        'left_to_right' (или 'ltr') — слева направо (движение вправо)
        """
        self._direction = direction

    def set_marquee_text(self, text: str, max_len: int = 25):
        """Устанавливает текст и запускает анимацию, если текст длиннее max_len."""
        if self._full_text == text:
            return  # Не сбрасываем анимацию, если текст не изменился

        self._full_text = text
        self._offset = 0

        if len(text) > max_len:
            self._display_text = text + "   •   "
            self._timer.start()
        else:
            self._timer.stop()
            self.setText(text)

    def _update_text(self):
        if not self._display_text:
            return

        length = len(self._display_text)

        # 1. Рассчитываем сдвиг в зависимости от направления
        if self._direction in ["left_to_right", "ltr"]:
            # Слева направо: смещаем индекс назад (вправо)
            self._offset = (self._offset - 1) % length
        else:
            # Справа налево: смещаем индекс вперед (влево)
            self._offset = (self._offset + 1) % length

        # 2. Формируем циклический срез текста
        shifted = self._display_text[self._offset:] + self._display_text[:self._offset]
        self.setText(shifted[:25])  # 18 — макс. кол-во видимых символов