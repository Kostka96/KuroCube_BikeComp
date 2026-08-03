import os
from PyQt6.QtGui import QColor, QPixmap, QPainter
from PyQt6.QtCore import Qt


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