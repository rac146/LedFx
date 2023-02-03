import voluptuous as vol

from ledfx.effects.audio import AudioReactiveEffect
import logging
import numpy as np
from threading import Event, Thread

_LOGGER = logging.getLogger(__name__)


class Strobe(AudioReactiveEffect):
    COLORS = [[255, 0, 0], [255, 165, 0], [255, 255, 0], [0, 128, 0], [0, 0, 255], [128, 0, 128], [0, 255, 0]]

    NAME = "BPM Strobe NEW"
    CATEGORY = "BPM"

    CONFIG_SCHEMA = vol.Schema(
        {
            vol.Optional(
                "strobe_mode",
                description="Send beat detections or use a timer",
                default="beats",
            ): vol.In(list(["beats", "timer"])),
            vol.Optional(
                "timer_seconds",
                description="If timer - when to update (in seconds)",
                default=1,
            ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10)),
        }
    )

    def __init__(self, ledfx, config):
        super().__init__(ledfx, config)
        self.color_array = None
        self.strobe_mode = "beats"
        self.current_color = 0
        self.current_light = 0
        self.color = [0, 0, 0]
        self.timer_seconds = 1

    def on_activate(self, pixel_count):
        self.current_color = 0
        self.current_light = 0
        self.color_array = np.zeros((self.pixel_count, 3))
        self.strobe_mode = self._config["strobe_mode"]
        self.timer_seconds = self._config["timer_seconds"]

    def check_timer(self):
        if self.strobe_mode == "timer":
            try:
                self.timer()
            except:
                pass

            self.timer = self.strobe_timer(self.timer_seconds, self.update_color)
        else:
            try:
                self.timer()
            except:
                pass

    def strobe_timer(self, interval, func):
        stopped = Event()

        def loop():
            while not stopped.wait(interval):
                func()

        Thread(target=loop).start()
        return stopped.set

    def config_updated(self, config):
        self.strobe_mode = self._config["strobe_mode"]
        self.timer_seconds = self._config["timer_seconds"]
        self.check_timer()

    def audio_data_updated(self, data):
        o = data.beat_oscillator()

        if self.strobe_mode == "beats" and o == 0:
            self.update_color()

    def update_color(self):
        new_color = self.COLORS[self.current_color]

        self.color_array[self.current_light] = new_color

        self.current_light += 1

        if self.current_light == self.pixel_count:
            self.current_color += 1
            self.current_light = 0

        if len(self.COLORS) == self.current_color:
            self.current_color = 0

        self.color = self.color_array

    def render(self):
        self.pixels[:] = self.color
