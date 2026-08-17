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
    dbus = None
    GLib = None
    AncsClient = None

log = logging.getLogger("bt_thread")


class BluetoothThread(QThread):
    notification_received = pyqtSignal(str, str, str, str)
    now_playing_changed = pyqtSignal(dict)
    status_changed = pyqtSignal(str)
    connection_status = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.client = None
        self.loop = None

    def _on_notification(self, app_id, title, message, category):
        self.notification_received.emit(app_id, title, message, category)

    def _on_now_playing_changed(self, data):
        self.now_playing_changed.emit(data)

    def _on_connection_status_changed(self, connected, name):
        self.connection_status.emit(bool(connected), str(name))

    def forget_paired_devices(self) -> bool:
        """Отключает активные устройства, удаляет pairing и перезапускает BLE-адаптер."""
        if not HAS_DBUS:
            log.warning("Сброс устройств не поддерживается вне Linux / DBus")
            return False

        try:
            result = subprocess.run(
                ["bluetoothctl", "paired-devices"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                log.warning("bluetoothctl paired-devices failed: %s", result.stderr.strip())

            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) < 2 or parts[0] != "Device":
                    continue
                mac = parts[1]
                subprocess.run(["bluetoothctl", "disconnect", mac], check=False)
                subprocess.run(["bluetoothctl", "remove", mac], check=False)
                log.info("Устройство отключено и удалено: %s", mac)

            # Сохраняем исходную архитектуру проекта: hci0 используется явно.
            subprocess.run(["sudo", "hciconfig", "hci0", "down"], check=False)
            subprocess.run(["sudo", "hciconfig", "hci0", "up"], check=False)

            if self.client:
                try:
                    adapter_path = self.client.setup_adapter()
                    self.client.register_agent()
                    self.client.register_advertisement(adapter_path)
                except Exception as e:
                    log.warning("Ошибка перезапуска BLE после сброса: %s", e)

            self.status_changed.emit("Все устройства и соединения сброшены")
            return True
        except Exception as e:
            log.exception("Ошибка при жесткой очистке устройств: %s", e)
            return False

    def run(self):
        if not HAS_DBUS:
            log.warning("dbus/GLib не найдены. Эмуляция на ПК.")
            return

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        self.client = AncsClient(bus)

        # Callbacks принадлежат экземпляру AncsClient, поэтому глобальное
        # состояние модуля ancs_client больше не меняется.
        self.client.on_notification = self._on_notification
        self.client.on_now_playing_changed = self._on_now_playing_changed
        self.client.on_connection_status_changed = self._on_connection_status_changed

        try:
            self.client.start()
            self.loop = GLib.MainLoop()
            self.loop.run()
        except Exception as e:
            log.exception("Ошибка Bluetooth цикла: %s", e)
        finally:
            self.loop = None

    def stop(self):
        """Корректно останавливает GLib-цикл и ждёт завершения потока."""
        self.running = False
        if HAS_DBUS and self.loop is not None:
            GLib.idle_add(self.loop.quit)
        self.wait(3000)

    def play_pause(self):
        if self.client:
            self.client.toggle_play_pause()

    def next_track(self):
        if self.client:
            self.client.next_track()

    def prev_track(self):
        if self.client:
            self.client.previous_track()

    def volume_up(self):
        if self.client:
            self.client.volume_up()

    def volume_down(self):
        if self.client:
            self.client.volume_down()