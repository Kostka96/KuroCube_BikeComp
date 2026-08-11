import subprocess
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

log = logging.getLogger("bt_thread")

class BluetoothThread(QThread):
    notification_received = pyqtSignal(str, str, str, str)  # app_id, title, message, category
    now_playing_changed = pyqtSignal(dict)
    status_changed = pyqtSignal(str)
    connection_status = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.client = None
        self.loop = None

    def forget_paired_devices(self) -> bool:
        """Отключает активные устройства, удаляет их из сопряжённых и перезапускает BLE-адаптер."""
        if not HAS_DBUS:
            log.warning("Сброс устройств не поддерживается вне Linux / DBus")
            return False

        try:
            # 1. Получаем список всех сопряжённых устройств
            result = subprocess.run(["bluetoothctl", "paired-devices"], capture_output=True, text=True)
            lines = result.stdout.strip().split("\n")

            for line in lines:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "Device":
                    mac = parts[1]
                    # Принудительно разрываем активное соединение
                    subprocess.run(["bluetoothctl", "disconnect", mac], check=False)
                    # Удаляем из базы данных BlueZ
                    subprocess.run(["bluetoothctl", "remove", mac], check=False)
                    log.info("Устройство отключено и удалено: %s", mac)

            # 2. Перезагружаем физический Bluetooth-адаптер (разрывает любые повисшие BLE-сессии)
            subprocess.run(["sudo", "hciconfig", "hci0", "down"], check=False)
            subprocess.run(["sudo", "hciconfig", "hci0", "up"], check=False)

            # 3. Перезапускаем агент и видимость в ancs_client (если клиент запущен)
            if self.client:
                try:
                    adapter_path = self.client.setup_adapter()
                    self.client.register_advertisement(adapter_path)
                except Exception as e:
                    log.warning("Ошибка перезапуска рекламы BLE: %s", e)

            self.status_changed.emit("Все устройства и соединения сброшены")
            return True
        except Exception as e:
            log.error("Ошибка при жесткой очистке устройств: %s", e)
            return False

    def run(self):
        if not HAS_DBUS:
            log.warning("dbus/GLib не найдены. Эмуляция на ПК.")
            return

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()

        self.client = AncsClient(bus)

        # Перехват глобальных функций обратного вызова ancs_client
        import ancs_client
        ancs_client.on_notification = lambda app_id, title, msg, cat: self.notification_received.emit(app_id, title, msg, cat)
        ancs_client.on_now_playing_changed = lambda data: self.now_playing_changed.emit(data)
        ancs_client.on_connection_status_changed = lambda conn, name: self.connection_status.emit(conn, name)
        self.client.on_now_playing_changed = lambda data: self.now_playing_changed.emit(data)
        try:
            self.client.start()
            self.loop = GLib.MainLoop()
            self.loop.run()
        except Exception as e:
            log.error("Ошибка Bluetooth цикла: %s", e)

    def stop(self):
        """Корректно останавливает GLib-цикл и ждёт завершения потока."""
        self.running = False
        if HAS_DBUS and self.loop is not None:
            # quit() нужно вызывать из потока самого GLib-цикла, а не из GUI-потока —
            # планируем вызов через idle_add
            GLib.idle_add(self.loop.quit)
        self.wait(3000)

    def play_pause(self):
        if self.client: self.client.toggle_play_pause()

    def next_track(self):
        if self.client: self.client.next_track()

    def prev_track(self):
        if self.client: self.client.previous_track()

    def volume_up(self):
        if self.client:
            self.client.volume_up()

    def volume_down(self):
        if self.client:
            self.client.volume_down()