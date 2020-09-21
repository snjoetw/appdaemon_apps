from unittest.mock import ANY, MagicMock, Mock

import pytest

from alarm_monitor import AlarmMonitor
from triggers import TriggerInfo


@pytest.fixture
def alarm_monitor(given_that):
    given_that.mock_functions_are_cleared()

    given_that.passed_arg('motion_entity_id') \
        .is_set_to(['binary_sensor.motion_1', 'binary_sensor.motion_2'])
    given_that.passed_arg('door_entity_id') \
        .is_set_to('binary_sensor.door')
    given_that.passed_arg('window_entity_id') \
        .is_set_to('binary_sensor.window')
    given_that.passed_arg('alarm_entity_id') \
        .is_set_to('alarm_control_panel.home_alarm')
    given_that.passed_arg('alarm_triggered_entity_id') \
        .is_set_to('input_text.alarm_triggered_entity_id')
    given_that.passed_arg('motion_notify_message') \
        .is_set_to('motion {{ friendly_name(trigger_info.data.entity_id) }}')
    given_that.passed_arg('default_notify_message') \
        .is_set_to('default {{ friendly_name(trigger_info.data.entity_id) }}')

    given_that.state_of('binary_sensor.motion_1') \
        .is_set_to('on', {'device_class': 'motion', 'friendly_name': 'Motion'})
    given_that.state_of('binary_sensor.motion_2') \
        .is_set_to('on', {'device_class': 'motion', 'friendly_name': 'Motion'})
    given_that.state_of('binary_sensor.door') \
        .is_set_to('on', {'device_class': 'door', 'friendly_name': 'Door'})
    given_that.state_of('binary_sensor.window') \
        .is_set_to('on', {'device_class': 'window', 'friendly_name': 'Window'})

    alarm_monitor = AlarmMonitor(None, None, None, None, None, None, None,
                                 None)
    alarm_monitor.initialize()

    alarm_monitor.get_app = MagicMock(name='get_app')
    alarm_monitor.get_app.return_value = Mock()

    return alarm_monitor


def test_should_register_motion_entity_id_state(alarm_monitor, assert_that):
    assert_that(alarm_monitor) \
        .listens_to.state('binary_sensor.motion_1', new='on') \
        .with_callback(ANY)

    assert_that(alarm_monitor) \
        .listens_to.state('binary_sensor.motion_2', new='on') \
        .with_callback(ANY)


def test_should_register_door_entity_id_state(alarm_monitor, assert_that):
    assert_that(alarm_monitor) \
        .listens_to.state('binary_sensor.door', new='on') \
        .with_callback(ANY)


def test_should_register_window_entity_id_state(alarm_monitor, assert_that):
    assert_that(alarm_monitor) \
        .listens_to.state('binary_sensor.window', new='on') \
        .with_callback(ANY)


def test_should_trigger_alarm_when_armed_away_and_motion_is_on(given_that,
                                                               alarm_monitor,
                                                               assert_that):
    expect_home_alarm_state(given_that, 'armed_away')

    trigger_info = create_trigger_info('binary_sensor.motion_1')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_executed(assert_that, trigger_info)
    assert_motion_alarm_notifier_message(trigger_info, alarm_monitor)


def test_should_trigger_alarm_when_armed_away_and_window_is_opened(given_that,
                                                                   alarm_monitor,
                                                                   assert_that):
    expect_home_alarm_state(given_that, 'armed_away')

    trigger_info = create_trigger_info('binary_sensor.window')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_executed(assert_that, trigger_info)
    assert_window_alarm_notifier_message(trigger_info, alarm_monitor)


def test_should_trigger_alarm_when_armed_away_and_door_is_opened(given_that,
                                                                 alarm_monitor,
                                                                 assert_that):
    expect_home_alarm_state(given_that, 'armed_away')

    trigger_info = create_trigger_info('binary_sensor.door')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_executed(assert_that, trigger_info)
    assert_door_alarm_notifier_message(trigger_info, alarm_monitor)


def test_should_not_trigger_alarm_when_disarmed_and_motion_is_on(given_that,
                                                                 alarm_monitor,
                                                                 assert_that):
    expect_home_alarm_state(given_that, 'disarmed')

    trigger_info = create_trigger_info('binary_sensor.motion_1')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_not_executed(assert_that)


def test_should_not_trigger_alarm_when_disarmed_and_window_is_opened(
        given_that,
        alarm_monitor,
        assert_that):
    expect_home_alarm_state(given_that, 'disarmed')

    trigger_info = create_trigger_info('binary_sensor.window')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_not_executed(assert_that)


def test_should_not_trigger_alarm_when_disarmed_and_door_is_opened(given_that,
                                                                   alarm_monitor,
                                                                   assert_that):
    expect_home_alarm_state(given_that, 'disarmed')

    trigger_info = create_trigger_info('binary_sensor.door')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_not_executed(assert_that)


def test_should_not_trigger_alarm_when_armed_home_and_motion_is_on(given_that,
                                                                   alarm_monitor,
                                                                   assert_that):
    expect_home_alarm_state(given_that, 'armed_home')

    trigger_info = create_trigger_info('binary_sensor.motion_2')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_not_executed(assert_that)


def test_should_trigger_alarm_when_armed_home_and_window_is_opened(given_that,
                                                                   alarm_monitor,
                                                                   assert_that):
    expect_home_alarm_state(given_that, 'armed_home')

    trigger_info = create_trigger_info('binary_sensor.window')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_executed(assert_that, trigger_info)
    assert_window_alarm_notifier_message(trigger_info, alarm_monitor)


def test_should_trigger_alarm_when_armed_home_and_door_is_opened(given_that,
                                                                 alarm_monitor,
                                                                 assert_that):
    expect_home_alarm_state(given_that, 'armed_home')

    trigger_info = create_trigger_info('binary_sensor.door')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_executed(assert_that, trigger_info)
    assert_door_alarm_notifier_message(trigger_info, alarm_monitor)


def test_should_trigger_alarm_and_set_triggered_entity_id(given_that,
                                                          alarm_monitor,
                                                          assert_that):
    expect_home_alarm_state(given_that, 'armed_home')

    trigger_info = create_trigger_info('binary_sensor.door')
    alarm_monitor.trigger_handler(trigger_info)

    assert_alarm_triggered_actions_executed(assert_that, trigger_info)
    assert_door_alarm_notifier_message(trigger_info, alarm_monitor)


def create_trigger_info(triggered_entity_id):
    return TriggerInfo('state', data={
        'entity_id': triggered_entity_id
    })


def expect_home_alarm_state(given_that, expected_state):
    given_that.state_of('alarm_control_panel.home_alarm').is_set_to(
        expected_state)


def assert_alarm_triggered_actions_executed(assert_that, trigger_info):
    assert_that('alarm_control_panel/alarm_trigger').was.called_with(
        entity_id='alarm_control_panel.home_alarm'
    )

    assert_that('input_text/set_value').was.called_with(
        entity_id='input_text.alarm_triggered_entity_id',
        value=trigger_info.data.get('entity_id')
    )


def assert_alarm_triggered_actions_not_executed(assert_that):
    assert_that('alarm_control_panel/alarm_trigger').was_not.called_with(
        entity_id=ANY)

    assert_that('input_text/set_value').was_not.called_with(
        entity_id=ANY,
        value=ANY
    )


def assert_motion_alarm_notifier_message(trigger_info, alarm_monitor):
    alarm_monitor.get_app.assert_called_once_with('alarm_notifier')
    alarm_monitor.get_app('alarm_notifier').send.assert_called_once_with(
        'motion Motion',
        trigger_info.data.get('entity_id'),
        (),
        None)


def assert_window_alarm_notifier_message(trigger_info, alarm_monitor):
    alarm_monitor.get_app.assert_called_once_with('alarm_notifier')
    alarm_monitor.get_app('alarm_notifier').send.assert_called_once_with(
        'default Window',
        trigger_info.data.get('entity_id'),
        (),
        None)


def assert_door_alarm_notifier_message(trigger_info, alarm_monitor):
    alarm_monitor.get_app.assert_called_once_with('alarm_notifier')
    alarm_monitor.get_app('alarm_notifier').send.assert_called_once_with(
        'default Door',
        trigger_info.data.get('entity_id'),
        (),
        None)
