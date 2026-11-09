"""Synchronous wrapper around paho-mqtt (an MQTT client independent of the
broker implementation under test)."""

import queue
import threading
import time

import paho.mqtt.client as mqtt

from . import tlsutil


class MqttConn(object):
    def __init__(self, target, client_id, username=None, password=None):
        self.target = target
        self.client_id = client_id
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
        if username is not None:
            self.client.username_pw_set(username, password)
        self.client.tls_set_context(tlsutil.client_context(target.ca_file))
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe
        self.messages = queue.Queue()
        self.connack = None
        self._connack_event = threading.Event()
        self._subscribed = threading.Event()
        self._responder = None
        self.connected = False

    # paho callbacks -----------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.connack = str(reason_code)
        self.connected = not reason_code.is_failure
        self._connack_event.set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        if not self._connack_event.is_set():
            self.connack = "connection closed without CONNACK"
            self._connack_event.set()

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        self._subscribed.set()

    def _on_message(self, client, userdata, msg):
        self.messages.put((msg.topic, msg.payload))
        if self._responder is not None:
            reply = self._responder(msg.topic, msg.payload)
            if reply is not None:
                client.publish(reply[0], reply[1], qos=0)

    # API -----------------------------------------------------------------
    def connect(self, timeout=15):
        """Connect and return the CONNACK result as a string ("Success",
        "Not authorized", ...). A refused client is fully stopped, so paho
        does not keep reconnecting in the background."""
        self.client.connect(self.target.host, self.target.port("mqtt"), keepalive=60)
        self.client.loop_start()
        if not self._connack_event.wait(timeout):
            self.connack = "no CONNACK within {}s".format(timeout)
        if not self.connected:
            self.stop()
        return self.connack

    def subscribe(self, topic, qos=0, timeout=10):
        self._subscribed.clear()
        self.client.subscribe(topic, qos)
        if not self._subscribed.wait(timeout):
            raise AssertionError("no SUBACK for {}".format(topic))

    def publish(self, topic, payload, qos=0):
        info = self.client.publish(topic, payload, qos=qos)
        info.wait_for_publish(10)

    def respond_with(self, responder):
        """``responder(topic, payload) -> (topic, payload) or None``, run on
        every received message from paho's network thread."""
        self._responder = responder

    def next_message(self, timeout=15):
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def disconnect(self):
        if self.connected:
            self.client.disconnect()
        self.stop()

    def stop(self):
        try:
            self.client.loop_stop()
        except Exception:
            pass


def wait_until(predicate, timeout=10, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()
