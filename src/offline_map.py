import os
import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPixmap, QPen, QColor, QBrush, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QElapsedTimer


class OfflineMapWidget(QWidget):
    def __init__(self, tiles_dir="tiles", zoom=15, parent=None):
        super().__init__(parent)
        self.tiles_dir = os.path.abspath(tiles_dir)
        self.tile_size = 256

        self.gps_lat = None
        self.gps_lon = None
        self.current_lat = None
        self.current_lon = None

        self.track_points = []
        self.has_fix = False

        self.min_zoom = 12
        self.max_zoom = 16
        self._follow_gps = True

        self._tile_cache = {}
        self._max_cache = 200

        self._update_timer = QElapsedTimer()
        self._update_timer.start()

        self._dragging = False
        self._drag_start = QPointF(0, 0)
        self._drag_center = (0.0, 0.0)

        # Поиск доступных тайлов при запуске
        self.zoom, self.center_tile_x, self.center_tile_y = self._find_available_tiles(zoom)

        # Устанавливаем стартовые гео-координаты по центру найденных тайлов, если GPS ещё нет
        if self.center_tile_x > 0 and self.center_tile_y > 0:
            init_px = (self.center_tile_x + 0.5) * self.tile_size
            init_py = (self.center_tile_y + 0.5) * self.tile_size
            self.current_lat, self.current_lon = self._pixel_to_lat_lon(init_px, init_py)

        print(
            f"[MAP] Загружены тайлы: zoom={self.zoom}, X={self.center_tile_x}, Y={self.center_tile_y}, path={self.tiles_dir}")

    # -------------------------------------------------------------------------
    # Поиск доступных тайлов
    # -------------------------------------------------------------------------
    def _find_available_tiles(self, requested_zoom):
        if not os.path.exists(self.tiles_dir):
            print(f"[MAP ERROR] Папка не найдена: {self.tiles_dir}")
            return requested_zoom, 0, 0

        target_zoom = requested_zoom
        zoom_path = os.path.join(self.tiles_dir, str(target_zoom))

        if not os.path.exists(zoom_path):
            all_zooms = sorted([int(d) for d in os.listdir(self.tiles_dir) if d.isdigit()])
            if not all_zooms:
                return requested_zoom, 0, 0
            target_zoom = all_zooms[0]
            zoom_path = os.path.join(self.tiles_dir, str(target_zoom))

        found_tiles = []
        for root, _, files in os.walk(zoom_path):
            for file in files:
                if file.endswith('.png'):
                    y_str = file.rsplit('.', 1)[0]
                    x_str = os.path.basename(root)
                    if x_str.isdigit() and y_str.isdigit():
                        found_tiles.append((int(x_str), int(y_str)))

        if not found_tiles:
            print(f"[MAP WARNING] PNG тайлы не найдены в {zoom_path}")
            return target_zoom, 0, 0

        xs = [t[0] for t in found_tiles]
        ys = [t[1] for t in found_tiles]
        avg_x = (min(xs) + max(xs)) // 2
        avg_y = (min(ys) + max(ys)) // 2

        return target_zoom, avg_x, avg_y

    # -------------------------------------------------------------------------
    # Кэширование тайлов
    # -------------------------------------------------------------------------
    def _get_tile_pixmap(self, zoom, x, y):
        key = (zoom, x, y)
        if key in self._tile_cache:
            return self._tile_cache[key]

        path = os.path.join(self.tiles_dir, str(zoom), str(x), f"{y}.png")
        if os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                if len(self._tile_cache) >= self._max_cache:
                    # Удаляем самый старый элемент (FIFO)
                    oldest_key = next(iter(self._tile_cache))
                    del self._tile_cache[oldest_key]
                self._tile_cache[key] = pix
                return pix
        return None

    # -------------------------------------------------------------------------
    # Управление извне
    # -------------------------------------------------------------------------
    def zoom_in(self):
        if self.zoom < self.max_zoom:
            self.zoom += 1
            self.update()

    def zoom_out(self):
        if self.zoom > self.min_zoom:
            self.zoom -= 1
            self.update()

    def center_on_gps(self):
        self._follow_gps = True
        if self.gps_lat is not None and self.gps_lon is not None:
            self.current_lat = self.gps_lat
            self.current_lon = self.gps_lon
        self.update()

    def set_position(self, lat, lon, is_recording=False):
        self.gps_lat = lat
        self.gps_lon = lon
        self.has_fix = True

        if self._follow_gps or self.current_lat is None:
            self.current_lat = lat
            self.current_lon = lon

        if is_recording:
            # Добавляем точку только при изменении координат (фильтрация дублей)
            if not self.track_points or self.track_points[-1] != (lat, lon):
                self.track_points.append((lat, lon))

        # Ограничиваем частоту обновления кадра (не чаще чем раз в 100 мс)
        if self._update_timer.elapsed() > 100:
            self.update()
            self._update_timer.restart()

    def clear_track(self):
        self.track_points.clear()
        self.update()

    # -------------------------------------------------------------------------
    # Геометрия (Проекция Меркатора)
    # -------------------------------------------------------------------------
    def _lat_lon_to_pixel(self, lat, lon):
        lat = max(-85.05112878, min(85.05112878, lat))
        lat_rad = math.radians(lat)
        n = 2.0 ** self.zoom
        x = (lon + 180.0) / 360.0 * n * self.tile_size
        y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n * self.tile_size
        return x, y

    def _pixel_to_lat_lon(self, px, py):
        n = 2.0 ** self.zoom
        lon = (px / self.tile_size) / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * (py / self.tile_size) / n)))
        lat = math.degrees(lat_rad)
        return lat, lon

    # -------------------------------------------------------------------------
    # Отрисовка
    # -------------------------------------------------------------------------
    def paintEvent(self, event):
        w_width = self.width()
        w_height = self.height()
        if w_width <= 0 or w_height <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Скругленный контур карты
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, float(w_width), float(w_height), 12.0, 12.0)
        painter.setClipPath(clip)

        painter.fillRect(self.rect(), QColor("#2b2b2b"))

        if self.current_lat is not None and self.current_lon is not None:
            center_x, center_y = self._lat_lon_to_pixel(self.current_lat, self.current_lon)
        else:
            center_x = (self.center_tile_x + 0.5) * self.tile_size
            center_y = (self.center_tile_y + 0.5) * self.tile_size

        left = center_x - w_width / 2.0
        top = center_y - w_height / 2.0

        start_x = int(math.floor(left / self.tile_size))
        end_x = int(math.floor((left + w_width) / self.tile_size))
        start_y = int(math.floor(top / self.tile_size))
        end_y = int(math.floor((top + w_height) / self.tile_size))

        # 1. Отрисовка тайлов
        for tile_x in range(start_x, end_x + 1):
            for tile_y in range(start_y, end_y + 1):
                screen_x = (tile_x * self.tile_size) - left
                screen_y = (tile_y * self.tile_size) - top

                pix = self._get_tile_pixmap(self.zoom, tile_x, tile_y)
                if pix:
                    painter.drawPixmap(int(screen_x), int(screen_y), pix)
                else:
                    painter.fillRect(int(screen_x), int(screen_y),
                                     self.tile_size, self.tile_size,
                                     QColor(35, 35, 35))

        # 2. Отрисовка трека заезда через QPainterPath (быстро и без разрывов)
        if len(self.track_points) > 1:
            pen = QPen(QColor("#00aaff"), 4, Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)

            path = QPainterPath()
            first = True

            for lat, lon in self.track_points:
                px, py = self._lat_lon_to_pixel(lat, lon)
                pt_x = px - left
                pt_y = py - top

                if first:
                    path.moveTo(pt_x, pt_y)
                    first = False
                else:
                    path.lineTo(pt_x, pt_y)

            painter.drawPath(path)

        # 3. Маркер текущей позиции
        marker_lat = self.gps_lat if self.gps_lat is not None else self.current_lat
        marker_lon = self.gps_lon if self.gps_lon is not None else self.current_lon

        if marker_lat is not None and marker_lon is not None:
            gps_px, gps_py = self._lat_lon_to_pixel(marker_lat, marker_lon)
            marker_x = gps_px - left
            marker_y = gps_py - top

            if -20 <= marker_x <= w_width + 20 and -20 <= marker_y <= w_height + 20:
                # Внешний контур маркера
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.setBrush(QBrush(QColor("#ff3333")))
                painter.drawEllipse(QPointF(marker_x, marker_y), 7, 7)
        else:
            # Предупреждение о поиске GPS
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, 160)))
            painter.drawRoundedRect(10, 10, 160, 28, 6, 6)
            painter.setPen(QColor("#ffaa00"))
            painter.drawText(18, 29, "Поиск GPS сигнала...")

    # -------------------------------------------------------------------------
    # События мыши / тачскрина
    # -------------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.position()
            self._follow_gps = False

            if self.current_lat is not None and self.current_lon is not None:
                self._drag_center = self._lat_lon_to_pixel(self.current_lat, self.current_lon)
            else:
                self._drag_center = ((self.center_tile_x + 0.5) * self.tile_size,
                                     (self.center_tile_y + 0.5) * self.tile_size)

    def mouseMoveEvent(self, event):
        if self._dragging:
            pos = event.position()
            dx = pos.x() - self._drag_start.x()
            dy = pos.y() - self._drag_start.y()

            new_cx = self._drag_center[0] - dx
            new_cy = self._drag_center[1] - dy

            self.current_lat, self.current_lon = self._pixel_to_lat_lon(new_cx, new_cy)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0 and self.zoom < self.max_zoom:
            self.zoom += 1
        elif delta < 0 and self.zoom > self.min_zoom:
            self.zoom -= 1
        self.update()