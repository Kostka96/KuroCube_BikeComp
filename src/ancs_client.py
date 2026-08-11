#!/usr/bin/env python3
import struct
import sys
import logging
import subprocess

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
except ImportError:
    dbus = None

BLUEZ_SERVICE_NAME = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"
AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"
AGENT_IFACE = "org.bluez.Agent1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"

AGENT_PATH = "/kurocube/ancs/agent"
ADV_PATH = "/kurocube/ancs/advertisement"
DEVICE_NAME = "KuroCube"

ANCS_SERVICE_UUID = "7905f431-b5ce-4e99-a40f-4b1e122d00d0"
NOTIFICATION_SOURCE_UUID = "9fbf120d-6301-42d9-8c58-25e699a21dbd"
CONTROL_POINT_UUID = "69d1d8f3-45e1-49a8-9821-9bbdfdaad9d9"
DATA_SOURCE_UUID = "22eac6e9-24d6-4bb5-be44-b36ace7c7bfb"

EVENT_ID_NOTIFICATION_ADDED = 0
EVENT_ID_NOTIFICATION_MODIFIED = 1
EVENT_ID_NOTIFICATION_REMOVED = 2

CATEGORY_NAMES = {
    0: "Other", 1: "IncomingCall", 2: "MissedCall", 3: "Voicemail",
    4: "Social", 5: "Schedule", 6: "Email", 7: "News",
    8: "HealthAndFitness", 9: "BusinessAndFinance", 10: "Location",
    11: "Entertainment",
}

ATTR_APP_IDENTIFIER = 0
ATTR_TITLE = 1
ATTR_SUBTITLE = 2
ATTR_MESSAGE = 3
ATTR_MESSAGE_SIZE = 4
ATTR_DATE = 5
ATTR_POSITIVE_ACTION_LABEL = 6
ATTR_NEGATIVE_ACTION_LABEL = 7

COMMAND_GET_NOTIFICATION_ATTRIBUTES = 0

AMS_SERVICE_UUID = "89d3502b-0f36-433a-8ef4-c502ad55f8dc"
AMS_REMOTE_COMMAND_UUID = "9b3c81d8-57b1-4a8a-b8df-0e56f7ca51c2"
AMS_ENTITY_UPDATE_UUID = "2f7cabce-808d-411f-9a0c-bb92ba96c102"
AMS_ENTITY_ATTRIBUTE_UUID = "c6b2f38c-23ab-46d8-a6ab-a3a870bbd5d7"

AMS_ENTITY_PLAYER = 0
AMS_ENTITY_QUEUE = 1
AMS_ENTITY_TRACK = 2

AMS_PLAYER_ATTR_NAME = 0
AMS_PLAYER_ATTR_PLAYBACK_INFO = 1
AMS_PLAYER_ATTR_VOLUME = 2

AMS_TRACK_ATTR_ARTIST = 0
AMS_TRACK_ATTR_ALBUM = 1
AMS_TRACK_ATTR_TITLE = 2
AMS_TRACK_ATTR_DURATION = 3

PLAYBACK_STATE_NAMES = {
    "0": "paused", "1": "playing", "2": "rewinding", "3": "fast_forwarding",
}

CMD_PLAY = 0
CMD_PAUSE = 1
CMD_TOGGLE_PLAY_PAUSE = 2
CMD_NEXT_TRACK = 3
CMD_PREVIOUS_TRACK = 4
CMD_VOLUME_UP = 5
CMD_VOLUME_DOWN = 6

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ancs")


def on_notification(app_id, title, message, category):
    log.info("[%s] %s: %s — %s", category, app_id, title, message)


def on_now_playing_changed(now_playing):
    log.info("Now playing: %s", now_playing)


class Advertisement(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = ADV_PATH
        self.bus = bus
        self.ad_type = "peripheral"
        self.local_name = DEVICE_NAME
        self.include_tx_power = False
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            LE_ADVERTISEMENT_IFACE: {
                "Type": self.ad_type,
                "LocalName": dbus.String(self.local_name),
                "IncludeTxPower": dbus.Boolean(self.include_tx_power),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs", "Unknown interface"
            )
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        log.info("Advertisement released")


class Agent(dbus.service.Object):
    """Pairing agent с авто-подтверждением."""

    def __init__(self, bus, path):
        super().__init__(bus, path)
        log.info("Agent created at %s", path)

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        log.info("Agent released")

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        log.info("Agent: AuthorizeService %s for %s", uuid, device)
        return

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        log.info("Agent: RequestPinCode from %s", device)
        return "000000"

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        log.info("Agent: RequestPasskey from %s", device)
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_IFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        log.info("Agent: DisplayPasskey %s (entered %d)", passkey, entered)
        return

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        log.info("Agent: DisplayPinCode %s", pincode)
        return

    @dbus.service.method(AGENT_IFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        log.info("Agent: RequestConfirmation from %s, passkey %s — AUTO-ACCEPTING", device, passkey)
        return

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        log.info("Agent: RequestAuthorization from %s — AUTO-ACCEPTING", device)
        return

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Cancel(self):
        log.info("Agent request cancelled")


class AncsClient:
    def __init__(self, bus):
        self.bus = bus
        self.notification_source = None
        self.control_point = None
        self.data_source = None
        self.device_path = None
        self._data_buffer = bytearray()
        self._pending_uid = None
        self._pending_app_id = None
        self._pending_category = "Other"
        self._bound_chars = set()
        self.remote_command = None
        self.entity_update = None
        self.entity_attribute = None
        self.now_playing = {
            "player_name": "", "state": "", "artist": "", "album": "",
            "title": "", "duration": "",
        }

    def find_adapter(self):
        om = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
        objects = om.GetManagedObjects()
        for path, interfaces in objects.items():
            if ADAPTER_IFACE in interfaces:
                log.info("Found adapter: %s", path)
                return path
        raise RuntimeError("Bluetooth adapter not found")

    def setup_adapter(self):
        adapter_path = self.find_adapter()
        adapter = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), DBUS_PROP_IFACE)

        log.info("Configuring adapter...")
        adapter.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))
        adapter.Set(ADAPTER_IFACE, "Pairable", dbus.Boolean(True))
        adapter.Set(ADAPTER_IFACE, "PairableTimeout", dbus.UInt32(0))
        adapter.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(True))
        adapter.Set(ADAPTER_IFACE, "DiscoverableTimeout", dbus.UInt32(0))
        adapter.Set(ADAPTER_IFACE, "Alias", dbus.String(DEVICE_NAME))
        log.info("Adapter configured")
        return adapter_path

    def register_agent(self):
        agent = Agent(self.bus, AGENT_PATH)
        agent_manager = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez"), AGENT_MANAGER_IFACE
        )

        # 1. Пытаемся удалить старый агент (если висит от прошлого запуска)
        try:
            agent_manager.UnregisterAgent(AGENT_PATH)
            log.info("Unregistered old agent")
        except dbus.exceptions.DBusException as e:
            log.info("No old agent to unregister: %s", e)

        # 2. Пробуем разные типы агентов
        agent_types = ["KeyboardDisplay", "NoInputNoOutput", "DisplayOnly", "DisplayYesNo"]
        registered = False

        for agent_type in agent_types:
            try:
                log.info("Trying RegisterAgent with type '%s'...", agent_type)
                agent_manager.RegisterAgent(AGENT_PATH, agent_type)
                log.info("RegisterAgent succeeded with '%s'", agent_type)
                registered = True
                break
            except dbus.exceptions.DBusException as e:
                log.warning("RegisterAgent '%s' failed: %s", agent_type, e)

        if not registered:
            raise RuntimeError("Failed to register any agent type")

        # 3. Пытаемся сделать агента дефолтным
        try:
            agent_manager.RequestDefaultAgent(AGENT_PATH)
            log.info("RequestDefaultAgent succeeded")
        except dbus.exceptions.DBusException as e:
            log.warning("RequestDefaultAgent failed: %s (continuing anyway)", e)

    def register_advertisement(self, adapter_path):
        try:
            ad = Advertisement(self.bus, 0)
            ad_manager = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
                LE_ADVERTISING_MANAGER_IFACE,
            )
            ad_manager.RegisterAdvertisement(
                ad.path, {},
                reply_handler=lambda: log.info("Advertising started as '%s'", DEVICE_NAME),
                error_handler=lambda e: log.warning("Advertising error: %s", e),
            )
        except Exception as e:
            log.warning("RegisterAdvertisement exception: %s", e)

    def start(self):
        adapter_path = self.setup_adapter()
        self.register_agent()
        self.register_advertisement(adapter_path)

        om = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
        om.connect_to_signal("InterfacesAdded", self._on_interfaces_added)

        for path, interfaces in om.GetManagedObjects().items():
            if GATT_SERVICE_IFACE in interfaces:
                self._maybe_bind_service(path, interfaces[GATT_SERVICE_IFACE])
            if GATT_CHRC_IFACE in interfaces:
                self._maybe_bind_characteristic(path, interfaces[GATT_CHRC_IFACE])

    def _on_interfaces_added(self, path, interfaces):
        if DEVICE_IFACE in interfaces:
            props = interfaces[DEVICE_IFACE]
            addr = props.get("Address", "unknown")
            paired = bool(props.get("Paired", False))
            connected = bool(props.get("Connected", False))
            log.info("Device event: %s | addr=%s | paired=%s | connected=%s", path, addr, paired, connected)
            self.device_path = path

            if connected and not paired:
                log.info("Device connected but not paired — triggering Pair()")
                try:
                    dev_iface = dbus.Interface(
                        self.bus.get_object(BLUEZ_SERVICE_NAME, path), DEVICE_IFACE
                    )
                    dev_iface.Pair(reply_handler=lambda: log.info("Pair() succeeded"),
                                   error_handler=lambda e: log.warning("Pair() failed: %s", e))
                except Exception as e:
                    log.warning("Could not call Pair(): %s", e)

        if GATT_SERVICE_IFACE in interfaces:
            self._maybe_bind_service(path, interfaces[GATT_SERVICE_IFACE])
        if GATT_CHRC_IFACE in interfaces:
            self._maybe_bind_characteristic(path, interfaces[GATT_CHRC_IFACE])

    def _maybe_bind_service(self, path, props):
        uuid = props.get("UUID", "").lower()
        if uuid == ANCS_SERVICE_UUID:
            log.info("Found ANCS service at %s", path)
        elif uuid == AMS_SERVICE_UUID:
            log.info("Found AMS service at %s", path)

    def _maybe_bind_characteristic(self, path, props):
        if path in self._bound_chars:
            return
        uuid = props.get("UUID", "").lower()
        if uuid == NOTIFICATION_SOURCE_UUID:
            self.notification_source = path
            self._subscribe(path, self._handle_notification_source)
            self._bound_chars.add(path)
            log.info("Bound Notification Source: %s", path)
        elif uuid == CONTROL_POINT_UUID:
            self.control_point = path
            self._bound_chars.add(path)
            log.info("Bound Control Point: %s", path)
        elif uuid == DATA_SOURCE_UUID:
            self.data_source = path
            self._subscribe(path, self._handle_data_source)
            self._bound_chars.add(path)
            log.info("Bound Data Source: %s", path)
        elif uuid == AMS_REMOTE_COMMAND_UUID:
            self.remote_command = path
            self._bound_chars.add(path)
            log.info("Bound AMS Remote Command: %s", path)
        elif uuid == AMS_ENTITY_UPDATE_UUID:
            self.entity_update = path
            self._subscribe(path, self._handle_entity_update)
            self._bound_chars.add(path)
            log.info("Bound AMS Entity Update: %s", path)
            self._register_media_attributes()
        elif uuid == AMS_ENTITY_ATTRIBUTE_UUID:
            self.entity_attribute = path
            self._bound_chars.add(path)
            log.info("Bound AMS Entity Attribute: %s", path)

    def _subscribe(self, char_path, handler):
        chrc = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, char_path), GATT_CHRC_IFACE
        )
        props = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, char_path), DBUS_PROP_IFACE
        )

        def on_props_changed(interface, changed, invalidated):
            if interface != GATT_CHRC_IFACE:
                return
            if "Value" in changed:
                handler(bytes(bytearray(changed["Value"])))

        props.connect_to_signal("PropertiesChanged", on_props_changed)
        try:
            chrc.StartNotify()
        except dbus.exceptions.DBusException as e:
            log.warning("StartNotify failed for %s: %s", char_path, e)

    def _handle_notification_source(self, data):
        if len(data) < 8:
            return
        event_id, event_flags, category_id, category_count, uid = struct.unpack("<BBBBI", data[:8])
        if event_id not in (EVENT_ID_NOTIFICATION_ADDED, EVENT_ID_NOTIFICATION_MODIFIED):
            return
        category = CATEGORY_NAMES.get(category_id, str(category_id))
        log.info("Notification uid=%s category=%s", uid, category)
        self._request_attributes(uid, category)

    def _request_attributes(self, uid, category):
        if self.control_point is None:
            log.warning("Control Point not ready, dropping notification %s", uid)
            return
        self._pending_uid = uid
        self._pending_category = category
        self._data_buffer = bytearray()

        payload = bytearray()
        payload += struct.pack("<B", COMMAND_GET_NOTIFICATION_ATTRIBUTES)
        payload += struct.pack("<I", uid)
        payload += struct.pack("<B", ATTR_APP_IDENTIFIER)
        payload += struct.pack("<B", ATTR_TITLE) + struct.pack("<H", 32)
        payload += struct.pack("<B", ATTR_MESSAGE) + struct.pack("<H", 100)

        chrc = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, self.control_point), GATT_CHRC_IFACE
        )
        try:
            chrc.WriteValue(list(payload), {})
        except dbus.exceptions.DBusException as e:
            log.warning("WriteValue failed: %s", e)

    def _handle_data_source(self, data: bytes):
        self._data_buffer += data
        buf = self._data_buffer
        if len(buf) < 5:
            return
        command_id, uid = struct.unpack("<BI", buf[:5])
        if command_id != COMMAND_GET_NOTIFICATION_ATTRIBUTES:
            return

        # Если сообщение с этим UID уже обработано, пропускаем
        if getattr(self, "_last_processed_uid", None) == uid:
            return

        offset = 5
        attrs = {}
        while offset + 3 <= len(buf):
            attr_id = buf[offset]
            length = struct.unpack("<H", buf[offset + 1: offset + 3])[0]
            value_end = offset + 3 + length
            if value_end > len(buf):
                return  # ждем фрагменты
            value = bytes(buf[offset + 3: value_end]).decode("utf-8", errors="replace")
            attrs[attr_id] = value
            offset = value_end

        app_id = attrs.get(ATTR_APP_IDENTIFIER, "")
        title = attrs.get(ATTR_TITLE, "")
        message = attrs.get(ATTR_MESSAGE, "")
        category = getattr(self, "_pending_category", "Other")

        # Запоминаем обработанный UID и очищаем буфер
        self._last_processed_uid = uid
        self._data_buffer = bytearray()

        on_notification(app_id, title, message, category)

    def _register_media_attributes(self):
        if self.entity_update is None:
            return
        chrc = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, self.entity_update), GATT_CHRC_IFACE
        )
        try:
            chrc.WriteValue([AMS_ENTITY_PLAYER, AMS_PLAYER_ATTR_NAME, AMS_PLAYER_ATTR_PLAYBACK_INFO], {})
            chrc.WriteValue([AMS_ENTITY_TRACK, AMS_TRACK_ATTR_ARTIST, AMS_TRACK_ATTR_ALBUM,
                             AMS_TRACK_ATTR_TITLE, AMS_TRACK_ATTR_DURATION], {})
            log.info("Subscribed to AMS updates")
        except dbus.exceptions.DBusException as e:
            log.warning("AMS subscribe failed: %s", e)

    def _handle_entity_update(self, data):
        if len(data) < 3:
            return
        entity_id, attribute_id = data[0], data[1]
        value = bytes(data[3:]).decode("utf-8", errors="replace")

        if entity_id == AMS_ENTITY_PLAYER:
            if attribute_id == AMS_PLAYER_ATTR_NAME:
                self.now_playing["player_name"] = value
            elif attribute_id == AMS_PLAYER_ATTR_PLAYBACK_INFO:
                state_code = value.split(",")[0] if value else ""
                self.now_playing["state"] = PLAYBACK_STATE_NAMES.get(state_code, state_code)
        elif entity_id == AMS_ENTITY_TRACK:
            key = {AMS_TRACK_ATTR_ARTIST: "artist", AMS_TRACK_ATTR_ALBUM: "album",
                   AMS_TRACK_ATTR_TITLE: "title", AMS_TRACK_ATTR_DURATION: "duration"}.get(attribute_id)
            if key:
                self.now_playing[key] = value

        on_now_playing_changed(dict(self.now_playing))

    def send_remote_command(self, command_id):
        if self.remote_command is None:
            log.warning("Remote Command not ready")
            return
        chrc = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, self.remote_command), GATT_CHRC_IFACE
        )
        try:
            chrc.WriteValue([command_id], {})
        except dbus.exceptions.DBusException as e:
            log.warning("Remote command failed: %s", e)

    def play(self): self.send_remote_command(CMD_PLAY)
    def pause(self): self.send_remote_command(CMD_PAUSE)
    def toggle_play_pause(self): self.send_remote_command(CMD_TOGGLE_PLAY_PAUSE)
    def next_track(self): self.send_remote_command(CMD_NEXT_TRACK)
    def previous_track(self): self.send_remote_command(CMD_PREVIOUS_TRACK)


def _setup_stdin_commands(client):
    commands = {
        "play": client.play, "pause": client.pause,
        "toggle": client.toggle_play_pause, "next": client.next_track,
        "prev": client.previous_track, "previous": client.previous_track,
    }
    def on_stdin_ready(source, condition):
        line = sys.stdin.readline().strip().lower()
        if not line: return True
        fn = commands.get(line)
        if fn: fn()
        return True
    GLib.io_add_watch(sys.stdin, GLib.IO_IN, on_stdin_ready)


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    client = AncsClient(bus)
    client.start()
    _setup_stdin_commands(client)
    log.info("Waiting for iPhone... Connect to '%s'", DEVICE_NAME)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()