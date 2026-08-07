import struct
import sys
import logging
from PyQt6.QtCore import QThread, pyqtSignal
try:
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib
    from ancs_client import AncsClient
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False
    AncsClient = None


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
        """Принудительно отключает текущее устройство и сбрасывает все связи."""
        if not HAS_DBUS:
            print("[BT] Сброс не поддерживается на Windows.")
            return False

        try:
            # 1. Принудительно отключаем текущее устройство
            if self.client and self.client.device_path:
                try:
                    dev_iface = dbus.Interface(
                        self.client.bus.get_object("org.bluez", self.client.device_path),
                        "org.bluez.Device1"
                    )
                    dev_iface.Disconnect()
                except Exception as e:
                    print(f"[BT] Не удалось отключить устройство напрямую: {e}")

            # 2. Удаляем все парные устройства
            import subprocess
            result = subprocess.run(["bluetoothctl", "paired-devices"], capture_output=True, text=True)
            lines = result.stdout.strip().split("\n")

            for line in lines:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "Device":
                    mac = parts[1]
                    subprocess.run(["bluetoothctl", "remove", mac])
                    print(f"[BT] Удалено из памяти: {mac}")

            self.status_changed.emit("Все связи сброшены. Включите поиск на iPhone")
            return True
        except Exception as e:
            print(f"[BT ERROR] Ошибка при очистке: {e}")
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