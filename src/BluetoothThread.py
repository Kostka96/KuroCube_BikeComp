import subprocess
from PyQt6.QtCore import QThread, pyqtSignal
try:
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib
    from ancs_client import AncsClient
    import ancs_client as _ancs_mod
    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False
    AncsClient = None
    _ancs_mod = None


class BluetoothThread(QThread):
    notification_received = pyqtSignal(str, str, str, str)
    now_playing_changed = pyqtSignal(dict)
    status_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.client = None

    def forget_paired_devices(self):
        if not HAS_DBUS:
            self.status_changed.emit("Сброс не поддерживается на Windows")
            return False

        try:
            bus = dbus.SystemBus()
            om = dbus.Interface(
                bus.get_object("org.bluez", "/"),
                "org.freedesktop.DBus.ObjectManager"
            )
            objects = om.GetManagedObjects()
            removed = 0

            for path, interfaces in objects.items():
                if "org.bluez.Device1" not in interfaces:
                    continue
                try:
                    props_iface = dbus.Interface(
                        bus.get_object("org.bluez", path),
                        "org.freedesktop.DBus.Properties"
                    )
                    if bool(props_iface.Get("org.bluez.Device1", "Paired")):
                        dev_iface = dbus.Interface(
                            bus.get_object("org.bluez", path), "org.bluez.Device1"
                        )
                        try:
                            dev_iface.Disconnect()
                        except Exception:
                            pass
                        adapter_path = path.rsplit("/dev_", 1)[0]
                        adapter = dbus.Interface(
                            bus.get_object("org.bluez", adapter_path), "org.bluez.Adapter1"
                        )
                        adapter.RemoveDevice(path)
                        removed += 1
                except Exception as e:
                    print(f"[BT] skip {path}: {e}")

            self.status_changed.emit(f"Сброшено устройств: {removed}")
            return True
        except Exception as e:
            self.status_changed.emit(f"Ошибка сброса: {e}")
            return False

    def run(self):
        if not HAS_DBUS:
            self.status_changed.emit("Bluetooth недоступен (Windows)")
            return

        self.status_changed.emit("Инициализация Bluetooth...")
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()

        self.client = AncsClient(bus)

        def _on_notif(app_id, title, message, category):
            self.notification_received.emit(app_id, title, message, category)

        def _on_media(now_playing):
            self.now_playing_changed.emit(now_playing)

        _ancs_mod.on_notification = _on_notif
        _ancs_mod.on_now_playing_changed = _on_media

        original = self.client._on_interfaces_added

        def _patched(path, interfaces):
            original(path, interfaces)
            if "org.bluez.Device1" in interfaces:
                self.status_changed.emit("Устройство подключено")

        self.client._on_interfaces_added = _patched

        try:
            self.client.start()
            self.status_changed.emit("Ожидание iPhone...")
            loop = GLib.MainLoop()
            loop.run()
        except Exception as e:
            print(f"[BT ERROR] {e}")
            self.status_changed.emit(f"Ошибка: {e}")

    def play_pause(self):
        if self.client:
            self.client.toggle_play_pause()

    def next_track(self):
        if self.client:
            self.client.next_track()

    def prev_track(self):
        if self.client:
            self.client.previous_track()