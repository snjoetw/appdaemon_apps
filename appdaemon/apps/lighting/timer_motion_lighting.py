from datetime import datetime, timedelta

from lib.core.monitored_callback import monitored_callback
from lib.triggers import TriggerInfo
from lighting.motion_lighting import MotionLighting

CHECK_FREQUENCY = 900

TIMER_ACTION_TURN_ON = 'timer_action_turn_on'
TIMER_ACTION_TURN_OFF = 'timer_action_turn_off'


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
        if not self.is_enabled:
            return

        trigger_info = TriggerInfo("time", {
            "time": time,
        })

        action = self._figure_timer_action()

        if action == TIMER_ACTION_TURN_OFF:
            self._turn_off_lights(trigger_info)
        elif action == TIMER_ACTION_TURN_ON:
            self._cancel_turn_off_delay()
            self._turn_on_lights()

    def _figure_timer_action(self):
        action_period_end = datetime.now().time()
        action_period_start = (datetime.now() - timedelta(seconds=CHECK_FREQUENCY)).time()

        turn_on_start_time = self.parse_datetime(self._timer_settings.turn_on_start_time).time()
        if action_period_start <= turn_on_start_time <= action_period_end:
            return TIMER_ACTION_TURN_ON

        turn_on_end_time = self.parse_datetime(self._timer_settings.turn_on_end_time).time()
        if action_period_start <= turn_on_end_time <= action_period_end:
            return TIMER_ACTION_TURN_OFF

        return None

    def _is_in_timer_period(self):
        period = self._timer_settings
        return self.now_is_between(period.turn_on_start_time, period.turn_on_end_time)

    def _should_turn_on_lights(self, trigger_info):
        if self._is_in_timer_period():
            return False

        return super()._should_turn_on_lights(trigger_info)

    def _should_turn_off_lights(self, trigger_info):
        if self._is_in_timer_period():
            return False

        return super()._should_turn_off_lights(trigger_info)
