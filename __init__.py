import json
from flask import redirect, render_template, request, jsonify
from sqlalchemy import or_
from app.authentication.handlers import handle_admin_required
from app.database import session_scope
from app.database import row2dict, get_now_to_utc
from app.core.main.BasePlugin import BasePlugin
from app.core.lib.object import callMethodThread, updatePropertyThread, setLinkToObject, removeLinkFromObject
from plugins.ThinQ.models.ThinqDevices import ThinqDevices
from plugins.ThinQ.models.ThinqStates import ThinqStates
from plugins.ThinQ.forms.SettingsForm import SettingsForm

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from aiohttp import ClientSession

import sys
from enum import Enum

# Проверяем версию Python (StrEnum появился в 3.11+)
if sys.version_info < (3, 11):
    class StrEnum(str, Enum):
        """
        Упрощённая реализация StrEnum для Python < 3.11.
        Позволяет использовать enum-значения как строки.
        """
        def __str__(self):
            return self.value

        def __repr__(self):
            return f"{self.__class__.__name__}.{self.name}"

        @classmethod
        def _missing_(cls, value):
            """Для поддержки поиска по значению, как в Python 3.11+"""
            for member in cls:
                if member.value == value:
                    return member
            raise ValueError(f"'{value}' is not a valid {cls.__name__}")

    # Подменяем StrEnum в модуле enum
    sys.modules['enum'].StrEnum = StrEnum

from thinqconnect import ThinQApi, ThinQMQTTClient, ThinQAPIException

class ThinQ(BasePlugin):

    def __init__(self,app):
        super().__init__(app,__name__)
        self.title = "ThinQ"
        self.version = 1
        self.description = """LG ThinQ v2 protocol"""
        self.category = "Devices"
        self.actions = ['cycle','search']
        self.author = "Eraser"
        self._client = None
        self.is_connect = False

        # Настройки для async операций
        self.loop = None
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.client = None

    def initialization(self):
        """Инициализация плагина"""
        self.logger.info("Initializing ThinQ Connect plugin")

        # Получаем настройки из конфигурации
        self.api_key = self.config.get('api_key', None)
        self.country = self.config.get('country', 'RU')
        self.client_id = self.config.get('client_id', None)
        if not self.client_id:
            import uuid
            self.client_id = str(uuid.uuid4())
            self.config['client_id'] = self.client_id
            self.saveConfig()

        if not self.api_key:
            self.logger.warning("API key not configured")

        # Создаем новый event loop для async операций
        self.loop = asyncio.new_event_loop()

    def start_cycle(self):
        """Переопределяем запуск цикла для поддержки async"""
        super().start_cycle()

        # Запускаем event loop в отдельном потоке
        if self.loop:
            def run_loop():
                asyncio.set_event_loop(self.loop)
                self.loop.run_forever()

            loop_thread = threading.Thread(target=run_loop, daemon=True)
            loop_thread.start()

    def stop_cycle(self):
        """Переопределяем остановку цикла"""
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

        super().stop_cycle()

    def cyclic_task(self):
        """Основной цикл плагина"""
        if not self.api_key:
            self.event.wait(5.00)
            return

        try:
            # Запускаем async операции в отдельном потоке
            future = asyncio.run_coroutine_threadsafe(
                self._async_update_devices(),
                self.loop
            )

            # Ждем результат с таймаутом
            result = future.result(timeout=30)

            if result:
                self.logger.debug(f"Updated {result} devices")

        except Exception as ex:
            self.logger.error(f"Error in cyclic task: {ex}")

        self.event.wait(60.00)

    async def _async_update_devices(self):
        """Async метод для обновления устройств"""
        try:
            # Инициализируем клиент если нужно
            if not self.client:
                await self._async_connect_thinq()

            # Получаем список устройств
            devices = await self.client.async_get_device_list()

            if len(devices) == 0:
                self.logger.info("No devices found!")
                return None

            with session_scope() as session:
                for device in devices:

                    self.logger.debug("{}: {} (model {})".format(device['deviceId'], device['deviceInfo']['alias'], device['deviceInfo']['modelName']))
                    rec = session.query(ThinqDevices).filter(ThinqDevices.uuid == device['deviceId']).one_or_none()
                    if not rec:
                        rec = ThinqDevices()
                        rec.uuid = device['deviceId']
                        session.add(rec)
                    rec.alias = device['deviceInfo']['alias']
                    rec.device_type = device['deviceInfo']['deviceType']
                    rec.model_name = device['deviceInfo']['modelName']
                    rec.updated = get_now_to_utc()
                    session.commit()

                    # try:
                    #     profile = await self.client.async_get_device_profile(device['deviceId'])
                    #     self.logger.info("profile : %s", profile)
                    # except Exception as ex:
                    #     self.logger.exception(ex)

                    try:
                        status = await self.client.async_get_device_status(device['deviceId'])
                        self.logger.info("status : %s", status)
                        rec.online = True

                        for name, prop in status.items():
                            if isinstance(prop, list):
                                for item in prop:
                                    loc = item['locationName']
                                    for key,value in item.items():
                                        if key != 'locationName':
                                            self.updateValue(session, f"{name}_{loc}_{key}", value, rec.id)

                            if isinstance(prop, dict):
                                for key,value in prop.items():
                                    self.updateValue(session, f"{name}_{key}", value, rec.id)

                        self.updateValue(session, "online", True, rec.id)

                    except ThinQAPIException as ex:
                        if ex.code == 1222:  # NOT_CONNECTED_DEVICE
                            self.updateValue(session, "online", False, rec.id)
                    except Exception as ex:
                        self.updateValue(session, "online", False, rec.id)
                        self.logger.exception(ex)

                    session.commit()

                return len(devices)

        except Exception as ex:
            self.logger.error(f"Async operation failed: {ex}")
            return None

    async def _async_connect_thinq(self):
        try:
            self.session = ClientSession()
            self.client = ThinQApi(session=self.session, access_token=self.api_key, country_code=self.country, client_id=self.client_id)
            self.mqtt_client = ThinQMQTTClient(
                self.client, self.client_id,
                self._on_message_received,
                self._on_connection_interrupted,
                self._on_connection_success,
                self._on_connection_failure,
                self._on_connection_closed)
            await self.mqtt_client.async_init()
            await self.mqtt_client.async_prepare_mqtt()
            await self.mqtt_client.async_connect_mqtt()

            # Получаем список устройств
            devices = await self.client.async_get_device_list()

            if len(devices) == 0:
                self.logger.info("No devices found!")
                return

            for device in devices:
                device_id = device.get("deviceId")
                try:
                    response = await self.client.async_post_push_subscribe(device_id)
                    self.logger.info("push subscribe : %s", response)
                except ThinQAPIException as ex:
                    self.logger.warning(ex)
                except Exception as ex:
                    self.logger.exception(ex)

                try:
                    response = await self.client.async_post_event_subscribe(device_id)
                    self.logger.info("event subscribe : %s", response)
                except ThinQAPIException as ex:
                    self.logger.warning(ex)
                except Exception as ex:
                    self.logger.exception(ex)

        except Exception as ex:
            self.logger.exception(ex)

    def admin(self, request):
        op = request.args.get('op', '')
        device = request.args.get('device',None)

        if op == 'edit':
            if device:
                return render_template("thinq_device.html", id=device)

        if op == 'delete':
            if device:
                with session_scope() as session:
                    session.query(ThinqStates).filter(ThinqStates.device_id == device).delete(synchronize_session=False)
                    session.query(ThinqDevices).filter(ThinqDevices.id == device).delete(synchronize_session=False)
                    session.commit()
                return redirect("ThinQ")

        settings = SettingsForm()
        if request.method == 'GET':
            settings.api_key.data = self.config.get('api_key','')
            settings.country.data = self.config.get('country','RU')
        else:
            if settings.validate_on_submit():
                self.config["api_key"] = settings.api_key.data
                self.config["country"] = settings.country.data
                self.api_key = settings.api_key.data
                self.country = settings.country.data
                self.saveConfig()
                return redirect("ThinQ")

        devices = ThinqDevices.query.all()
        devices = [row2dict(device) for device in devices]
        content = {
            "devices": devices,
            "form": settings,
        }
        return self.render('thinq_devices.html', content)

    def route_index(self):
        @self.blueprint.route('/ThinQ/device', methods=['POST'])
        @self.blueprint.route('/ThinQ/device/<device_id>', methods=['GET', 'POST'])
        @handle_admin_required
        def point_thinq_device(device_id=None):
            with session_scope() as session:
                if request.method == "GET":
                    dev = session.query(ThinqDevices).filter(ThinqDevices.id == device_id).one()
                    device = row2dict(dev)
                    device['props'] = []
                    props = session.query(ThinqStates).filter(ThinqStates.device_id == device_id).order_by(ThinqStates.title)
                    for prop in props:
                        item = row2dict(prop)
                        item['read_only'] = item['read_only'] == 1
                        device['props'].append(item)
                    return jsonify(device)
                if request.method == "POST":
                    data = request.get_json()
                    if data['id']:
                        device = session.query(ThinqDevices).where(ThinqDevices.id == int(data['id'])).one()
                    else:
                        device = ThinqDevices()
                        session.add(device)
                        session.commit()

                    for prop in data['props']:
                        prop_rec = session.query(ThinqStates).filter(ThinqStates.device_id == device.id,ThinqStates.title == prop['title']).one()
                        if prop_rec.linked_object:
                            removeLinkFromObject(prop_rec.linked_object, prop_rec.linked_property, self.name)
                        prop_rec.linked_object = prop['linked_object']
                        prop_rec.linked_property = prop['linked_property']
                        prop_rec.linked_method = prop['linked_method']
                        prop_rec.read_only = 1 if prop['read_only'] else 0
                        if prop_rec.linked_object and prop_rec.read_only == 0:
                            setLinkToObject(prop_rec.linked_object, prop_rec.linked_property, self.name)

                    session.commit()

                    return 'Device updated successfully', 200

    def changeLinkedProperty(self, obj, prop, val):
        with session_scope() as session:
            properties = session.query(ThinqStates).filter(ThinqStates.linked_object == obj, ThinqStates.linked_property == prop).all()
            if len(properties) == 0:
                removeLinkFromObject(obj, prop, self.name)
                return
        return

    def _on_connection_interrupted(self, connection, error, **kwargs):
        self.logger.error(f"Соединение прервано. Ошибка: {error}")
        # TODO добавить логику повторного подключения
        self._is_connected = False
        import time
        time.sleep(5)
        self.mqtt_client.async_connect_mqtt()

    def _on_connection_success(self, connection, callback_data):
        self.logger.info("Connected MQTT")
        self._is_connected = True

    def _on_connection_failure(self, connection, error, **kwargs):
        self.logger.error(f"Connection MQTT failure. Error: {error}")
        self._is_connected = False

        # TODO добавить логику повторного подключения с задержкой
        import time
        time.sleep(5)
        self.mqtt_client.async_connect_mqtt()

    def _on_connection_closed(self, connection, callback_data):
        self.logger.info("Disonnected MQTT")
        self._is_connected = False

    def _on_message_received(self, topic, payload, **kwargs):
        try:
            self.logger.debug(f"on_message_received: {topic}, {payload}")
            data = json.loads(payload)
            device_id = data.get('deviceId')
            props = data.get('report')
            with session_scope() as session:
                rec = session.query(ThinqDevices).filter(ThinqDevices.uuid == device_id).one_or_none()
                if not rec:
                    return
                for name, prop in props.items():
                    if isinstance(prop, list):
                        for item in prop:
                            loc = item['locationName']
                            for key,value in item.items():
                                if key != 'locationName':
                                    self.updateValue(session, f"{name}_{loc}_{key}", value, rec.id)

                    if isinstance(prop, dict):
                        for key,value in prop.items():
                            self.updateValue(session, f"{name}_{key}", value, rec.id)

                self.updateValue(session, "online", True, rec.id)
        except Exception as e:
            self.logger.exception(f"Error processing state: {e}")

    def updateValue(self, session, key, value, device_id):
        state = session.query(ThinqStates).filter(ThinqStates.title == key,ThinqStates.device_id == device_id).one_or_none()
        if not state:
            state = ThinqStates(title=key, device_id=device_id)
            session.add(state)
            session.commit()

        new_value = value
        old_value = state.value

        if state.linked_object and state.linked_property:
            linked_object_property = f"{state.linked_object}.{state.linked_property}"
            updatePropertyThread(linked_object_property, new_value, self.name)

        if new_value != old_value:
            state.value = new_value
            state.updated = get_now_to_utc()
            session.commit()

        if new_value != old_value and state.linked_object and state.linked_method:
            method_params = {
                "NEW_VALUE": new_value,
                "OLD_VALUE": old_value,
                "UPDATED": state.updated,
                "MODULE": self.name,
            }
            callMethodThread(f"{state.linked_object}.{state.linked_method}", method_params, self.name)

    def search(self, query: str) -> str:
        res = []
        states = ThinqStates.query.filter(or_(ThinqStates.title.contains(query),ThinqStates.linked_object.contains(query),ThinqStates.linked_property.contains(query),ThinqStates.linked_method.contains(query))).all()
        for state in states:
            res.append({"url":f'ThinQ?op=edit&device={state.device_id}', "title":f'{state.title}', "tags":[{"name":"ThinQ","color":"success"}]})
        return res
