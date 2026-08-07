import struct
import sys
import logging
from PyQt6.QtCore import QThread, pyqtSignal
import subprocess
from ancs_client import AncsClient
# Флаг доступности DBus (для работы на Linux / RPi)
try:
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib

    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False


class BluetoothThread(QThread):
    # Сигналы для PyQt UI
    notification_received = pyqtSignal(str, str, str, str)  # app_id, title, message, category
    now_playing_changed = pyqtSignal(dict)  # track info[cite: 3]
    status_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.client = None

    def forget_paired_devices(self):
        """Удаляет все привязанные Bluetooth-устройства на Raspberry Pi."""
        if not HAS_DBUS:
            print("[BT] Сброс устройств не поддерживается на Windows.")
            return False

        try:
            # Получаем список привязанных устройств
            result = subprocess.run(["bluetoothctl", "paired-devices"], capture_output=True, text=True)
            lines = result.stdout.strip().split("\n")

            for line in lines:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "Device":
                    mac = parts[1]
                    subprocess.run(["bluetoothctl", "remove", mac])
                    print(f"[BT] Удалено устройство: {mac}")

            self.status_changed.emit("История устройств очищена")
            return True
        except Exception as e:
            print(f"[BT ERROR] Ошибка при очистке устройств: {e}")
            return False

    def run(self):
        if not HAS_DBUS:
            print("[BT WARNING] dbus/GLib не найдены. Эмуляция на ПК.")
            return

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()

        # Импортируем классы из вашего ancs_client.py
        # В данном контексте привязываем коллбеки к сигналам PyQt:
        self.client = AncsClient(bus)

        # Переопределяем методы передачи данных в Qt
        def _on_notif(app_id, title, message, category):
            self.notification_received.emit(app_id, title, message, category)

        def _on_media(now_playing):
            self.now_playing_changed.emit(now_playing)

        # Подменяем обработчики[cite: 3]
        global on_notification, on_now_playing_changed
        on_notification = _on_notif
        on_now_playing_changed = _on_media

        try:
            self.client.start()
            loop = GLib.MainLoop()
            loop.run()
        except Exception as e:
            print(f"[BT ERROR] {e}")

    # Публичные методы для управления плеером из кнопок UI
    def play_pause(self):
        if self.client:
            self.client.toggle_play_pause()

    def next_track(self):
        if self.client:
            self.client.next_track()

    def prev_track(self):
        if self.client:
            self.client.previous_track()