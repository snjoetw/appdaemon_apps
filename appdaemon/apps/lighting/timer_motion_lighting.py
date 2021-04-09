from datetime import datetime, timedelta

from lib.core.monitored_callback import monitored_callback
from lib.triggers import TriggerInfo
from lighting.motion_lighting import MotionLighting

CHECK_FREQUENCY = 300


class TimerSettings:
    def __init__(self, config):
        self._turn_on_start_time = config['turn_on_start_time']
        self._turn_on_end_time = config['turn_on_end_time']

    @property
    def turn_on_start_time(self):
        return self._turn_on_start_time

    @property
    def turn_on_end_time(self):
        return self._turn_on_end_time


class TimerMotionLighting(MotionLighting):
    _timer_settings: TimerSettings

    def initialize(self):
        super().initialize()

        self._timer_settings = TimerSettings(self.cfg.value('timer'))

        now = datetime.now() + timedelta(seconds=2)
        self.run_every(self._run_every_handler, now, CHECK_FREQUENCY)

    @monitored_callback
    def _run_every_handler(self, time=None, **kwargs):
        trigger_info = TriggerInfo("time", {
            "time": time,
        })

        if self._is_in_timer_turn_off_period():
            self._turn_off_lights(trigger_info)
            return

        if not self._is_in_timer_period():
            return

        self._cancel_turn_off_delay()
        self._turn_on_lights()

    def _is_in_timer_period(self):
        period = self._timer_settings
        return self.now_is_between(period.turn_on_start_time, period.turn_on_end_time)

    def _is_in_timer_turn_off_period(self):
        turn_on_end_time = self.parse_datetime(self._timer_settings.turn_on_end_time)
        turn_off_time_end = datetime.now()
        turn_off_time_start = turn_off_time_end - timedelta(seconds=CHECK_FREQUENCY)
        is_in_timer_turn_off_period = turn_off_time_start <= turn_on_end_time <= turn_off_time_end

        self.debug('in_timer_turn_off_period={}, turn_off_start={}, turn_off_end={}, turn_on_end_time={}'.format(
            is_in_timer_turn_off_period,
            turn_off_time_start,
            turn_off_time_end,
            turn_on_end_time,
        ))

        return is_in_timer_turn_off_period

    def _should_turn_on_lights(self, trigger_info):
        if self._is_in_timer_period():
            return False

        return super()._should_turn_on_lights(trigger_info)

    def _should_turn_off_lights(self, trigger_info):
        if self._is_in_timer_period():
            return False

        return super()._should_turn_off_lights(trigger_info)
