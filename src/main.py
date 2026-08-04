import os
import sys
import json
import serial
import math
import threading
import configparser
from http.server import SimpleHTTPRequestHandler, HTTPServer
from datetime import date, datetime
from PyQt6 import uic
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout
from PyQt6.QtCore import QThread, pyqtSignal, QUrl, Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QFontDatabase, QFont
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from T9Dialog import T9Dialog
from ui_utils import load_icon

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SRC_DIR, ".."))

CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
RESOURCES_DIR = os.path.join(BASE_DIR, "resources")

# --- ЗАГРУЗКА ШРИФТА ---
def load_custom_fonts():
    """
    Загружает все шрифты из папки resources/fonts/.
    Возвращает словарь: {'имя_файла_без_расширения': 'семейство_шрифта'}
    """
    fonts_dir = os.path.join(os.path.dirname(__file__), "..", "resources", "fonts")
    loaded_fonts = {}

    if not os.path.exists(fonts_dir):
        print(f"Папка со шрифтами не найдена: {fonts_dir}")
        return loaded_fonts

    for file in os.listdir(fonts_dir):
        if file.endswith(('.ttf', '.otf')):
            font_path = os.path.join(fonts_dir, file)
            font_id = QFontDatabase.addApplicationFont(font_path)

            if font_id != -1:
                # Получаем имя семейства (например, "Orbitron Bold")
                family = QFontDatabase.applicationFontFamilies(font_id)[0]
                # Берем имя файла без расширения для ключа (например, "Orbitron-Bold")
                key = os.path.splitext(file)[0]
                loaded_fonts[key] = family
                print(f"Загружен шрифт: {file} -> {family}")
            else:
                print(f"Ошибка загрузки шрифта: {file}")
    return loaded_fonts


# =========================================================
# СЕРВЕР ОФЛАЙН КАРТ (SimpleHTTPRequestHandler)
# =========================================================
class TileServer:
    def __init__(self, tiles_dir="../resources/OpenStreetMap", port=8088):
        self.tiles_dir = os.path.abspath(tiles_dir)
        self.port = port
        self.server = None

    def start(self):
        tiles_directory = self.tiles_dir

        class TileRequestHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=tiles_directory, **kwargs)

            def log_message(self, format, *args):
                pass  # Отключаем спам в консоль

        try:
            self.server = HTTPServer(('127.0.0.1', self.port), TileRequestHandler)
            thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            thread.start()
            print(f"Сервер карт запущен на http://127.0.0.1:{self.port} ({self.tiles_dir})")
        except Exception as e:
            print(f"Ошибка запуска сервера карт: {e}")


# =========================================================
# ФОНОВЫЙ ПОТОК ЧТЕНИЯ SERIAL / JSON
# =========================================================
class SerialThread(QThread):
    data_received = pyqtSignal(dict)

    def __init__(self, port='COM5', baudrate=115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = True

    def run(self):
        try:
            # Подключаемся к порту
            ser = serial.Serial(self.port, self.baudrate, timeout=1)

            # ВАЖНО: Активируем линии DTR и RTS для RP2040
            ser.dtr = True
            ser.rts = True

            print(f"Успешно подключено к Serial-порту: {self.port} (DTR/RTS set)")

            while self.running:
                if ser.in_waiting > 0:
                    # Читаем сырую строку
                    raw_line = ser.readline()
                    try:
                        line = raw_line.decode('utf-8', errors='ignore').strip()
                    except Exception as dec_err:
                        print(f"Ошибка декодирования: {dec_err}")
                        continue

                    # Выводим ВСЁ, что пришло в порт для отладки
                    #if line:
                        print(f"[RAW SERIAL]: {line}")

                    # Проверяем на JSON
                    if line.startswith('{') and line.endswith('}'):
                        try:
                            data = json.loads(line)
                            self.data_received.emit(data)
                        except json.JSONDecodeError as json_err:
                            print(f"Ошибка парсинга JSON: {json_err}")

        except Exception as e:
            print(f"Ошибка чтения Serial ({self.port}): {e}")

    def stop(self):
        self.running = False
        self.wait()


# =========================================================
# ГЛАВНОЕ ОКНО
# =========================================================
class BikeComputerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        ui_path = os.path.join(SRC_DIR, 'KuroCube_BikeComp_UI.ui')
        uic.loadUi(ui_path, self)
        FONTS = load_custom_fonts()
        self.config = configparser.ConfigParser()
        self.config_file = CONFIG_PATH
        self.stackedWidget.setCurrentIndex(0)
        self.LANG_OPTIONS = [('ru', 'Русский'), ('en', 'English')]
        self.SPEED_OPTIONS = [('metric', 'Км/ч'), ('imperial', 'Мили/ч')]
        self.TEMP_OPTIONS = [('celsius', '°C'), ('fahrenheit', '°F')]
        self.TIME_OPTIONS = [('24h', '24-часовой'), ('12h', '12-часовой')]
        self.DATE_OPTIONS = [('DMY', 'ДД.ММ.ГГГГ'), ('MDY', 'ММ/ДД/ГГГГ')]
        # --- Состояние заезда ---
        self.is_recording = False  # Запущен ли запись заезда/секундомер
        self.trip_distance_km = 0.0  # Дистанция текущего заезда (км)
        self.trip_seconds = 0  # Секунды секундомера

        # --- Таймер для секундомера ---
        self.track_timer = QTimer(self)
        self.track_timer.setInterval(1000)  # Раз в 1 секунду
        self.track_timer.timeout.connect(self.update_track_time)

        # --- Переменные для одометра ---
        self.last_raw_trip = None  # Чтобы считать дельту с RP2040
        # --- 1. ЗАПУСК КАРТЫ И СЕРВЕРА ---
        tiles_path = os.path.join(RESOURCES_DIR, "OpenStreetMap")
        self.tile_server = TileServer(tiles_dir=tiles_path, port=8088)
        self.tile_server.start()
        app.setStyle('Fusion')
        if hasattr(self, 'f_map'):
            if self.f_map.layout() is None:
                layout = QVBoxLayout(self.f_map)
                layout.setContentsMargins(0, 0, 0, 0)
                self.f_map.setLayout(layout)

            self.map_view = QWebEngineView()
            self.map_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

            # Настройки безопасности
            settings = self.map_view.page().settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

            self.f_map.layout().addWidget(self.map_view)

            html_path = os.path.join(tiles_path, "map_offline.html")
            self.map_view.load(QUrl.fromLocalFile(html_path))

        # --- 2. НАСТРОЙКИ И ЯЗЫКИ ---
        self.translations = {}
        self.current_lang = "en"
        self.current_unit = "metric"
        self.current_temp_unit = "celsius"

        self.load_settings()
        self.setup_settings_signals()
        if hasattr(self, 'frame_settings'):
            self.frame_settings.hide()
        self.load_language(self.current_lang)

        if hasattr(self, 'btn_settings'):
            self.btn_settings.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        if hasattr(self, 'btn_close_settings'):
            self.btn_close_settings.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))

        self.btn_back_to_main.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        if hasattr(self, 'btn_change_lang'):
            self.btn_change_lang.clicked.connect(self.on_lang_clicked)
        # --- 3. ПОТОК СЕРИАЛА ---
        self.serial_thread = SerialThread(port='COM5')  # Проверь имя порта
        self.serial_thread.data_received.connect(self.update_telemetry)
        self.serial_thread.start()

        label_icons = [
            (self.lbl_satellite_icon, "satellite", 24, 24, "#55ff7f"),
            (self.stat_avg_speed_icon, "average", 24, 24, "#CCCCCC"),
            (self.stat_max_speed_icon, "max", 24, 24, "#CCCCCC"),
            (self.stat_climb_icon, "climb", 24, 24, "#CCCCCC"),
            (self.stat_dist_trip_icon, "distance_trip", 24, 24, "#CCCCCC"),
            (self.stat_dist_total_icon, "distance_total", 24, 24, "#CCCCCC"),
            (self.stat_trip_icon, "time-distance", 24, 24, "#CCCCCC"),
            (self.stat_altitude_icon, "altitude", 24, 24, "#CCCCCC"),
            (self.stat_pressure_icon, "pressure", 24, 24, "#CCCCCC"),
            (self.stat_temp_icon, "temp", 24, 24, "#CCCCCC"),
        ]
        for widget, icon_name, w, h, color in label_icons:
            widget.setPixmap(load_icon(icon_name, w, h, color))

        button_icons = [
            (self.btn_message, "message", 24, 24, "#CCCCCC"),
            (self.btn_settings, "settings", 48, 48, "#CCCCCC"),
            (self.btn_play_pause_track, "start", 24, 24, "#CCCCCC"),
            (self.btn_stop_track, "stop", 24, 24, "#CCCCCC"),
            (self.btn_prev, "player_back", 24, 24, "#CCCCCC"),
            (self.btn_pause_player, "player_play", 24, 24, "#CCCCCC"),
            (self.btn_next, "player_forward", 24, 24, "#CCCCCC"),
            (self.btn_volume_plus, "volume-plus", 36, 36, "#CCCCCC"),
            (self.btn_volume_minus, "volume-minus", 36, 36, "#CCCCCC"),
            (self.btn_back_to_main, "btn_back", 36, 36, "#CCCCCC"),
            (self.btn_settings_to_ui, "globus", 36, 36, "#CCCCCC"),
            (self.btn_settings_to_wifi, "wifi", 36, 36, "#CCCCCC"),
        ]
        for widget, icon_name, w, h, color in button_icons:
            pixmap = load_icon(icon_name, w, h, color)
            widget.setIcon(QIcon(pixmap))
            widget.setIconSize(QSize(w, h))
            # Применяем шрифт только если он успешно загружен

        # Убедитесь, что FONTS загружен и в нем есть ключ "Roboto"
        if FONTS and "Roboto-Regular" in FONTS:
            family = FONTS["Roboto-Regular"]  # Получаем имя семейства (например, "Roboto")

            # Список: (Виджет, Размер, Вес/Жирность)
            font_settings = [
                # --- Верхняя панель ---
                (self.lbl_clock, 18, QFont.Weight.Bold),
                (self.lbl_date, 12, QFont.Weight.Normal),
                (self.lbl_satellite, 18, QFont.Weight.Normal),

                # --- Скорость ---
                (self.lbl_speed_text, 18, QFont.Weight.Normal),
                (self.lbl_speed_value, 100, QFont.Weight.Normal),
                (self.lbl_speed_unit, 24, QFont.Weight.Bold),

                # --- Статистика: Заголовки (Текст) ---
                (self.stat_avg_speed_text, 10, QFont.Weight.Normal),
                (self.stat_max_speed_text, 10, QFont.Weight.Normal),
                (self.stat_climb_text, 10, QFont.Weight.Normal),
                (self.stat_dist_trip_text, 10, QFont.Weight.Normal),
                (self.stat_dist_total_text, 10, QFont.Weight.Normal),
                (self.stat_pressure_text, 10, QFont.Weight.Normal),

                # --- Статистика: Значения (Цифры) ---
                (self.stat_avg_speed, 16, QFont.Weight.Bold),
                (self.stat_max_speed, 16, QFont.Weight.Bold),
                (self.stat_climb, 16, QFont.Weight.Bold),
                (self.stat_dist_trip, 16, QFont.Weight.Bold),
                (self.stat_dist_total, 16, QFont.Weight.Bold),
                (self.stat_trip_time, 10, QFont.Weight.Bold),
                (self.stat_altitude, 16, QFont.Weight.Bold),
                (self.stat_temp, 16, QFont.Weight.Bold),

                # --- Статистика: Единицы измерения ---
                (self.stat_avg_speed_unit, 16, QFont.Weight.Normal),
                (self.stat_climb_unit, 16, QFont.Weight.Normal),
                (self.stat_dist_trip_unit, 16, QFont.Weight.Normal),
                (self.stat_dist_total_unit, 16, QFont.Weight.Normal),
                (self.stat_altitude_unit, 16, QFont.Weight.Normal),
                (self.stat_temp_unit, 16, QFont.Weight.Normal),

                # --- Трек и Музыка ---
                (self.lbl_track_time, 16, QFont.Weight.Bold),
                (self.lbl_current_time_music, 16, QFont.Weight.Normal),
                (self.lbl_music_name, 16, QFont.Weight.Normal),
                (self.lbl_max_time_music, 16, QFont.Weight.Normal),

                # --- Настройки: Интерфейс ---
                (self.lbl_change_lang, 16, QFont.Weight.Normal),
                (self.btn_change_lang, 16, QFont.Weight.Normal),
                (self.lbl_change_unit_speed, 16, QFont.Weight.Normal),
                (self.btn_change_unit_speed, 16, QFont.Weight.Normal),
                (self.lbl_change_unit_distance, 15, QFont.Weight.Normal),
                (self.btn_change_unit_distance, 16, QFont.Weight.Normal),
                (self.lbl_change_unit_temp, 13, QFont.Weight.Normal),
                (self.btn_change_unit_temp, 16, QFont.Weight.Normal),
                (self.lbl_change_unit_time, 16, QFont.Weight.Normal),
                (self.btn_change_unit_time, 16, QFont.Weight.Normal),
                (self.lbl_change_unit_data, 16, QFont.Weight.Normal),
                (self.btn_change_unit_data, 14, QFont.Weight.Normal),


            ]

            # --- Применяем одним циклом ---
            for widget, size, weight in font_settings:
                widget.setFont(QFont(family, size, weight))





    # =========================================================
    # ГРАФИКА И ИКОНКИ (SVG)
    # =========================================================
    def open_keyboard(self):
        # Создаем диалог, передаем текущий текст (если есть)
        dialog = T9Dialog(self, "Парк Горького")

        # Показываем и ждем ответа. dialog.exec() вернет QDialog.Rejected или QDialog.Accepted
        if dialog.exec() == T9Dialog.Accepted:
            # Пользователь нажал "Готово"
            entered_text = dialog.get_text()
            print(f"Пользователь ввел: {entered_text}")
            # Здесь вы можете записать этот текст в нужное место (например, в name маршрута)
            # self.lbl_route_name.setText(entered_text)

    # =========================================================
    # МЕТОДЫ НАСТРОЕК И ПЕРЕВОДА
    # =========================================================

    def load_language(self, lang_code):
        self.current_lang = lang_code
        file_path = os.path.join(os.path.dirname(__file__), "../resources/locales", f"{lang_code}.json")

        if not os.path.exists(file_path):
            print(f"Внимание: Файл перевода {file_path} не найден! Использую английский (en).")
            fallback_path = os.path.join(os.path.dirname(__file__), "locales", "en.json")
            if os.path.exists(fallback_path):
                with open(fallback_path, "r", encoding="utf-8") as f:
                    self.translations = json.load(f)
            else:
                self.translations = {}
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                self.translations = json.load(f)

        self.apply_translations()
        self.save_settings()

    def load_settings(self):
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
            self.current_lang = self.config.get("Settings", "language", fallback="en")
            self.current_unit = self.config.get("Settings", "unit_system", fallback="metric")
            self.current_temp_unit = self.config.get("Settings", "temp_unit", fallback="celsius")
            self.current_time_format = self.config.get("Settings", "time_format", fallback="24h")
            self.current_date_format = self.config.get("Settings", "date_format", fallback="DMY")
            self.total_distance_km = float(self.config.get("Settings", "total_distance", fallback="0.0"))
        else:
            self.save_settings()

    def save_settings(self):
        if not hasattr(self, 'config'):
            return
        self.config["Settings"]["total_distance"] = f"{self.total_distance_km:.2f}"
        self.config["Settings"] = {
            "language": self.current_lang,
            "unit_system": self.current_unit,
            "temp_unit": self.current_temp_unit,
            "time_format": getattr(self, 'current_time_format', '24h'),
            "date_format": getattr(self, 'current_date_format', 'DMY'),
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            self.config.write(f)

    def set_unit_system(self, unit_system):
        self.current_unit = unit_system
        self.apply_unit_system()
        self.save_settings()

    def apply_translations(self):
        if hasattr(self, 'lbl_speed_text'):
            self.lbl_speed_text.setText(self.translations.get("speed_text", "SPEED"))
        if hasattr(self, 'stat_avg_speed_text'):
            self.stat_avg_speed_text.setText(self.translations.get("average_speed", "Average"))
        if hasattr(self, 'stat_max_speed_text'):
            self.stat_max_speed_text.setText(self.translations.get("max_speed", "Max"))
        if hasattr(self, 'stat_climb_text'):
            self.stat_climb_text.setText(self.translations.get("climb", "Climb"))

        if hasattr(self, 'stat_dist_trip_text'):
            self.stat_dist_trip_text.setText(self.translations.get("trip_distance", "Trip distance"))
        if hasattr(self, 'stat_dist_total_text'):
            self.stat_dist_total_text.setText(self.translations.get("total_distance", "Total distance"))
        if hasattr(self, 'stat_trip_time'):
            self.stat_trip_time.setText(self.translations.get("trip_time", "Time move"))
        if hasattr(self, 'stat_temp_unit'):
            temp_key = "temp_unit_imperial" if self.current_temp_unit == "fahrenheit" else "temp_unit_metric"
            self.stat_temp_unit.setText(self.translations.get(temp_key, "°C"))

        # --- ПЛИТКА 1: ЯЗЫК ---
        if hasattr(self, 'lbl_change_lang'):
            self.lbl_change_lang.setText(self.translations.get("language", "Language"))
        if hasattr(self, 'btn_change_lang'):
            self.btn_change_lang.setText(self.translations.get("meta_language_name", "English"))

        # --- ПЛИТКА 2: СКОРОСТЬ ---
        if hasattr(self, 'lbl_change_unit_speed'):
            self.lbl_change_unit_speed.setText(self.translations.get("speed_text", "Speed"))
        if hasattr(self, 'btn_change_unit_speed'):
            speed_key = "speed_unit_imperial" if self.current_unit == "imperial" else "speed_unit_metric"
            self.btn_change_unit_speed.setText(self.translations.get(speed_key, "Km/H"))

        # --- ПЛИТКА 3: РАССТОЯНИЕ ---
        if hasattr(self, 'lbl_change_unit_distance'):
            self.lbl_change_unit_distance.setText(self.translations.get("distance", "Distance"))
        if hasattr(self, 'btn_change_unit_distance'):
            dist_key = "distance_unit_imperial" if self.current_unit == "imperial" else "distance_unit_metric"
            self.btn_change_unit_distance.setText(self.translations.get(dist_key, "Km"))

        # --- ПЛИТКА 4: ТЕМПЕРАТУРА ---
        if hasattr(self, 'lbl_change_unit_temp'):
            self.lbl_change_unit_temp.setText(self.translations.get("temperature", "Temperature"))
        if hasattr(self, 'btn_change_unit_temp'):
            temp_key = "temp_unit_imperial" if self.current_temp_unit == "fahrenheit" else "temp_unit_metric"
            self.btn_change_unit_temp.setText(self.translations.get(temp_key, "°C"))

        # --- ПЛИТКА 5: ВРЕМЯ (24H / 12H) ---
        if hasattr(self, 'lbl_change_unit_time'):
            self.lbl_change_unit_time.setText(self.translations.get("time", "Time"))
        if hasattr(self, 'btn_change_unit_time'):
            time_key = "time_format_12" if getattr(self, 'current_time_format',
                                                   '24h') == '12h' else "time_format_24"
            self.btn_change_unit_time.setText(self.translations.get(time_key, "24H"))

        # --- ПЛИТКА 6: ДАТА ---
        if hasattr(self, 'lbl_change_unit_data'):
            # Иправлено: берем "date" вместо "distance"
            self.lbl_change_unit_data.setText(self.translations.get("date", "Date"))
        if hasattr(self, 'btn_change_unit_data'):
            date_key = "date_format_MM.DD.YYYY" if getattr(self, 'current_date_format',
                                                           'DMY') == 'MDY' else "date_format_DD.MM.YYYY"
            self.btn_change_unit_data.setText(self.translations.get(date_key, "DD.MM.YYYY"))

        self.apply_unit_system()

        if hasattr(self, 'last_gps_date'):
            self.lbl_date.setText(self.format_date(self.last_gps_date))

    def apply_unit_system(self):
        if self.current_unit == "imperial":
            speed_unit = self.translations.get("speed_unit_imperial", "mi/h")
            distance_unit = self.translations.get("distance_unit_imperial", "mi")
            alt_unit = self.translations.get("altitude_unit_imperial", "ft")
        else:
            speed_unit = self.translations.get("speed_unit_metric", "km/h")
            distance_unit = self.translations.get("distance_unit_metric", "km")
            alt_unit = self.translations.get("altitude_unit_metric", "m")

        if hasattr(self, 'lbl_speed_unit'): self.lbl_speed_unit.setText(speed_unit)
        if hasattr(self, 'stat_avg_speed_unit'): self.stat_avg_speed_unit.setText(speed_unit)
        if hasattr(self, 'stat_max_speed_unit'): self.stat_max_speed_unit.setText(speed_unit)

        if hasattr(self, 'stat_dist_trip_unit'): self.stat_dist_trip_unit.setText(distance_unit)
        if hasattr(self, 'stat_dist_total_unit'): self.stat_dist_total_unit.setText(distance_unit)
        if hasattr(self, 'lbl_alt_unit'): self.lbl_alt_unit.setText(alt_unit)

        if self.current_temp_unit == "fahrenheit":
            temp_unit = self.translations.get("temp_unit_imperial", "°F")
        else:
            temp_unit = self.translations.get("temp_unit_metric", "°C")

        if hasattr(self, 'lbl_temp_unit'): self.lbl_temp_unit.setText(temp_unit)

    def toggle_settings(self):
        self.stackedWidget.setCurrentIndex(1)

    def format_date(self, dt_object: date) -> str:
        months_list = self.translations.get("months", [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ])

        date_format = self.translations.get("date_format", "%d %B %Y")
        temp_str = dt_object.strftime("%d %m %Y")
        parts = temp_str.split()
        month_index = int(parts[1]) - 1

        formatted_month = months_list[month_index] if 0 <= month_index < len(months_list) else "???"
        return dt_object.strftime(date_format.replace("%B", formatted_month))

    def convert_speed(self, speed_kmh):
        return speed_kmh * 0.621371 if self.current_unit == "imperial" else speed_kmh

    def convert_distance(self, dist_km):
        return dist_km * 0.621371 if self.current_unit == "imperial" else dist_km

    def convert_altitude(self, alt_m):
        return alt_m * 3.28084 if self.current_unit == "imperial" else alt_m

    def convert_temperature(self, temp_c):
        return (temp_c * 9 / 5) + 32 if self.current_temp_unit == "fahrenheit" else temp_c

    def get_available_languages(self):
        """
        Сканирует папку resources/locales и возвращает список кортежей:
        [('en', 'English'), ('ru', 'Русский'), ...]
        """
        locales_dir = os.path.join(BASE_DIR, "resources", "locales")
        languages = []

        if os.path.exists(locales_dir):
            for file in sorted(os.listdir(locales_dir)):
                if file.endswith('.json'):
                    lang_code = os.path.splitext(file)[0]  # Получаем 'en', 'ru' и т.д.
                    file_path = os.path.join(locales_dir, file)

                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            # Берем мета-имя из файла или код языка как фоллбэк
                            lang_name = data.get("meta_language_name", lang_code.upper())
                            languages.append((lang_code, lang_name))
                    except Exception as e:
                        print(f"Ошибка чтения файла перевода {file}: {e}")

        # Если папка пуста или файлы не найдены
        if not languages:
            languages = [("en", "English")]

        return languages

    def on_lang_clicked(self):
        """Переключает язык на следующий из доступных по кругу."""
        available_langs = self.get_available_languages()

        # Извлекаем список кодов ['en', 'ru', ...]
        lang_codes = [lang[0] for lang in available_langs]

        # Находим индекс текущего языка
        try:
            current_index = lang_codes.index(self.current_lang)
            next_index = (current_index + 1) % len(lang_codes)
        except ValueError:
            next_index = 0

        # Берем новый код языка
        next_lang_code = lang_codes[next_index]

        # Загружаем новый язык (этот метод у тебя уже есть, он сам вызовет apply_translations и save_settings)
        self.load_language(next_lang_code)

    # --- 1. СКОРОСТЬ (Км/ч <-> Mi/H) ---
    def on_speed_unit_clicked(self):
        """Переключает систему измерения скорости."""
        self.current_unit = "imperial" if self.current_unit == "metric" else "metric"
        self.apply_translations()
        self.save_settings()

    # --- 2. РАССТОЯНИЕ (Км <-> Mi) ---
    def on_distance_unit_clicked(self):
        """Связано с общей системой единиц (metric / imperial)."""
        # Обычно расстояние и скорость переключаются вместе,
        # но если нужно менять только систему единиц — дергаем ту же логику
        self.current_unit = "imperial" if self.current_unit == "metric" else "metric"
        self.apply_translations()
        self.save_settings()

    # --- 3. ТЕМПЕРАТУРА (°C <-> °F) ---
    def on_temp_unit_clicked(self):
        """Переключает шкалу температуры."""
        self.current_temp_unit = "fahrenheit" if self.current_temp_unit == "celsius" else "celsius"
        self.apply_translations()
        self.save_settings()

    # --- 4. ВРЕМЯ (24H <-> 12H) ---
    def on_time_format_clicked(self):
        """Переключает формат времени."""
        current_fmt = getattr(self, 'current_time_format', '24h')
        self.current_time_format = "12h" if current_fmt == "24h" else "24h"
        self.apply_translations()
        self.save_settings()

    # --- 5. ДАТА (DD.MM.YYYY <-> MM.DD.YYYY) ---
    def on_date_format_clicked(self):
        """Переключает формат отображения даты."""
        current_fmt = getattr(self, 'current_date_format', 'DMY')
        self.current_date_format = "MDY" if current_fmt == "DMY" else "DMY"
        self.apply_translations()
        self.save_settings()

    def setup_settings_signals(self):
        """Подключение всех кнопок плиток к их обработчикам."""
        if hasattr(self, 'btn_change_unit_speed'):
            self.btn_change_unit_speed.clicked.connect(self.on_speed_unit_clicked)

        if hasattr(self, 'btn_change_unit_distance'):
            self.btn_change_unit_distance.clicked.connect(self.on_distance_unit_clicked)

        if hasattr(self, 'btn_change_unit_temp'):
            self.btn_change_unit_temp.clicked.connect(self.on_temp_unit_clicked)

        if hasattr(self, 'btn_change_unit_time'):
            self.btn_change_unit_time.clicked.connect(self.on_time_format_clicked)

        if hasattr(self, 'btn_change_unit_data'):
            self.btn_change_unit_data.clicked.connect(self.on_date_format_clicked)

    def setup_track_buttons(self):
        if hasattr(self, 'btn_play_pause_track'):
            self.btn_play_pause_track.clicked.connect(self.toggle_recording)
        if hasattr(self, 'btn_stop_track'):
            self.btn_stop_track.clicked.connect(self.stop_recording)

    def toggle_recording(self):
        """Старт / Пауза заезда"""
        self.is_recording = not self.is_recording

        if self.is_recording:
            # Запуск/Возобновление
            self.track_timer.start()
            print("Заезд запущен (Старт / Запись GPS / Секундомер)")
            # Сюда позже добавим смену иконки кнопки на "Pause"
        else:
            # Пауза
            self.track_timer.stop()
            print("Заезд поставлен на паузу")
            # Сюда позже добавим смену иконки кнопки на "Play"

    def stop_recording(self):
        """Остановка и финализация заезда"""
        if self.is_recording or self.trip_seconds > 0 or self.trip_distance_km > 0:
            self.is_recording = False
            self.track_timer.stop()

            print(f"Заезд завершен! Время: {self.lbl_track_time.text()}, Дистанция: {self.trip_distance_km:.2f} км")

            # TODO: Позже здесь сформируем файл трека (.gpx или .json) из даты и времени

            # Сброс локального счетчика заезда
            self.trip_distance_km = 0.0
            self.trip_seconds = 0
            self.last_raw_trip = None

            # Обновляем интерфейс
            if hasattr(self, 'lbl_track_time'):
                self.lbl_track_time.setText("00:00:00")
            if hasattr(self, 'stat_dist_trip'):
                self.stat_dist_trip.setText("0.0")

    def update_track_time(self):
        """Тикает раз в секунду при активном заезде"""
        self.trip_seconds += 1

        # Форматируем секунды в HH:MM:SS
        hours = self.trip_seconds // 3600
        minutes = (self.trip_seconds % 3600) // 60
        seconds = self.trip_seconds % 60

        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        if hasattr(self, 'lbl_track_time'):
            self.lbl_track_time.setText(time_str)

    def get_gps_signal_color(self, sats, hdop=None):
        """
        Возвращает HEX-цвет в зависимости от качества сигнала GPS.
        """
        if sats >= 8 and (hdop is None or hdop <= 2.0):
            return "#55ff7f"  # Отличный фикс (Твой зеленый)
        elif 4 <= sats < 8:
            return "#ffaa00"  # Средняя точность (Оранжевый / Желтый)
        else:
            return "#ff5555"  # Поиски / Слабый сигнал (Красный)
    # =========================================================
    # ОБРАБОТКА ДАННЫХ C RP2040
    # =========================================================
    def update_telemetry(self, data):
        # 1. Время и Дата из JSON
        if 'time' in data and hasattr(self, 'lbl_clock'):
            self.lbl_clock.setText(data['time'])

        if 'date' in data and data['date'] != "N/A":
            try:
                dt = datetime.strptime(data['date'], "%d.%m.%Y").date()
                if not hasattr(self, 'last_gps_date') or self.last_gps_date != dt:
                    self.last_gps_date = dt
                    if hasattr(self, 'lbl_date'):
                        self.lbl_date.setText(self.format_date(self.last_gps_date))
            except ValueError:
                pass

        # 2. GPS: Спутники + Динамическая подсветка точности
        if 'gps' in data:
            sats = data['gps'].get('sats', 0)
            hdop = data['gps'].get('hdop', 99.0)

            # Вычисляем цвет
            color_hex = self.get_gps_signal_color(sats, hdop)

            # Обновляем число спутников и его цвет
            if hasattr(self, 'lbl_satellite'):
                self.lbl_satellite.setText(str(sats))
                self.lbl_satellite.setStyleSheet(f"color: {color_hex};")

            # Обновляем цвет иконки
            if hasattr(self, 'lbl_satellite_icon'):
                #self.lbl_satellite_icon.setStyleSheet(f"color: {color_hex};")
                label_icons = [
                    (self.lbl_satellite_icon, "satellite", 24, 24, f"{color_hex}")
                ]
                for widget, icon_name, w, h, color in label_icons:
                    widget.setPixmap(load_icon(icon_name, w, h, color))
            # Если есть координаты — двигаем маркер на карте
            if 'lat' in data['gps'] and 'lon' in data['gps']:
                lat = data['gps']['lat']
                lon = data['gps']['lon']
                if hasattr(self, 'map_view'):
                    self.map_view.page().runJavaScript(f"updatePosition({lat}, {lon});")

        # 3. Скорость и Пробег (Датчик Холла)
        if 'wheel' in data:
            raw_speed = data['wheel'].get('speed', 0)
            converted_speed = self.convert_speed(raw_speed)

            # Текущая скорость показывается всегда
            if hasattr(self, 'lbl_speed_value'):
                self.lbl_speed_value.setText(f"{converted_speed:.1f}")

            # Обработка дистанции из пакета RP2040
            if 'trip' in data['wheel']:
                current_raw_trip = data['wheel']['trip']

                # Инициализируем стартовое значение
                if self.last_raw_trip is None:
                    self.last_raw_trip = current_raw_trip

                # Вычисляем прирост дистанции между пакетами
                delta = current_raw_trip - self.last_raw_trip
                self.last_raw_trip = current_raw_trip

                if delta > 0:
                    # 1. ОБЩИЙ ПРОБЕГ (ODO): Растет ВСЕГДА при движении колеса
                    self.total_distance_km += delta
                    self.save_settings()  # Сохраняем свежий одометр в config.ini

                    # 2. ПРОБЕГ ЗА ПОЕЗДКУ (Trip): Растет ТОЛЬКО при записи заезда
                    if self.is_recording:
                        self.trip_distance_km += delta

                # Выводим Trip (Пробег текущей записи)
                if hasattr(self, 'stat_dist_trip'):
                    trip_dist = self.convert_distance(self.trip_distance_km)
                    self.stat_dist_trip.setText(f"{trip_dist:.1f}")

                # Выводим ODO (Общий одометр из config.ini)
                if hasattr(self, 'stat_dist_total'):
                    total_dist = self.convert_distance(self.total_distance_km)
                    self.stat_dist_total.setText(f"{total_dist:.1f}")

            # 4. Барометр и Высота (BMP280) — высота всегда в метрах
            if 'bmp' in data:
                if 'temp' in data['bmp'] and hasattr(self, 'stat_temp'):
                    temp = self.convert_temperature(data['bmp']['temp'])
                    self.stat_temp.setText(f"{temp:.1f}")

                if 'alt' in data['bmp'] and hasattr(self, 'stat_altitude'):
                    raw_alt_m = data['bmp']['alt']
                    self.stat_altitude.setText(f"{int(raw_alt_m)}")

                if 'press' in data['bmp'] and hasattr(self, 'lbl_press_val'):
                    self.lbl_press_val.setText(f"{int(data['bmp']['press'])}")

        # 5. Акселерометр (Расчет Уклона / Climb %)
        if 'imu' in data:
            ax = data['imu'].get('ax', 0)
            ay = data['imu'].get('ay', 0)
            az = data['imu'].get('az', 9.8)

            # Расчет тангажа (Pitch angle в градусах)
            pitch_rad = math.atan2(ax, math.sqrt(ay ** 2 + az ** 2))
            pitch_deg = math.degrees(pitch_rad)

            # Перевод в процент уклона (Grade %)
            incline_percent = math.tan(pitch_rad) * 100

            if hasattr(self, 'stat_climb'):
                self.stat_climb.setText(f"{incline_percent:.1f}")

    def closeEvent(self, event):
        self.serial_thread.stop()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = BikeComputerWindow()
    window.show()
    sys.exit(app.exec())