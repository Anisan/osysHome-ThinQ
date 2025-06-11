import json
import os
from flask import redirect, render_template, request, jsonify
from sqlalchemy import or_
from app.authentication.handlers import handle_admin_required
from app.database import session_scope
from app.database import row2dict, get_now_to_utc
from app.core.main.BasePlugin import BasePlugin
from app.core.lib.object import callMethodThread, updatePropertyThread, setLinkToObject, removeLinkFromObject
from app.core.lib.cache import findInCache, getFullFilename
from app.core.lib.common import addNotify, CategoryNotify
from plugins.ThinQ.models.ThinqDevices import ThinqDevices
from plugins.ThinQ.models.ThinqStates import ThinqStates
from plugins.ThinQ.thinq2.controller.auth import ThinQAuth
from plugins.ThinQ.thinq2.controller.thinq import ThinQ as ThinQClient

LANGUAGE_CODE = "ru-RU"
COUNTRY_CODE = "RU"

class ThinQ(BasePlugin):

    def __init__(self,app):
        super().__init__(app,__name__)
        self.title = "ThinQ"
        self.version = 1
        self.description = """LG ThinQ v2 protocol"""
        self.category = "Devices"
        self.actions = ['cycle','search']
        self._client = None
        self.is_connect = False
        self.auth = None
        self.cache_devices = {}

    def initialization(self):
        self.connect_thinq()

    def connect_thinq(self):
        try:
            token_file = findInCache("thinq.json", self.name)
            if token_file:
                # Создаем клиент
                with open(token_file, "r") as f:
                    config = json.load(f)
                    self._client = ThinQClient(config)
                # Назначаем функции обратного вызова
                self._client.mqtt.on_connect = self.on_connect
                self._client.mqtt.on_disconnect = self.on_disconnect
                self._client.mqtt.on_message = self.on_message
                self._client.mqtt.on_log = self.on_log
                # self._client.mqtt.on_device_message = self.on_device_message
                # Подключаемся к брокеру MQTT
                self._client.mqtt.connect()
                # Запускаем цикл обработки сообщений в отдельном потоке
                self._client.mqtt.loop_start()
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

        if op == "update":
            if not self._client:
                return redirect("ThinQ?op=auth")
            self.updateDevices()
            return redirect("ThinQ")

        if op == 'oauth_verifier':
            try:
                callback_url = request.args.get('url', '')
                self.auth.set_token_from_url(callback_url)
                thinq = ThinQClient(auth=self.auth)
                file_path = getFullFilename("thinq.json", self.name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w") as f:
                    json.dump(vars(thinq), f)
                self.auth = None
                self.connect_thinq()
            except Exception as ex:
                self.logger.exception(ex)
            return redirect("ThinQ")

        if op == 'auth':
            self.auth = ThinQAuth(language_code=LANGUAGE_CODE, country_code=COUNTRY_CODE)
            login_url = self.auth.oauth_login_url
            return self.render('thinq_auth.html', {"login_url": login_url})

        devices = ThinqDevices.query.all()
        devices = [row2dict(device) for device in devices]
        content = {
            "devices": devices,
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

    def cyclic_task(self):
        if self.event.is_set():
            pass
        else:
            if self._client:
                if not self.is_connect:
                    self.updateDevices()

            self.event.wait(5.0)

    def updateDevices(self):
        self.logger.debug("Get devices")
        if not self._client:
            return

        devices = self._client.mqtt.thinq_client.get_devices()

        if len(devices.items) == 0:
            self.logger.info("No devices found!")
            return

        with session_scope() as session:
            for device in devices.items:
                self.logger.debug("{}: {} (model {})".format(device.device_id, device.alias, device.model_name))
                rec = session.query(ThinqDevices).filter(ThinqDevices.uuid == device.device_id).one_or_none()
                if not rec:
                    rec = ThinqDevices()
                    rec.uuid = device.device_id
                    session.add(rec)
                rec.alias = device.alias
                rec.device_type = device.device_type
                rec.model_name = device.model_name
                rec.model_protocol = device.model_protocol
                rec.online = device.online
                rec.updated = get_now_to_utc()
                rec.image = device.image_url
                session.commit()

                try:
                    self.logger.debug(device)
                    state = device.snapshot.state
                    self.logger.debug(state)
                    for key, value in device.snapshot.state.items():
                        self.updateValue(session, key, value, rec.id)
                except Exception as error:
                    self.logger.error("Error: " + str(error))

    def mqttPublish(self, topic, value, qos=0, retain=False):
        self.logger.debug("Pubs: %s - %s",topic,value)
        self._client.publish(topic, str(value), qos=qos, retain=retain)

    def changeLinkedProperty(self, obj, prop, val):
        with session_scope() as session:
            properties = session.query(ThinqStates).filter(ThinqStates.linked_object == obj, ThinqStates.linked_property == prop).all()
            if len(properties) == 0:
                removeLinkFromObject(obj, prop, self.name)
                return
        return

    # Функция обратного вызова для подключения к брокеру MQTT
    def on_connect(self,client, userdata, flags, rc, properties):
        self.logger.info("Connected with result code " + str(rc))
        self.is_connect = True

    def on_disconnect(self, client, userdata, disconnect_flags, rc, properties):
        self.is_connect = False
        addNotify("Disconnect MQTT",str(rc),CategoryNotify.Error,self.name)
        if rc == 0:
            self.logger.info("Disconnected gracefully.")
        elif rc == 1:
            self.logger.info("Client requested disconnection.")
        elif rc == 2:
            self.logger.info("Broker disconnected the client unexpectedly.")
        elif rc == 3:
            self.logger.info("Client exceeded timeout for inactivity.")
        elif rc == 4:
            self.logger.info("Broker closed the connection.")
        else:
            self.logger.warning("Unexpected disconnection with code: %s", rc)

    def on_log(self, client, userdata, level, buf):
        import paho.mqtt.client as mqtt
        if level == mqtt.MQTT_LOG_ERR:
            self.logger.error(f"MQTT Error: {buf}")
        elif level == mqtt.MQTT_LOG_WARNING:
            self.logger.warning(f"MQTT Warning: {buf}")
        elif level == mqtt.MQTT_LOG_NOTICE:
            self.logger.info(f"MQTT Notice: {buf}")
        else:
            self.logger.debug(f"MQTT Debug: {buf}")

    def on_device_message(self, message):
        self.logger.debug("Action: %s", str(message))

    # Функция обратного вызова для получения сообщений
    def on_message(self,client, userdata, msg):
        self.logger.debug("Subs: %s - %s",msg.topic, str(msg.payload))
        try:
            with session_scope() as session:
                data = json.loads(str(msg.payload.decode("utf-8","ignore")))
                rec = session.query(ThinqDevices).filter(ThinqDevices.uuid == data['deviceId']).one_or_none()
                if not rec:
                    return
                rec.online = True
                rec.updated = get_now_to_utc()
                session.commit()
                dev_type = 'meta'
                if rec.device_type == 101:
                    dev_type = 'refState'
                elif rec.device_type == 201 or rec.device_type == 202:
                    dev_type = 'washerDryer'

                states = data['data']['state']['reported'][dev_type]
                for key, value in states.items():
                    self.updateValue(session, key, value, rec.id)

        except Exception as e:
            self.logger.error("Error processing message: %s", e, exc_info=True)

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
