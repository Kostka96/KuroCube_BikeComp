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
    # Сигнал принимает 5 параметров, включая int uid
    notification_received = pyqtSignal(str, str, str, str, int)  # app_id, title, message, category, uid
    now_playing_changed = pyqtSignal(dict)
    status_changed = pyqtSignal(str)
    connection_status = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.client = None
        self.loop = None

    def _on_notification(self, app_id, title, message, category, uid=0):
        """Перехватывает уведомление от AncsClient и пробрасывает его в Qt-сигнал."""
        self.notification_received.emit(app_id, title, message, category, int(uid or 0))

    def _on_now_playing_changed(self, data):
        self.now_playing_changed.emit(data)

    def _on_connection_status_changed(self, connected, name):
        self.connection_status.emit(bool(connected), str(name))

    def forget_paired_devices(self):
        try:
            bus = dbus.SystemBus()
            om = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
            objects = om.GetManagedObjects()

            adapter_path = None
            for path, interfaces in objects.items():
                if "org.bluez.Adapter1" in interfaces:
                    adapter_path = path
                    break

            if adapter_path is None:
                print("[BT] Адаптер не найден")
                return False

            adapter = dbus.Interface(bus.get_object("org.bluez", adapter_path), "org.bluez.Adapter1")
            removed_any = False

            for path, interfaces in objects.items():
                if "org.bluez.Device1" not in interfaces:
                    continue

                print(f"[BT] Удаляю устройство: {path}")
                try:
                    adapter.RemoveDevice(path)
                    removed_any = True
                except Exception as e:
                    print(f"[BT] Ошибка RemoveDevice: {e}")

            return removed_any

        except Exception as e:
            print(f"[BT] Ошибка forget_paired_devices: {e}")
            return False

    def run(self):
        if not HAS_DBUS:
            log.warning("dbus/GLib не найдены. Эмуляция на ПК.")
            return

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()

        # Создаем единый экземпляр клиента
        self.client = AncsClient(bus)

        # Подключаем колбэки клиента к внутренним методам потока
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