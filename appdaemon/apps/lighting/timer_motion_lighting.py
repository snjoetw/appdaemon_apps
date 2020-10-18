from datetime import datetime, timedelta

from lighting.motion_lighting2 import MotionLighting

CHECK_FREQUENCY = 300


class TimerMotionLighting(MotionLighting):

    def initialize(self):
        super().initialize()

        self.timer_settings = ImageProcessingSettings(self.arg('timer'))

        now = datetime.now() + timedelta(seconds=2)
        self.run_every(self.run_every_handler, now, CHECK_FREQUENCY)

    def run_every_handler(self, time=None, **kwargs):
        if self.is_in_timer_turn_off_period():
            self.turn_off_lights()
            return

        if not self.is_in_timer_period():
            return

        self.cancel_turn_off_delay()
        self.turn_on_lights()

    def is_in_timer_period(self):
        period = self.timer_settings
        return self.now_is_between(period.turn_on_start_time, period.turn_on_end_time)

    def is_in_timer_turn_off_period(self):
        turn_on_end_time = self.parse_datetime(self.timer_settings.turn_on_end_time)
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

    def should_turn_on_lights(self, trigger_info):
        if self.is_in_timer_period():
            return False

        return super().should_turn_on_lights(trigger_info)

    def should_turn_off_lights(self, trigger_info):
        if self.is_in_timer_period():
            return False

        return super().should_turn_off_lights(trigger_info)


class ImageProcessingSettings:
    def __init__(self, config):
        self._turn_on_start_time = config['turn_on_start_time']
        self._turn_on_end_time = config['turn_on_end_time']

    @property
    def turn_on_start_time(self):
        return self._turn_on_start_time

    @property
    def turn_on_end_time(self):
        return self._turn_on_end_time
