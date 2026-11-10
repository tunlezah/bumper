#!/usr/bin/env python3

import logging
import asyncio
import os
from dataclasses import dataclass
from typing import Optional
from amqtt.adapters import StreamReaderAdapter, StreamWriterAdapter
from amqtt.broker import Broker
from amqtt.client import MQTTClient
from amqtt.errors import BrokerError
from amqtt.mqtt.constants import QOS_0, QOS_1, QOS_2
from amqtt.plugins.base import BaseAuthPlugin
import time
import bumper
from bumper import tls
import json
from datetime import datetime, timedelta
import bumper
from passlib.apps import custom_app_context as pwd_context

helperbotlog = logging.getLogger("helperbot")
boterrorlog = logging.getLogger("boterror")
mqttserverlog = logging.getLogger("mqttserver")


# --- amqtt internals ---------------------------------------------------------
# Everything Bumper needs to know about amqtt's session bookkeeping lives in
# the functions below, so that an amqtt upgrade that changes it breaks here,
# in one place, and in tests/test_mqtt_compat.py. They only use attributes
# without a leading underscore (Broker.sessions, Session.transitions,
# ProtocolHandler.session/.writer), but the *shape* of that data (a
# (Session, handler) tuple per client id, the state names) is not a documented
# API.


def broker_sessions(broker):
    """[(client_id, Session, BrokerProtocolHandler)] for every session the
    broker currently knows about, in insertion order."""
    return [(client_id, entry[0], entry[1]) for client_id, entry in broker.sessions.items()]


def session_state(session):
    """State name of an amqtt Session: 'new', 'connected' or 'disconnected'."""
    if session is None:
        return None
    return session.transitions.state


def broker_state(broker):
    """State name of an amqtt Broker: 'new', 'starting', 'started', 'not_started',
    'stopping', 'stopped' or 'not_stopped'."""
    return broker.transitions.state


def client_is_connected(client):
    """True while an MQTTClient's session is connected (replaces the legacy
    check of the private ``client._handler.writer``)."""
    return client is not None and session_state(client.session) == "connected"


async def close_session_connection(handler):
    """Close the network connection behind a broker-side protocol handler."""
    if handler is not None and handler.writer is not None:
        await handler.writer.close()


def release_sessions_of_connection(broker, writer_adapter):
    """Mark sessions still bound to a finished connection as disconnected.

    amqtt 0.12 registers a session and moves it to "connected" *before* it
    checks authentication; when authentication fails it closes the connection
    but leaves the session "connected" in ``Broker.sessions`` forever, so the
    status page would list failed logins as *connected* clients and the table
    would grow without bound. (The legacy broker kept them too, as "new".)
    Once a connection is over, any session whose handler still writes to it
    is stale; moving it to "disconnected" lets amqtt's own session monitor
    remove it, like any other disconnected clean session (see CHANGES.md,
    C-003).
    """
    released = []
    for client_id, session, handler in broker_sessions(broker):
        if handler is not None and handler.writer is writer_adapter and session_state(session) == "connected":
            session.transitions.disconnect()
            released.append(client_id)
    return released

class MQTTHelperBot:

    Client = None
    wait_resp_timeout_seconds = 10
    expire_msg_seconds = 10

    def __init__(self, address):
        self.address = address
        self.client_id = "helperbot@bumper/helperbot"
        self.command_responses = []

    async def start_helper_bot(self):

        try:
            if self.Client is None:
                self.Client = MQTTClient(
                    client_id=self.client_id, config={"check_hostname": False, "reconnect_retries": 20}
                )

            await self.Client.connect(
                "mqtts://{}:{}/".format(self.address[0], self.address[1]),
                cafile=bumper.ca_cert,
            )
            await self.Client.subscribe(
                [
                    ("iot/p2p/+/+/+/+/helperbot/bumper/helperbot/+/+/+", QOS_0),
                    ("iot/p2p/+", QOS_0),
                    ("iot/atr/+", QOS_0),
                ]
            )

#        except ConnectionRefusedError as e:
#            helperbotlog.Error(e)
#            pass

#        except asyncio.CancelledError as e:
#            pass

#        except amqtt.errors.ConnectError as e:
#            helperbotlog.Error(e)
#            pass

        except Exception as e:
            helperbotlog.exception("{}".format(e))

    async def wait_for_resp(self, requestid):
        try:

            t_end = (
                datetime.now() + timedelta(seconds=self.wait_resp_timeout_seconds)
            ).timestamp()

            while time.time() < t_end:
                await asyncio.sleep(0.1)
                if len(self.command_responses) > 0:
                    for msg in self.command_responses:
                        topic = str(msg["topic"]).split("/")
                        if topic[6] == "helperbot" and topic[10] == requestid:
                            if topic[11] == "j":
                                resppayload = json.loads(msg["payload"])
                            else:
                                resppayload = str(msg["payload"])
                            resp = {"id": requestid, "ret": "ok", "resp": resppayload}
                            self.command_responses.remove(msg)
                            return resp

            return {
                "id": requestid,
                "errno": 500,
                "ret": "fail",
                "debug": "wait for response timed out",
            }
        except asyncio.CancelledError as e:
            helperbotlog.debug("wait_for_resp cancelled by asyncio")
            return {
                "id": requestid,
                "errno": 500,
                "ret": "fail",
                "debug": "wait for response timed out",
            }
        except Exception as e:
            helperbotlog.exception("{}".format(e))
            return {
                "id": requestid,
                "errno": 500,
                "ret": "fail",
                "debug": "wait for response timed out",
            }

    async def send_command(self, cmdjson, requestid):
        if client_is_connected(self.Client):
            try:
                ttopic = "iot/p2p/{}/helperbot/bumper/helperbot/{}/{}/{}/q/{}/{}".format(
                    cmdjson["cmdName"],
                    cmdjson["toId"],
                    cmdjson["toType"],
                    cmdjson["toRes"],
                    requestid,
                    cmdjson["payloadType"],
                )
                try:
                    if cmdjson["payloadType"] == "x":
                        await self.Client.publish(
                            ttopic, str(cmdjson["payload"]).encode(), QOS_0
                        )

                    if cmdjson["payloadType"] == "j":
                        await self.Client.publish(
                            ttopic, json.dumps(cmdjson["payload"]).encode(), QOS_0
                        )

                except Exception as e:
                    helperbotlog.exception("{}".format(e))

                resp = await self.wait_for_resp(requestid)

                return resp

            except Exception as e:
                helperbotlog.exception("{}".format(e))
                return {}


class MQTTServer:
    default_config = None
    broker = None

    async def broker_coro(self):

        mqttserverlog.info(
            "Starting MQTT Server at {}:{}".format(self.address[0], self.address[1])
        )        

        try:
            await self.broker.start()

        except BrokerError as e:
            mqttserverlog.exception(e)
            #asyncio.create_task(bumper.shutdown())
            pass

        except Exception as e:
            mqttserverlog.exception("{}".format(e))
            #asyncio.create_task(bumper.shutdown())
            pass

    def __init__(self, address, **kwargs):
        try:
            self.address = address

            # Default config opts
            passwd_file = os.path.join(
                os.path.join(bumper.data_dir, "passwd")
            ) # For file auth, set user:hash in passwd file (passlib hashes, e.g. sha512_crypt)

            allow_anon = False

            for key, value in kwargs.items():
                if key == "password_file":
                    passwd_file = kwargs["password_file"]

                elif key == "allow_anonymous":
                    allow_anon = kwargs["allow_anonymous"] # Set to True to allow anonymous authentication

            # Initialize bot server
            self.default_config = {
                "listeners": {
                    # amqtt requires a "default" listener and would bind it to
                    # 0.0.0.0:1883 (plain MQTT) unless bind is explicitly None.
                    # The previous broker skipped bind-less listeners, so the
                    # legacy {"type": "tcp"} must not be ported verbatim.
                    "default": {"type": "tcp", "bind": None},
                    # The TLS socket is served by BumperBroker itself (see
                    # below); amqtt only needs to know the listener exists.
                    "tls1": {
                        "type": "external",
                        "bind": "{}:{}".format(address[0], address[1]),
                    },
                },
                # Plugins are loaded by dotted path. Listing them replaces
                # amqtt's defaults (incl. its anonymous-auth and $SYS
                # plugins), and the legacy "auth"/"topic-check" sections are
                # ignored when "plugins" is present, so the auth options live
                # in the plugin's own Config.
                "plugins": {
                    "bumper.mqttserver.BumperMQTTServer_Plugin": {  # provides auth and handling of bots/clients connecting
                        "allow_anonymous": allow_anon,
                        "password_file": passwd_file,
                    },
                },
            }

            self.broker = BumperBroker(
                config=self.default_config,
                tls_listener="tls1",
                bind=address,
            )

        except Exception as e:
            mqttserverlog.exception("{}".format(e))


class BumperBroker(Broker):
    """amqtt Broker whose TLS listener is an asyncio server owned by Bumper.

    amqtt builds its listener SSLContext itself from certfile/keyfile and
    offers no way to pass one in. So the "tls1" listener is declared as an
    amqtt *external* listener, and this class serves the TLS socket with
    Bumper's own SSLContext and hands every connection to the broker via the
    public ``Broker.external_connected``. The socket follows the broker's
    lifecycle: bound in ``start()`` before the broker starts (so bind errors
    surface as BrokerError, like before) and closed in ``shutdown()``.
    """

    def __init__(self, config, *, tls_listener, bind, **kwargs):
        super().__init__(config=config, **kwargs)
        self._bumper_tls_listener = tls_listener
        self._bumper_bind = bind
        self._bumper_tls_server = None

    def bumper_ssl_context(self):
        # Shared TLS policy; the MQTT listener always asked for an optional
        # client certificate, so it still does.
        return tls.server_context(bumper.server_cert, bumper.server_key, request_client_cert=True)

    async def start(self):
        try:
            self._bumper_tls_server = await asyncio.start_server(
                self._bumper_tls_connected,
                self._bumper_bind[0],
                self._bumper_bind[1],
                ssl=self.bumper_ssl_context(),
                reuse_address=True,
                start_serving=False,
            )
        except Exception as e:
            raise BrokerError("Broker instance can't be started: {}".format(e)) from e

        try:
            await super().start()
        except Exception:
            self._bumper_close_tls_server()
            raise
        await self._bumper_tls_server.start_serving()
        self.logger.info(
            "Listener '{}' bind to {}:{} (TLS, served by Bumper)".format(
                self._bumper_tls_listener, self._bumper_bind[0], self._bumper_bind[1]
            )
        )

    async def shutdown(self):
        self._bumper_close_tls_server()
        await super().shutdown()

    def _bumper_close_tls_server(self):
        if self._bumper_tls_server is not None:
            self._bumper_tls_server.close()
            self._bumper_tls_server = None

    async def _bumper_tls_connected(self, reader, writer):
        tls.log_connection("MQTT", writer.get_extra_info("peername"), writer.get_extra_info("ssl_object"))
        writer_adapter = StreamWriterAdapter(writer)
        try:
            await self.external_connected(StreamReaderAdapter(reader), writer_adapter, self._bumper_tls_listener)
        except Exception as e:
            mqttserverlog.exception("{}".format(e))
            writer.close()
        finally:
            for client_id in release_sessions_of_connection(self, writer_adapter):
                mqttserverlog.debug("Released stale session of finished connection: {}".format(client_id))


class BumperMQTTServer_Plugin(BaseAuthPlugin):
    @dataclass
    class Config:
        allow_anonymous: bool = False  # MQTTServer always sets this explicitly
        password_file: Optional[str] = None

    def __init__(self, context):
        super().__init__(context)
        try:
            # Same keys as the legacy broker config's "auth" section
            self.auth_config = {
                "allow-anonymous": self.config.allow_anonymous,
                "password-file": self.config.password_file,
            }
            self._users = dict()
            self._read_password_file()

        except Exception as e:
            mqttserverlog.exception("{}".format(e))

    async def authenticate(self, *, session):
        authenticated = False
        username = None

        try:
            username = session.username
            password = session.password
            client_id = session.client_id

            if "@" in client_id:
                didsplit = str(client_id).split("@")
                if not (  # if ecouser or bumper aren't in details it is a bot
                    "ecouser" in didsplit[1] or "bumper" in didsplit[1]
                ):
                    tmpbotdetail = str(didsplit[1]).split("/")
                    bumper.bot_add(
                        username,
                        didsplit[0],
                        tmpbotdetail[0],
                        tmpbotdetail[1],
                        "eco-ng",
                    )
                    mqttserverlog.info(f"Bumper Authentication Success - Bot - SN: {username} - DID: {didsplit[0]} - Class: {tmpbotdetail[0]}")                    
                    authenticated = True

                else:
                    tmpclientdetail = str(didsplit[1]).split("/")
                    userid = didsplit[0]
                    realm = tmpclientdetail[0]
                    resource = tmpclientdetail[1]

                    if userid == "helperbot":
                        mqttserverlog.info(f"Bumper Authentication Success - Helperbot: {client_id}")
                        authenticated = True
                    else:
                        auth = False
                        if bumper.check_authcode(didsplit[0], password):
                            auth = True
                        elif bumper.use_auth == False:
                            auth = True

                        if auth:
                            bumper.client_add(userid, realm, resource)
                            mqttserverlog.info(f"Bumper Authentication Success - Client - Username: {username} - ClientID: {client_id}")
                            authenticated = True

                        else:
                            authenticated = False

            # Check for File Auth            
            if username and not authenticated: # If there is a username and it isn't already authenticated
                hash = self._users.get(username, None)
                if hash: # If there is a matching entry in passwd, check hash
                    authenticated = pwd_context.verify(password, hash)
                    if authenticated:
                        mqttserverlog.info(f"File Authentication Success - Username: {username} - ClientID: {client_id}")
                    else:
                        mqttserverlog.info(f"File Authentication Failed - Username: {username} - ClientID: {client_id}")
                else:
                    mqttserverlog.info(f"File Authentication Failed - No Entry for Username: {username} - ClientID: {client_id}")

        except Exception as e:
            mqttserverlog.exception(
                "Session: {} - {}".format(session, e)
            )
            authenticated = False

        # Check for allow anonymous
        allow_anonymous = self.auth_config.get(
            "allow-anonymous", True
        )  
        if allow_anonymous and not authenticated: # If anonymous auth is allowed and it isn't already authenticated
            authenticated = True
            self.context.logger.debug(f"Anonymous Authentication Success: config allows anonymous - Username: {username}")
            mqttserverlog.info(f"Anonymous Authentication Success: config allows anonymous - Username: {username}")

        return authenticated

    def _read_password_file(self):
        password_file = self.auth_config.get('password-file', None)
        if password_file:
            try:
                with open(password_file) as f:
                    self.context.logger.debug(f"Reading user database from {password_file}")
                    for l in f:
                        line = l.strip()
                        if not line.startswith('#'):    # Allow comments in files
                            (username, pwd_hash) = line.split(sep=":", maxsplit=3)
                            if username:
                                self._users[username] = pwd_hash
                                self.context.logger.debug(f"user: {username} - hash: {pwd_hash}")
                self.context.logger.debug(f"{(len(self._users))} user(s) read from file {password_file}")
            except FileNotFoundError:
                self.context.logger.warning(f"Password file {password_file} not found")

    async def on_broker_client_connected(self, *, client_id, client_session):

        didsplit = str(client_id).split("@")

        bot = bumper.bot_get(didsplit[0])
        if bot:
            bumper.bot_set_mqtt(bot["did"], True)
            return

        clientresource = didsplit[1].split("/")[1]
        client = bumper.client_get(clientresource)
        if client:
            bumper.client_set_mqtt(client["resource"], True)
            return

    async def on_broker_message_received(self, *, client_id, message):
        self.handle_helperbot_msg(client_id, message)
        
    def handle_helperbot_msg(self, client_id, message):

            if str(message.topic).split("/")[6] == "helperbot":
                # Response to command
                helperbotlog.debug(
                    "Received Response - Topic: {} - Message: {}".format(
                        message.topic, str(message.data.decode("utf-8"))
                    )
                )
                bumper.mqtt_helperbot.command_responses.append(
                    {
                        "time": time.time(),
                        "topic": message.topic,
                        "payload": str(message.data.decode("utf-8")),
                    }
                )
            elif str(message.topic).split("/")[3] == "helperbot":
                # Helperbot sending command
                helperbotlog.debug(
                    "Send Command - Topic: {} - Message: {}".format(
                        message.topic, str(message.data.decode("utf-8"))
                    )
                )
            elif str(message.topic).split("/")[1] == "atr":
                # Broadcast message received on atr
                if str(message.topic).split("/")[2] == "errors":
                    boterrorlog.error(
                        "Received Error - Topic: {} - Message: {}".format(
                            message.topic, str(message.data.decode("utf-8"))
                        )
                    )
                else:
                    helperbotlog.debug(
                        "Received Broadcast - Topic: {} - Message: {}".format(
                            message.topic, str(message.data.decode("utf-8"))
                        )
                    )

            else:
                helperbotlog.debug(
                    "Received Message - Topic: {} - Message: {}".format(
                        message.topic, str(message.data.decode("utf-8"))
                    )
                )

            # Cleanup "expired messages" > 60 seconds from time
            for msg in bumper.mqtt_helperbot.command_responses:
                expire_time = (
                    datetime.fromtimestamp(msg["time"])
                    + timedelta(seconds=bumper.mqtt_helperbot.expire_msg_seconds)
                ).timestamp()
                if time.time() > expire_time:
                    helperbotlog.debug(
                        "Pruning Message Due To Expiration - Message Topic: {}".format(
                            msg["topic"]
                        )
                    )
                    bumper.mqtt_helperbot.command_responses.remove(msg)


    async def on_broker_client_disconnected(self, *, client_id, client_session):

        didsplit = str(client_id).split("@")

        bot = bumper.bot_get(didsplit[0])
        if bot:
            bumper.bot_set_mqtt(bot["did"], False)
            return

        clientresource = didsplit[1].split("/")[1]
        client = bumper.client_get(clientresource)
        if client:
            bumper.client_set_mqtt(client["resource"], False)
            return
