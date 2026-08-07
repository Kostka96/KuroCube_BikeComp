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
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QIcon, QFontDatabase, QFont

from T9Dialog import T9Dialog
from ui_utils import load_icon
from offline_map import OfflineMapWidget
from NotificationBanner import NotificationBanner
from BluetoothThread import BluetoothThread
import serial.tools.list_ports
# --- ГЛОБАЛЬНЫЕ ПУТИ ---
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SRC_DIR, ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
RESOURCES_DIR = os.path.join(BASE_DIR, "resources")
TILES_DIR = os.path.join(RESOURCES_DIR, "OpenStreetMap")


def load_custom_fonts():
    """Загружает все шрифты из папки resources/fonts/"""
    fonts_dir = os.path.join(RESOURCES_DIR, "fonts")
    loaded_fonts = {}

    if not os.path.exists(fonts_dir):
        print(f"Папка со шрифтами не найдена: {fonts_dir}")
        return loaded_fonts

    for file in os.listdir(fonts_dir):
        if file.endswith(('.ttf', '.otf')):
            font_path = os.path.join(fonts_dir, file)
            font_id = QFontDatabase.addApplicationFont(font_path)

            if font_id != -1:
                family = QFontDatabase.applicationFontFamilies(font_id)[0]
                key = os.path.splitext(file)[0]
                loaded_fonts[key] = family
                print(f"Загружен шрифт: {file} -> {family}")
            else:
                print(f"Ошибка загрузки шрифта: {file}")
    return loaded_fonts


# =========================================================
# СЕРВЕР ОФЛАЙН КАРТ
# =========================================================
class TileServer:
    def __init__(self, tiles_dir=TILES_DIR, port=8088):
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
def find_rp2040_port():
    """
    Автоматически ищет подключенный RP2040 (Raspberry Pi Pico) на Windows и Linux/Raspberry Pi.
    """
    # Расширенный список VID:PID для RP2040 (включая 2E8A:0003)
    RP2040_VID_PIDS = [
        (0x2E8A, 0x0003),  # Standard Pico CDC Serial
        (0x2E8A, 0x0005),  # Pico Bootloader/Serial
        (0x2E8A, 0x000A),  # RP2040 Dual Serial
        (0x2341, 0x005E),  # Arduino Nano RP2040
    ]

    ports = list(serial.tools.list_ports.comports())

    for port in ports:
        # 1. Точная проверка по VID и PID
        if (port.vid, port.pid) in RP2040_VID_PIDS:
            print(f"[SERIAL] Найден RP2040 по VID/PID ({port.vid:04X}:{port.pid:04X}): {port.device}")
            return port.device

        # 2. Проверка HWID строки на тот случай, если VID/PID не распарсились автоматически
        hwid = (port.hwid or "").upper()
        if "2E8A:0003" in hwid or "2E8A:" in hwid:
            print(f"[SERIAL] Найден RP2040 по HWID: {port.device}")
            return port.device

        # 3. Проверка по описанию устройства
        desc = (port.description or "").lower()
        manufacturer = (port.manufacturer or "").lower()
        if "rp2040" in desc or "pico" in desc or "rp2040" in manufacturer:
            print(f"[SERIAL] Найден RP2040 по описанию: {port.device}")
            return port.device

    # 4.Резервный вариант для Linux / Raspberry Pi OS
    for port in ports:
        if "ttyACM" in port.device or "ttyUSB" in port.device:
            print(f"[SERIAL] Найден резервный порт Linux: {port.device}")
            return port.device

    print("[SERIAL ERROR] Устройство RP2040 не найдено!")
    return None


class SerialThread(QThread):
    data_received = pyqtSignal(dict)

    def __init__(self, baudrate=115200):
        super().__init__()
        self.baudrate = baudrate
        self.running = True

    def run(self):
        while self.running:
            port_name = find_rp2040_port()

            if not port_name:
                self.msleep(2000)
                continue

            try:
                ser = serial.Serial(port_name, self.baudrate, timeout=1)
                ser.dtr = True
                ser.rts = True
                print(f"[SERIAL] Подключено к {port_name}")

                while self.running:
                    if ser.in_waiting > 0:
                        raw_line = ser.readline()
                        try:
                            line = raw_line.decode('utf-8', errors='ignore').strip()
                        except Exception:
                            continue

                        if line.startswith('{') and line.endswith('}'):
                            try:
                                data = json.loads(line)
                                self.data_received.emit(data)
                            except json.JSONDecodeError:
                                pass
                    else:
                        self.msleep(10)

            except (serial.SerialException, OSError) as e:
                print(f"[SERIAL ERROR] Потеря связи с {port_name}: {e}")
                self.msleep(2000)

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
        #self.showFullScreen()
        #self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self.unread_count = 0
        self.notifications_history = []
        # 1. Создаем виджет всплывающего уведомления
        self.banner = NotificationBanner(self)

        # 2. Запускаем Bluetooth Поток
        self.bt_thread = BluetoothThread()
        self.bt_thread.notification_received.connect(self.handle_new_notification)
        self.bt_thread.now_playing_changed.connect(self.update_media_widget)
        self.bt_thread.start()
        self.setup_bluetooth_ui()

        FONTS = load_custom_fonts()
        self.config_file = CONFIG_PATH
        self.stackedWidget.setCurrentIndex(0)

        # --- Состояние заезда ---
        self.is_recording = False
        self.trip_distance_km = 0.0
        self.trip_seconds = 0

        # --- Таймер секундомера ---
        self.track_timer = QTimer(self)
        self.track_timer.setInterval(1000)
        self.track_timer.timeout.connect(self.update_track_time)

        # --- Одометр ---
        self.last_raw_trip = None

        # --- 1. ЗАПУСК КАРТЫ И СЕРВЕРА ---
        self.tile_server = TileServer(tiles_dir=TILES_DIR, port=8088)
        self.tile_server.start()

        if hasattr(self, 'f_map'):
            if self.f_map.layout() is None:
                layout = QVBoxLayout(self.f_map)
                layout.setContentsMargins(0, 0, 0, 0)
                self.f_map.setLayout(layout)

            self.map_widget = OfflineMapWidget(tiles_dir=TILES_DIR, zoom=15, parent=self)
            self.f_map.layout().addWidget(self.map_widget)

        # --- 2. НАСТРОЙКИ И ЯЗЫКИ ---
        self.translations = {}
        self.current_lang = "en"
        self.current_unit = "metric"
        self.current_temp_unit = "celsius"

        self.load_settings()
        self.setup_settings_signals()
        self.load_language(self.current_lang)

        # Переключение экранов
        if hasattr(self, 'btn_settings'):
            self.btn_settings.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        if hasattr(self, 'btn_close_settings'):
            self.btn_close_settings.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        if hasattr(self, 'btn_back_to_main'):
            self.btn_back_to_main.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        if hasattr(self, 'btn_change_lang'):
            self.btn_change_lang.clicked.connect(self.on_lang_clicked)
        if hasattr(self, 'btn_settings_to_ui'):
            self.btn_settings_to_ui.clicked.connect(lambda: self.stackedWidget_2.setCurrentIndex(0))
        if hasattr(self, 'btn_settings_to_wifi'):
            self.btn_settings_to_wifi.clicked.connect(lambda: self.stackedWidget_2.setCurrentIndex(1))

        self.setup_track_buttons()
        button_icons = [
            (self.btn_play_pause_track, "pause", 24, 24, "#CCCCCC")]
        for widget, icon_name, w, h, color in button_icons:
            if hasattr(self, widget.objectName()):
                pixmap = load_icon(icon_name, w, h, color)
                widget.setIcon(QIcon(pixmap))
                widget.setIconSize(QSize(w, h))
        self.btn_map_zoom_plus.clicked.connect(self.map_widget.zoom_in)
        self.btn_map_zoom_minus.clicked.connect(self.map_widget.zoom_out)
        self.btn_map_to_me.clicked.connect(self.map_widget.center_on_gps)

        # --- 3. ПОТОК СЕРИАЛА ---
        self.serial_thread = SerialThread()
        self.serial_thread.data_received.connect(self.update_telemetry)
        self.serial_thread.start()

        # --- ИКОНКИ ---
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
            if hasattr(self, widget.objectName()):
                widget.setPixmap(load_icon(icon_name, w, h, color))

        button_icons = [
            (self.btn_message, "message", 24, 24, "#CCCCCC"),
            (self.btn_settings, "settings", 48, 48, "#CCCCCC"),
            (self.btn_play_pause_track, "start", 24, 24, "#CCCCCC"),
            (self.btn_stop_track, "stop", 24, 24, "#CCCCCC"),
            (self.btn_map_zoom_plus, "plus", 24, 24, "#CCCCCC"),
            (self.btn_map_zoom_minus, "minus", 24, 24, "#CCCCCC"),
            (self.btn_map_to_me, "metka_gps", 24, 24, "#CCCCCC"),
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
            if hasattr(self, widget.objectName()):
                pixmap = load_icon(icon_name, w, h, color)
                widget.setIcon(QIcon(pixmap))
                widget.setIconSize(QSize(w, h))

        # --- ШРИФТЫ ---
        if FONTS and "Roboto-Regular" in FONTS:
            family = FONTS["Roboto-Regular"]
            font_settings = [
                (self.lbl_clock, 18, QFont.Weight.Bold),
                (self.lbl_date, 12, QFont.Weight.Normal),
                (self.lbl_satellite, 18, QFont.Weight.Normal),
                (self.lbl_speed_text, 18, QFont.Weight.Normal),
                (self.lbl_speed_value, 100, QFont.Weight.Normal),
                (self.lbl_speed_unit, 24, QFont.Weight.Bold),
                (self.stat_avg_speed_text, 10, QFont.Weight.Normal),
                (self.stat_max_speed_text, 10, QFont.Weight.Normal),
                (self.stat_climb_text, 10, QFont.Weight.Normal),
                (self.stat_dist_trip_text, 10, QFont.Weight.Normal),
                (self.stat_dist_total_text, 10, QFont.Weight.Normal),
                (self.stat_pressure_text, 10, QFont.Weight.Normal),
                (self.stat_avg_speed, 16, QFont.Weight.Bold),
                (self.stat_max_speed, 16, QFont.Weight.Bold),
                (self.stat_climb, 16, QFont.Weight.Bold),
                (self.stat_dist_trip, 16, QFont.Weight.Bold),
                (self.stat_dist_total, 16, QFont.Weight.Bold),
                (self.stat_trip_time, 10, QFont.Weight.Bold),
                (self.stat_altitude, 16, QFont.Weight.Bold),
                (self.stat_temp, 16, QFont.Weight.Bold),
                (self.stat_avg_speed_unit, 16, QFont.Weight.Normal),
                (self.stat_climb_unit, 16, QFont.Weight.Normal),
                (self.stat_dist_trip_unit, 16, QFont.Weight.Normal),
                (self.stat_dist_total_unit, 16, QFont.Weight.Normal),
                (self.stat_altitude_unit, 16, QFont.Weight.Normal),
                (self.stat_temp_unit, 16, QFont.Weight.Normal),
                (self.lbl_track_time, 16, QFont.Weight.Bold),
                (self.lbl_current_time_music, 16, QFont.Weight.Normal),
                (self.lbl_music_name, 16, QFont.Weight.Normal),
                (self.lbl_max_time_music, 16, QFont.Weight.Normal),
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

            for widget, size, weight in font_settings:
                if hasattr(self, widget.objectName()):
                    widget.setFont(QFont(family, size, weight))

    def handle_new_notification(self, app_id, title, message, category):
        # Добавляем в историю
        notif_data = {"app": app_id, "title": title, "msg": message, "cat": category}
        self.notifications_history.append(notif_data)

        # Увеличиваем счетчик
        self.unread_count += 1
        self.update_message_badge()

        # Показываем всплывающий баннер
        display_title = title if title else app_id
        self.banner.show_notification(display_title, message)

    def update_message_badge(self):
        # Обновление текста на кнопке сообщений
        if self.unread_count > 0:
            self.btn_messages.setText(f"💬 ({self.unread_count})")
            self.btn_messages.setStyleSheet("color: #ff3333; font-weight: bold;")
        else:
            self.btn_messages.setText("💬")
            self.btn_messages.setStyleSheet("")

    def open_messages_screen(self):
        # При открытии списка сбрасываем счётчик
        self.unread_count = 0
        self.update_message_badge()
        # Показать QListWidget с self.notifications_history...

    def update_media_widget(self, now_playing: dict):
        """
        Принимает словарь с данными плеера от BluetoothThread
        Keys: player_name, state, artist, album, title, duration
        """
        artist = now_playing.get("artist", "")
        title = now_playing.get("title", "")
        state = now_playing.get("state", "")

        # Формируем строку для отображения
        if artist and title:
            track_info = f"{artist} — {title}"
        elif title:
            track_info = title
        else:
            track_info = "Нет трека"

        print(f"[MEDIA] State: {state} | {track_info}")

        # Обновляем QLabels интерфейса (подставьте имя вашего QLabel для плеера)
        if hasattr(self, 'lbl_track_title'):
            self.lbl_track_title.setText(track_info)

        if hasattr(self, 'btn_play_pause'):
            # Изменяем иконку/текст кнопки в зависимости от статуса
            if state == "playing":
                self.btn_play_pause.setText("⏸")
            else:
                self.btn_play_pause.setText("▶")

    def setup_bluetooth_ui(self):
        # 1. Привязываем сигнал обновления статуса к метке
        self.bt_thread.status_changed.connect(self.lbl_ble_status.setText)

        # 2. Переключатель Advertising (включение / выключение видимости)
        self.rb_ble_advertising.toggled.connect(self.on_ble_advertising_toggled)

        # 3. Кнопка «Забыть устройства»
        self.btn_forget_paired_devices.clicked.connect(self.on_forget_devices_clicked)

    def on_ble_advertising_toggled(self, checked: bool):
        if checked:
            self.lbl_ble_status.setText("Режим поиска (Advertising) включен")
            # Если поток ещё не запущен — запускаем
            if not self.bt_thread.isRunning():
                self.bt_thread.start()
        else:
            self.lbl_ble_status.setText("Bluetooth отключен")

    def on_forget_devices_clicked(self):
        # Вызываем очистку через поток
        success = self.bt_thread.forget_paired_devices()
        if success:
            self.lbl_ble_status.setText("Все связи сброшены. Готово к новой паре")

    def open_keyboard(self):
        dialog = T9Dialog(self, "Парк Горького")
        if dialog.exec() == T9Dialog.Accepted:
            entered_text = dialog.get_text()
            print(f"Пользователь ввел: {entered_text}")

    # =========================================================
    # НАСТРОЙКИ И ПЕРЕВОД
    # =========================================================
    def load_language(self, lang_code):
        self.current_lang = lang_code
        file_path = os.path.join(RESOURCES_DIR, "locales", f"{lang_code}.json")

        if not os.path.exists(file_path):
            print(f"Внимание: Файл перевода {file_path} не найден! Использую en.json.")
            file_path = os.path.join(RESOURCES_DIR, "locales", "en.json")

        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                self.translations = json.load(f)
        else:
            self.translations = {}

        self.apply_translations()
        self.save_settings()

    def load_settings(self):
        self.config = configparser.ConfigParser()

        if os.path.exists(self.config_file):
            self.config.read(self.config_file, encoding="utf-8")
            self.current_lang = self.config.get("Settings", "language", fallback="en")
            self.current_unit = self.config.get("Settings", "unit_system", fallback="metric")
            self.current_temp_unit = self.config.get("Settings", "temp_unit", fallback="celsius")
            try:
                self.total_distance_km = float(self.config.get("Settings", "total_distance", fallback="0.0"))
            except ValueError:
                self.total_distance_km = 0.0
        else:
            self.total_distance_km = 0.0
            self.save_settings()

    def save_settings(self):
        if not hasattr(self, 'config'):
            self.config = configparser.ConfigParser()

        if not self.config.has_section("Settings"):
            self.config.add_section("Settings")

        self.config.set("Settings", "language", getattr(self, 'current_lang', 'en'))
        self.config.set("Settings", "unit_system", getattr(self, 'current_unit', 'metric'))
        self.config.set("Settings", "temp_unit", getattr(self, 'current_temp_unit', 'celsius'))
        self.config.set("Settings", "total_distance", f"{getattr(self, 'total_distance_km', 0.0):.2f}")

        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                self.config.write(f)
        except Exception as e:
            print(f"Ошибка сохранения config.ini: {e}")

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

        # Элементы настроек
        if hasattr(self, 'lbl_change_lang'):
            self.lbl_change_lang.setText(self.translations.get("language", "Language"))
        if hasattr(self, 'btn_change_lang'):
            self.btn_change_lang.setText(self.translations.get("meta_language_name", "English"))
        if hasattr(self, 'lbl_change_unit_speed'):
            self.lbl_change_unit_speed.setText(self.translations.get("speed_text", "Speed"))
        if hasattr(self, 'btn_change_unit_speed'):
            speed_key = "speed_unit_imperial" if self.current_unit == "imperial" else "speed_unit_metric"
            self.btn_change_unit_speed.setText(self.translations.get(speed_key, "Km/H"))
        if hasattr(self, 'lbl_change_unit_distance'):
            self.lbl_change_unit_distance.setText(self.translations.get("distance", "Distance"))
        if hasattr(self, 'btn_change_unit_distance'):
            dist_key = "distance_unit_imperial" if self.current_unit == "imperial" else "distance_unit_metric"
            self.btn_change_unit_distance.setText(self.translations.get(dist_key, "Km"))
        if hasattr(self, 'lbl_change_unit_temp'):
            self.lbl_change_unit_temp.setText(self.translations.get("temperature", "Temperature"))
        if hasattr(self, 'btn_change_unit_temp'):
            temp_key = "temp_unit_imperial" if self.current_temp_unit == "fahrenheit" else "temp_unit_metric"
            self.btn_change_unit_temp.setText(self.translations.get(temp_key, "°C"))
        if hasattr(self, 'lbl_change_unit_time'):
            self.lbl_change_unit_time.setText(self.translations.get("time", "Time"))
        if hasattr(self, 'btn_change_unit_time'):
            time_key = "time_format_12" if getattr(self, 'current_time_format', '24h') == '12h' else "time_format_24"
            self.btn_change_unit_time.setText(self.translations.get(time_key, "24H"))
        if hasattr(self, 'lbl_change_unit_data'):
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

        temp_unit = self.translations.get("temp_unit_imperial",
                                          "°F") if self.current_temp_unit == "fahrenheit" else self.translations.get(
            "temp_unit_metric", "°C")
        if hasattr(self, 'lbl_temp_unit'): self.lbl_temp_unit.setText(temp_unit)

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
        locales_dir = os.path.join(RESOURCES_DIR, "locales")
        languages = []

        if os.path.exists(locales_dir):
            for file in sorted(os.listdir(locales_dir)):
                if file.endswith('.json'):
                    lang_code = os.path.splitext(file)[0]
                    file_path = os.path.join(locales_dir, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            lang_name = data.get("meta_language_name", lang_code.upper())
                            languages.append((lang_code, lang_name))
                    except Exception as e:
                        print(f"Ошибка чтения файла перевода {file}: {e}")

        return languages if languages else [("en", "English")]

    def on_lang_clicked(self):
        available_langs = self.get_available_languages()
        lang_codes = [lang[0] for lang in available_langs]

        try:
            current_index = lang_codes.index(self.current_lang)
            next_index = (current_index + 1) % len(lang_codes)
        except ValueError:
            next_index = 0

        self.load_language(lang_codes[next_index])

    def on_speed_unit_clicked(self):
        self.current_unit = "imperial" if self.current_unit == "metric" else "metric"
        self.apply_translations()
        self.save_settings()

    def on_distance_unit_clicked(self):
        self.current_unit = "imperial" if self.current_unit == "metric" else "metric"
        self.apply_translations()
        self.save_settings()

    def on_temp_unit_clicked(self):
        self.current_temp_unit = "fahrenheit" if self.current_temp_unit == "celsius" else "celsius"
        self.apply_translations()
        self.save_settings()

    def on_time_format_clicked(self):
        current_fmt = getattr(self, 'current_time_format', '24h')
        self.current_time_format = "12h" if current_fmt == "24h" else "24h"
        self.apply_translations()
        self.save_settings()

    def on_date_format_clicked(self):
        current_fmt = getattr(self, 'current_date_format', 'DMY')
        self.current_date_format = "MDY" if current_fmt == "DMY" else "DMY"
        self.apply_translations()
        self.save_settings()

    def setup_settings_signals(self):
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
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.track_timer.start()
            print("Заезд запущен (Старт / Запись GPS / Секундомер)")
        else:
            self.track_timer.stop()
            print("Заезд поставлен на паузу")

    def stop_recording(self):
        if self.is_recording or self.trip_seconds > 0 or self.trip_distance_km > 0:
            self.is_recording = False
            self.track_timer.stop()
            print(f"Заезд завершен! Время: {self.lbl_track_time.text()}, Дистанция: {self.trip_distance_km:.2f} км")

            self.trip_distance_km = 0.0
            self.trip_seconds = 0
            self.last_raw_trip = None

            if hasattr(self, 'lbl_track_time'):
                self.lbl_track_time.setText("00:00:00")
            if hasattr(self, 'stat_dist_trip'):
                self.stat_dist_trip.setText("0.0")

    def update_track_time(self):
        self.trip_seconds += 1
        hours = self.trip_seconds // 3600
        minutes = (self.trip_seconds % 3600) // 60
        seconds = self.trip_seconds % 60

        if hasattr(self, 'lbl_track_time'):
            self.lbl_track_time.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def get_gps_signal_color(self, sats, hdop=None):
        if sats >= 8 and (hdop is None or hdop <= 2.0):
            return "#55ff7f"
        elif 4 <= sats < 8:
            return "#ffaa00"
        else:
            return "#ff5555"

    # =========================================================
    # ОБРАБОТКА ДАННЫХ C RP2040
    # =========================================================
    def update_telemetry(self, data):
        # 1. Время и Дата
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

        # 2. GPS
        if 'gps' in data:
            sats = data['gps'].get('sats', 0)
            hdop = data['gps'].get('hdop', 99.0)
            color_hex = self.get_gps_signal_color(sats, hdop)

            if hasattr(self, 'lbl_satellite'):
                self.lbl_satellite.setText(str(sats))
                self.lbl_satellite.setStyleSheet(f"color: {color_hex};")

            if hasattr(self, 'lbl_satellite_icon'):
                self.lbl_satellite_icon.setPixmap(load_icon("satellite", 24, 24, color_hex))

            if 'lat' in data['gps'] and 'lon' in data['gps']:
                if hasattr(self, 'map_widget'):
                    self.map_widget.set_position(data['gps']['lat'], data['gps']['lon'], is_recording=self.is_recording)

        # 3. Скорость и Пробег
        if 'wheel' in data:
            raw_speed = data['wheel'].get('speed', 0)
            converted_speed = self.convert_speed(raw_speed)

            if hasattr(self, 'lbl_speed_value'):
                self.lbl_speed_value.setText(f"{converted_speed:.1f}")

            if 'trip' in data['wheel']:
                current_raw_trip = data['wheel']['trip']
                if self.last_raw_trip is None:
                    self.last_raw_trip = current_raw_trip

                delta = current_raw_trip - self.last_raw_trip
                self.last_raw_trip = current_raw_trip

                if delta > 0:
                    self.total_distance_km += delta
                    self.save_settings()

                    if self.is_recording:
                        self.trip_distance_km += delta

                if hasattr(self, 'stat_dist_trip'):
                    self.stat_dist_trip.setText(f"{self.convert_distance(self.trip_distance_km):.1f}")

                if hasattr(self, 'stat_dist_total'):
                    self.stat_dist_total.setText(f"{self.convert_distance(self.total_distance_km):.1f}")

        # 4. BMP280
        if 'bmp' in data:
            if 'temp' in data['bmp'] and hasattr(self, 'stat_temp'):
                self.stat_temp.setText(f"{self.convert_temperature(data['bmp']['temp']):.1f}")

            if 'alt' in data['bmp'] and hasattr(self, 'stat_altitude'):
                self.stat_altitude.setText(f"{int(data['bmp']['alt'])}")

            if 'press' in data['bmp'] and hasattr(self, 'lbl_press_val'):
                self.lbl_press_val.setText(f"{int(data['bmp']['press'])}")

        # 5. IMU / Уклон
        if 'imu' in data:
            ax = data['imu'].get('ax', 0)
            ay = data['imu'].get('ay', 0)
            az = data['imu'].get('az', 9.8)

            pitch_rad = math.atan2(ax, math.sqrt(ay ** 2 + az ** 2))
            incline_percent = math.tan(pitch_rad) * 100

            if hasattr(self, 'stat_climb'):
                self.stat_climb.setText(f"{incline_percent:.0f}")

    def closeEvent(self, event):
        self.serial_thread.stop()
        self.save_settings()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = BikeComputerWindow()
    window.show()
    sys.exit(app.exec())