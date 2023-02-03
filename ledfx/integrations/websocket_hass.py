import logging

import asyncio
import paho.mqtt.client as mqtt
import voluptuous as vol
import struct
import numpy as np
from aiohttp import WSMsgType

from ledfx.events import SceneActivatedEvent, Event
import json
import aiohttp

# from ledfx.events import Event
from ledfx.integrations import Integration
from ledfx.utils import async_fire_and_forget

_LOGGER = logging.getLogger(__name__)


class HASSWebSocket(Integration):
    """HASS Websocket Integration"""

    NAME = "HASS Websocket"
    DESCRIPTION = "Home Assistant Websocket Integration"

    CONFIG_SCHEMA = vol.Schema(
        {
            vol.Required(
                "name",
                description="Name of this integration instance and associated settings",
                default="Home Assistant WebSocket",
            ): str,
            vol.Required(
                "ip_address",
                description="HASS ip address",
                default="127.0.0.1",
            ): str,
            vol.Required(
                "access_token",
                description="HASS Access Token",
                default="",
            ): str,
            vol.Required(
                "port", description="HASS WebSocket port", default=8123
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        }
    )

    def __init__(self, ledfx, config, active, data):
        super().__init__(ledfx, config, active, data)

        self._connect_task = None
        self._ledfx = ledfx
        self._config = config
        self._client = None
        self._data = []
        self._listeners = []
        _LOGGER.info(f"CONFIG: {self._config}")

    def on_connect(self, client, userdata, flags, rc):
        _LOGGER.info("Connecting2")
        _LOGGER.info("Connected with result code " + str(rc))

    async def toggle_event(self, data, light_entity):
        _LOGGER.info("Event sent! " + str(data))
        if self._client is not None:
            await self._client.send_light_event(data[0].tolist(), light_entity)

        return True

    def on_websocket_message(self, msg):
        _LOGGER.info(str(msg))

    async def on_websocket_connected(self):
        await super().connect(f"Connected to Hass websocket")
        self._ledfx.events.fire_event(Event("hass_websocket"))

    async def connect(self):
        _LOGGER.info("Connecting1")

        url = f"ws://{self._config['ip_address']}:{self._config['port']}/api/websocket"
        access_token = self._config['access_token']

        if self._client is None:
            self._client = HassWebsocketClient(url, access_token, self.on_websocket_connected)
        self._cancel_connect()
        self._connect_task = asyncio.create_task(self._client.begin(self.on_websocket_message))

    def _cancel_connect(self):
        if self._connect_task is not None:
            self._connect_task.cancel()
            self._connect_task = None

    async def disconnect(self):
        if self._client is not None:
            # fire and forget bc for some reason close() never returns... -o-
            async_fire_and_forget(
                self._client.disconnect(), loop=self._ledfx.loop
            )
            self._cancel_connect()
            await super().disconnect("Disconnected from Hass websocket")
        else:
            await super().disconnect()


class HassWebsocketClient:
    def __init__(self, url, access_token, connected_callback):
        super().__init__()
        self.websocket = None
        self.url = url
        self.session = aiohttp.ClientSession()
        self.access_token = access_token
        self.id = 1
        self.connected_callback = connected_callback

    async def connect_and_receive(self):
        """Connect to the WebSocket."""
        async with self.session.ws_connect(self.url) as self.websocket:

            async for msg in self.websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    resp = json.loads(msg.data)
                    if resp["type"] == 'close':
                        await self.websocket.close()
                        break
                    if resp["type"] == "auth_required":
                        await self.auth()
                    if resp["type"] == "auth_ok":
                        await self.connected_callback()
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    raise Exception("Websocket error")
                    break

    async def disconnect(self):
        if self.websocket is not None:
            await self.websocket.close()

    async def begin(self, callback):
        """Connect and indefinitely read from websocket, returning messages to callback func"""
        self.id = 1

        """for now, if disconnected, just try to reconnect automatically"""
        while True:
            try:
                await self.connect_and_receive()
            except Exception as e:
                _LOGGER.info(str(e))

            await asyncio.sleep(2)

    async def auth(self):

        token_info = {
              "type": "auth",
              "access_token": self.access_token
        }

        token_info_json = json.dumps(token_info)

        await self.send(token_info_json)

    async def query(self, message):
        """Send a message, and return the response"""
        await self.send(message)
        result = await self.receive()
        return result.lstrip("QLC+API|")

    async def send_light_event(self, color_data, light_entity):
        light_event = {
            "id": self.id,
            "type": "call_service",
            "domain": "light",
            "service": "turn_on",
            "service_data": {
                "rgb_color": color_data
            },
            "target": {
                "entity_id": f"light.{light_entity}"
            }
        }

        self.id += 1

        light_json = json.dumps(light_event)

        await self.send(light_json)

    async def send(self, message):
        """Send a message to the WebSocket."""
        if self.websocket is None:
            _LOGGER.error("Websocket not yet established")
            return

        await self.websocket.send_str(message)
        # Every call to the logger is a performance hit
        # _LOGGER.debug(f"Sent message {message}")

    async def receive(self):
        """Receive one message from the WebSocket."""
        if self.websocket is None:
            _LOGGER.error("Websocket not yet established")
            return

        return (await self.websocket.receive()).data

    async def read(self, callback):
        """Read messages from the WebSocket."""
        if self.websocket is None:
            _LOGGER.error("Websocket not yet established")
            return

        while message := await self.websocket.receive():
            if message.type is WSMsgType.TEXT:
                _LOGGER.info(message.data)
            # if message.type == aiohttp.WSMsgType.TEXT:
            #     self.callback(message)
            # elif message.type == aiohttp.WSMsgType.CLOSED:
            #     break
            # elif message.type == aiohttp.WSMsgType.ERROR:
            #     break
