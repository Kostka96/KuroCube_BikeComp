#!/usr/bin/env python3
import struct
import sys
import logging
from collections import deque

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
except ImportError:
    dbus = None
    GLib = None

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


def on_connection_status_changed(connected: bool, device_name: str):
    log.info("Status changed: connected=%s, name=%s", connected, device_name)


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
        self.solicit_uuids = ["7905F431-B5CE-4E99-A40F-4B1E122D00D0"]
        super().__init__(bus, self.path)

    def get_properties(self):
        properties = {
            "Type": self.ad_type,
            "LocalName": dbus.String(self.local_name),
            "IncludeTxPower": dbus.Boolean(self.include_tx_power),
        }
        if self.solicit_uuids:
            properties["SolicitUUIDs"] = dbus.Array(
                [dbus.String(u) for u in self.solicit_uuids], signature="s"
            )
        return {LE_ADVERTISEMENT_IFACE: properties}

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

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        log.info("Agent: DisplayPinCode %s", pincode)

    @dbus.service.method(AGENT_IFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        log.info("Agent: RequestConfirmation from %s, passkey %s — AUTO-ACCEPTING", device, passkey)

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        log.info("Agent: RequestAuthorization from %s — AUTO-ACCEPTING", device)

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
        self._bound_chars = set()

        # ANCS notification request state.
        self._attribute_queue = deque()
        self._attribute_request_active = False
        self._pending_uid = None
        self._pending_category = "Other"
        self._data_buffer = bytearray()

        # Keep D-Bus objects alive for the whole client lifetime.
        self.agent = None
        self.advertisement = None

        # AMS state.
        self.remote_command = None
        self.entity_update = None
        self.entity_attribute = None
        self._media_registered = False

        self.now_playing = {
            "player_name": "", "state": "", "artist": "", "album": "",
            "title": "", "duration": "", "elapsed": "0",
        }

        # Instance callbacks.
        self.on_notification = on_notification
        self.on_now_playing_changed = on_now_playing_changed
        self.on_connection_status_changed = on_connection_status_changed

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
        adapter = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), DBUS_PROP_IFACE
        )
        log.info("Configuring adapter...")
        adapter.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))
        adapter.Set(ADAPTER_IFACE, "Pairable", dbus.Boolean(True))
        adapter.Set(ADAPTER_IFACE, "PairableTimeout", dbus.UInt32(0))
        adapter.Set(ADAPTER_IFACE, "DiscoverableTimeout", dbus.UInt32(180))
        adapter.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(True))
        adapter.Set(ADAPTER_IFACE, "Alias", dbus.String(DEVICE_NAME))
        log.info("Adapter configured")
        return adapter_path

    def register_agent(self):
        self.agent = Agent(self.bus, AGENT_PATH)
        agent_manager = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez"), AGENT_MANAGER_IFACE
        )

        try:
            agent_manager.UnregisterAgent(AGENT_PATH)
            log.info("Unregistered old agent")
        except dbus.exceptions.DBusException as e:
            log.info("No old agent to unregister: %s", e)

        agent_types = ["KeyboardDisplay", "NoInputNoOutput", "DisplayOnly", "DisplayYesNo"]
        for agent_type in agent_types:
            try:
                log.info("Trying RegisterAgent with type '%s'...", agent_type)
                agent_manager.RegisterAgent(AGENT_PATH, agent_type)
                log.info("RegisterAgent succeeded with '%s'", agent_type)
                break
            except dbus.exceptions.DBusException as e:
                log.warning("RegisterAgent '%s' failed: %s", agent_type, e)
        else:
            raise RuntimeError("Failed to register any agent type")

        try:
            agent_manager.RequestDefaultAgent(AGENT_PATH)
            log.info("RequestDefaultAgent succeeded")
        except dbus.exceptions.DBusException as e:
            log.warning("RequestDefaultAgent failed: %s (continuing anyway)", e)

    def register_advertisement(self, adapter_path):
        try:
            self.advertisement = Advertisement(self.bus, 0)
            ad_manager = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
                LE_ADVERTISING_MANAGER_IFACE,
            )
            ad_manager.RegisterAdvertisement(
                self.advertisement.path,
                {},
                reply_handler=lambda: log.info("Advertising started as '%s'", DEVICE_NAME),
                error_handler=lambda e: log.warning("Advertising error: %s", e),
            )
        except Exception as e:
            log.warning("RegisterAdvertisement exception: %s", e)

    def connect_known_devices(self):
        try:
            om = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
            objects = om.GetManagedObjects()
            for path, interfaces in objects.items():
                if DEVICE_IFACE not in interfaces:
                    continue
                props = interfaces[DEVICE_IFACE]
                paired = bool(props.get("Paired", False))
                connected = bool(props.get("Connected", False))
                if paired and not connected:
                    log.info("Найден сохраненный device (%s). Пробуем Connect()...", path)
                    dev_iface = dbus.Interface(
                        self.bus.get_object(BLUEZ_SERVICE_NAME, path), DEVICE_IFACE
                    )
                    dev_iface.Connect(
                        reply_handler=lambda: log.info("Успешное авто-подключение!"),
                        error_handler=lambda e: log.debug(
                            "Фоновое авто-подключение не выполнено: %s", e
                        ),
                    )
        except Exception as e:
            log.warning("Ошибка при попытке автоподключения: %s", e)

    def start(self):
        adapter_path = self.setup_adapter()
        self.register_agent()
        self.register_advertisement(adapter_path)

        om = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
        om.connect_to_signal("InterfacesAdded", self._on_interfaces_added)

        self.bus.add_signal_receiver(
            self._on_device_properties_changed,
            signal_name="PropertiesChanged",
            dbus_interface=DBUS_PROP_IFACE,
            arg0=DEVICE_IFACE,
            path_keyword="path",
        )

        for path, interfaces in om.GetManagedObjects().items():
            if GATT_SERVICE_IFACE in interfaces:
                self._maybe_bind_service(path, interfaces[GATT_SERVICE_IFACE])
            if GATT_CHRC_IFACE in interfaces:
                self._maybe_bind_characteristic(path, interfaces[GATT_CHRC_IFACE])

        self.connect_known_devices()

    def reset_now_playing(self):
        self.now_playing = {
            "player_name": "",
            "state": "paused",
            "artist": "",
            "album": "",
            "title": "Disconnected",
            "duration": "0",
            "elapsed": "0",
        }
        if callable(self.on_now_playing_changed):
            self.on_now_playing_changed(dict(self.now_playing))

    def _reset_gatt_state(self):
        self.notification_source = None
        self.control_point = None
        self.data_source = None
        self.remote_command = None
        self.entity_update = None
        self.entity_attribute = None

        self._bound_chars.clear()
        self._media_registered = False

        self._attribute_queue.clear()
        self._attribute_request_active = False
        self._pending_uid = None
        self._pending_category = "Other"
        self._data_buffer.clear()

    def _on_device_properties_changed(self, interface, changed, invalidated, path):
        if "Connected" in changed:
            connected = bool(changed["Connected"])
            if connected:
                try:
                    adapter_path = self.find_adapter()
                    adapter = dbus.Interface(
                        self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), DBUS_PROP_IFACE
                    )
                    adapter.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(False))
                    log.info("Устройство подключено: Discoverable отключен")
                except Exception as e:
                    log.warning("Не удалось отключить Discoverable: %s", e)
            else:
                log.info("BLE device disconnected; resetting GATT/ANCS state")
                self._reset_gatt_state()
                self.reset_now_playing()

                try:
                    adapter_path = self.find_adapter()
                    adapter = dbus.Interface(
                        self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path), DBUS_PROP_IFACE
                    )
                    adapter.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(True))
                    log.info("Устройство отключено: Discoverable снова включен")
                    self.connect_known_devices()
                except Exception as e:
                    log.warning("Не удалось включить Discoverable при отключении: %s", e)
            try:
                dev_prop = dbus.Interface(
                    self.bus.get_object(BLUEZ_SERVICE_NAME, path), DBUS_PROP_IFACE
                )
                name = str(dev_prop.Get(DEVICE_IFACE, "Name"))
            except Exception:
                name = "iPhone"

            if callable(self.on_connection_status_changed):
                self.on_connection_status_changed(connected, name)

        if "ServicesResolved" in changed and bool(changed["ServicesResolved"]):
            log.info("Сервисы GATT инициализированы (ServicesResolved).")

            # --- ПРИНУДИТЕЛЬНОЕ ПЕРЕСКАНИРОВАНИЕ GATT ---
            om = dbus.Interface(self.bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
            for obj_path, interfaces in om.GetManagedObjects().items():
                if GATT_SERVICE_IFACE in interfaces:
                    self._maybe_bind_service(obj_path, interfaces[GATT_SERVICE_IFACE])
                if GATT_CHRC_IFACE in interfaces:
                    self._maybe_bind_characteristic(obj_path, interfaces[GATT_CHRC_IFACE])
            # ------------------------------------------------

            # AMS + ANCS: попробовать подписаться и запустить очередь
            self._register_media_attributes()
            self._process_next_attribute_request()

    def _on_interfaces_added(self, path, interfaces):
        if DEVICE_IFACE in interfaces:
            props = interfaces[DEVICE_IFACE]
            addr = props.get("Address", "unknown")
            paired = bool(props.get("Paired", False))
            connected = bool(props.get("Connected", False))
            name = str(props.get("Name", "iPhone"))
            log.info(
                "Device event: %s | addr=%s | paired=%s | connected=%s",
                path, addr, paired, connected,
            )
            self.device_path = path

            try:
                dev_prop = dbus.Interface(
                    self.bus.get_object(BLUEZ_SERVICE_NAME, path), DBUS_PROP_IFACE
                )
                dev_prop.Set(DEVICE_IFACE, "Trusted", dbus.Boolean(True))
                log.info("Device %s marked as Trusted", addr)
            except Exception as e:
                log.warning("Failed to set Trusted: %s", e)

            if connected and not paired:
                log.info("Device connected but not paired — triggering Pair()")
                try:
                    dev_iface = dbus.Interface(
                        self.bus.get_object(BLUEZ_SERVICE_NAME, path), DEVICE_IFACE
                    )
                    dev_iface.Pair(
                        reply_handler=lambda: log.info("Pair() succeeded"),
                        error_handler=lambda e: log.warning("Pair() failed: %s", e),
                    )
                except Exception as e:
                    log.warning("Could not call Pair(): %s", e)

            if callable(self.on_connection_status_changed):
                self.on_connection_status_changed(connected, name)

        if GATT_SERVICE_IFACE in interfaces:
            self._maybe_bind_service(path, interfaces[GATT_SERVICE_IFACE])
        if GATT_CHRC_IFACE in interfaces:
            self._maybe_bind_characteristic(path, interfaces[GATT_CHRC_IFACE])

    def _maybe_bind_service(self, path, props):
        uuid = str(props.get("UUID", "")).lower()
        if uuid == ANCS_SERVICE_UUID:
            log.info("Found ANCS service at %s", path)
        elif uuid == AMS_SERVICE_UUID:
            log.info("Found AMS service at %s", path)

    def _maybe_bind_characteristic(self, path, props):
        if path in self._bound_chars:
            return
        uuid = str(props.get("UUID", "")).lower()

        if uuid == NOTIFICATION_SOURCE_UUID:
            self.notification_source = path
            self._subscribe(path, self._handle_notification_source)
            self._bound_chars.add(path)
            log.info("Bound Notification Source: %s", path)

        elif uuid == CONTROL_POINT_UUID:
            self.control_point = path
            self._bound_chars.add(path)
            log.info("Bound Control Point: %s", path)
            # Если к этому моменту уже есть уведомления в очереди — пробуем их обработать
            self._process_next_attribute_request()

        elif uuid == DATA_SOURCE_UUID:
            self.data_source = path
            self._subscribe(path, self._handle_data_source)
            self._bound_chars.add(path)
            log.info("Bound Data Source: %s", path)
            # Аналогично — запускаем обработку очереди, если всё готово
            self._process_next_attribute_request()

        elif uuid == AMS_REMOTE_COMMAND_UUID:
            self.remote_command = path
            self._bound_chars.add(path)
            log.info("Bound AMS Remote Command: %s", path)

        elif uuid == AMS_ENTITY_UPDATE_UUID:
            self.entity_update = path
            self._bound_chars.add(path)
            self._subscribe(path, self._handle_entity_update)
            log.info("Bound AMS Entity Update: %s", path)
            self._register_media_attributes()

        elif uuid == AMS_ENTITY_ATTRIBUTE_UUID:
            self.entity_attribute = path
            self._bound_chars.add(path)
            log.info("Bound AMS Entity Attribute: %s", path)

    def _subscribe(self, char_path, handler):
        props = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, char_path), DBUS_PROP_IFACE
        )

        def on_props_changed(interface, changed, invalidated):
            if interface != GATT_CHRC_IFACE:
                return
            if "Value" in changed:
                try:
                    handler(bytes(bytearray(changed["Value"])))
                except Exception:
                    log.exception("Error in GATT notification handler for %s", char_path)

        props.connect_to_signal("PropertiesChanged", on_props_changed)
        try:
            chrc = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE_NAME, char_path), GATT_CHRC_IFACE
            )
            chrc.StartNotify()
        except dbus.exceptions.DBusException as e:
            log.warning("StartNotify failed for %s: %s", char_path, e)

    def _handle_notification_source(self, data):
        if len(data) < 8:
            log.warning("Short ANCS Notification Source packet: %d bytes", len(data))
            return

        event_id, event_flags, category_id, category_count, uid = struct.unpack("<BBBBI", data[:8])
        if event_id == EVENT_ID_NOTIFICATION_REMOVED:
            log.debug("Ignoring removed notification uid=%s", uid)
            return
        if event_id not in (EVENT_ID_NOTIFICATION_ADDED, EVENT_ID_NOTIFICATION_MODIFIED):
            return

        category = CATEGORY_NAMES.get(category_id, str(category_id))
        log.info("Notification uid=%s category=%s", uid, category)
        self._request_attributes(uid, category)

    def _request_attributes(self, uid, category):
        if self.control_point is None or self.data_source is None:
            log.warning("ANCS Control Point/Data Source not ready, queueing notification %s", uid)
        self._attribute_queue.append((uid, category))
        self._process_next_attribute_request()

    def _process_next_attribute_request(self):
        if self._attribute_request_active:
            return
        if not self._attribute_queue:
            return
        if self.control_point is None or self.data_source is None:
            return

        uid, category = self._attribute_queue.popleft()
        self._pending_uid = uid
        self._pending_category = category
        self._data_buffer.clear()
        self._attribute_request_active = True

        payload = bytearray()
        payload += struct.pack("<B", COMMAND_GET_NOTIFICATION_ATTRIBUTES)
        payload += struct.pack("<I", uid)
        payload += struct.pack("<B", ATTR_APP_IDENTIFIER)
        payload += struct.pack("<B", ATTR_TITLE) + struct.pack("<H", 32)
        payload += struct.pack("<B", ATTR_MESSAGE) + struct.pack("<H", 100)

        try:
            chrc = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE_NAME, self.control_point), GATT_CHRC_IFACE
            )
            chrc.WriteValue(list(payload), {})
            log.debug("Requested ANCS attributes for uid=%s", uid)
        except dbus.exceptions.DBusException as e:
            log.warning("WriteValue failed for uid=%s: %s", uid, e)
            self._finish_attribute_request()

    def _finish_attribute_request(self):
        self._attribute_request_active = False
        self._pending_uid = None
        self._pending_category = "Other"
        self._data_buffer.clear()
        self._process_next_attribute_request()

    def _handle_data_source(self, data: bytes):
        if not self._attribute_request_active:
            log.debug("Ignoring ANCS Data Source packet without active request")
            return

        self._data_buffer += data
        buf = self._data_buffer
        if len(buf) < 5:
            return

        command_id, uid = struct.unpack("<BI", buf[:5])
        if command_id != COMMAND_GET_NOTIFICATION_ATTRIBUTES:
            log.warning("Unexpected ANCS Data Source command id=%s", command_id)
            self._finish_attribute_request()
            return

        if self._pending_uid is not None and uid != self._pending_uid:
            log.warning("Unexpected ANCS response UID=%s, expected=%s", uid, self._pending_uid)
            return

        offset = 5
        attrs = {}
        while offset + 3 <= len(buf):
            attr_id = buf[offset]
            length = struct.unpack("<H", buf[offset + 1:offset + 3])[0]
            value_end = offset + 3 + length
            if value_end > len(buf):
                return
            raw_value = bytes(buf[offset + 3:value_end])
            attrs[attr_id] = raw_value.decode("utf-8", errors="replace")
            offset = value_end

        required = {ATTR_APP_IDENTIFIER, ATTR_TITLE, ATTR_MESSAGE}
        if not required.issubset(attrs):
            return

        app_id = attrs.get(ATTR_APP_IDENTIFIER, "")
        title = attrs.get(ATTR_TITLE, "")
        message = attrs.get(ATTR_MESSAGE, "")
        category = self._pending_category

        if callable(self.on_notification):
            self.on_notification(app_id, title, message, category)

        self._finish_attribute_request()

    def _register_media_attributes(self):
        if self.entity_update is None or self._media_registered:
            return

        chrc = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, self.entity_update), GATT_CHRC_IFACE
        )
        try:
            chrc.WriteValue(
                [AMS_ENTITY_PLAYER, AMS_PLAYER_ATTR_NAME, AMS_PLAYER_ATTR_PLAYBACK_INFO], {}
            )
            chrc.WriteValue(
                [AMS_ENTITY_TRACK, AMS_TRACK_ATTR_ARTIST, AMS_TRACK_ATTR_ALBUM,
                 AMS_TRACK_ATTR_TITLE, AMS_TRACK_ATTR_DURATION], {}
            )
            self._media_registered = True
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
                parts = value.split(",") if value else []
                state_code = parts[0] if len(parts) > 0 else ""
                elapsed = parts[2] if len(parts) > 2 else "0"
                self.now_playing["state"] = PLAYBACK_STATE_NAMES.get(state_code, state_code)
                self.now_playing["elapsed"] = elapsed
        elif entity_id == AMS_ENTITY_TRACK:
            key = {
                AMS_TRACK_ATTR_ARTIST: "artist",
                AMS_TRACK_ATTR_ALBUM: "album",
                AMS_TRACK_ATTR_TITLE: "title",
                AMS_TRACK_ATTR_DURATION: "duration",
            }.get(attribute_id)
            if key:
                self.now_playing[key] = value

        if callable(self.on_now_playing_changed):
            self.on_now_playing_changed(dict(self.now_playing))

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

    def play(self):
        self.send_remote_command(CMD_PLAY)

    def pause(self):
        self.send_remote_command(CMD_PAUSE)

    def toggle_play_pause(self):
        self.send_remote_command(CMD_TOGGLE_PLAY_PAUSE)

    def next_track(self):
        self.send_remote_command(CMD_NEXT_TRACK)

    def previous_track(self):
        self.send_remote_command(CMD_PREVIOUS_TRACK)

    def volume_up(self):
        self.send_remote_command(CMD_VOLUME_UP)

    def volume_down(self):
        self.send_remote_command(CMD_VOLUME_DOWN)




def _setup_stdin_commands(client):
    commands = {
        "play": client.play,
        "pause": client.pause,
        "toggle": client.toggle_play_pause,
        "next": client.next_track,
        "prev": client.previous_track,
        "previous": client.previous_track,
        "volup": client.volume_up,
        "voldown": client.volume_down,
    }

    def on_stdin_ready(source, condition):
        line = sys.stdin.readline().strip().lower()
        if not line:
            return True
        fn = commands.get(line)
        if fn:
            fn()
        return True

    GLib.io_add_watch(sys.stdin, GLib.IO_IN, on_stdin_ready)


def main():
    if dbus is None or GLib is None:
        raise RuntimeError("Python D-Bus/GLib modules are not available")

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    client = AncsClient(bus)
    client.start()
    _setup_stdin_commands(client)
    log.info("Waiting for iPhone... Connect to '%s'", DEVICE_NAME)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()