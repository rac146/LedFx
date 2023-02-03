import asyncio
import logging
import socket

import numpy as np
import voluptuous as vol

from ledfx.devices import Device, packets
from ledfx.events import DevicesUpdatedEvent
from ledfx.utils import async_fire_and_forget

_LOGGER = logging.getLogger(__name__)


class MQTTDEVICE(Device):
    """MQTT protocol device support"""

    @staticmethod
    @property
    def CONFIG_SCHEMA():
        return vol.Schema(
            {
                vol.Required(
                    "name", description="Friendly name for the device"
                ): str,
                vol.Required(
                    "pixel_count",
                    description="Number of individual pixels",
                    default=1,
                ): vol.All(int, vol.Range(min=1)),
            }
        )

    def __init__(self, ledfx, config):
        super().__init__(ledfx, config)
        self.integration = None
        self._ledfx = ledfx
        self._online = True
        self.listener = None
        self.last_frame = np.full((config["pixel_count"], 3), -1)

    def websocket_connected(self, event):
        _LOGGER.info("test connect")
        self.integration = self._ledfx.integrations.get("home-assistant-websocket")

    def activate(self):
        try:

            self.listener = self._ledfx.events.add_listener(
                self.websocket_connected,
                "hass_websocket",
            )

            try:
                self._online = True
                self.integration = self._ledfx.integrations.get("home-assistant-websocket")

            except (ConnectionRefusedError, TimeoutError):
                _LOGGER.warning(
                    f"{self.openrgb_device_id} not reachable. Is the api server running?"
                )
                self._online = False
                return
            # check for eedevice

        except ImportError:
            _LOGGER.critical("Unable to load openrgb library")
            self.deactivate()
        except IndexError:
            _LOGGER.critical(
                f"Couldn't find OpenRGB device ID: {self.openrgb_device_id}"
            )
            self._online = False
            self.deactivate()
        except ValueError:
            _LOGGER.critical(
                f"{self.openrgb_device_id} doesn't support direct mode, and isn't suitable for streamed effects from LedFx"
            )
            self.deactivate()
        else:
            self._online = True
            super().activate()

    def deactivate(self):
        super().deactivate()

        self.listener()

    def flush(self, data):
        """Flush LED data to the strip"""
        try:
            # _LOGGER.info(self.name)

            if self.integration and not np.array_equal(data, self.last_frame):
                async_fire_and_forget(self.integration.toggle_event(data, self.name), self._ledfx.loop)

            self.last_frame = np.copy(data)
            return
        except AttributeError:
            self.activate()
        except ConnectionAbortedError:
            _LOGGER.warning(f"Device disconnected: {self.openrgb_device_id}")
            self._ledfx.events.fire_event(DevicesUpdatedEvent(self.id))
            self._online = False
            self.deactivate()

    @staticmethod
    def send_out(sock: socket.socket, data: np.ndarray, device_id: int):
        _LOGGER.info("Not implemented")
