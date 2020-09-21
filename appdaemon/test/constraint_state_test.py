import unittest
from unittest.mock import Mock

from constraints import get_constraint
from triggers import TriggerInfo


def create_constraint(expected_state, actual_state):
    app = Mock(**{'get_state.return_value': actual_state})
    return get_constraint(app, {
        'platform': 'state',
        'entity_id': 'input_number.test',
        'state': expected_state
    })


class TestStateConstraint(unittest.TestCase):

    def test_numeric_state_value_match(self):
        constraint = create_constraint(11, 11)
        result = constraint.check(TriggerInfo('state'))
        self.assertTrue(result)

    def test_numeric_state_value_not_match(self):
        constraint = create_constraint(11, 12)
        result = constraint.check(TriggerInfo('state'))
        self.assertFalse(result)

    def test_string_state_value_match(self):
        constraint = create_constraint('Open', 'Open')
        result = constraint.check(TriggerInfo('state'))
        self.assertTrue(result)

    def test_string_state_value_not_match(self):
        constraint = create_constraint('Open', 'Close')
        result = constraint.check(TriggerInfo('state'))
        self.assertFalse(result)

    def test_state_with_greater_or_equal_operator_value_match(self):
        constraint = create_constraint('>=11', 11)
        result = constraint.check(TriggerInfo('state'))
        self.assertTrue(result)

    def test_state_with_greater_or_equal_operator_value_not_match(self):
        constraint = create_constraint('>=11', 10)
        result = constraint.check(TriggerInfo('state'))
        self.assertFalse(result)

    def test_state_with_greater_operator_value_match(self):
        constraint = create_constraint('>11', 12)
        result = constraint.check(TriggerInfo('state'))
        self.assertTrue(result)

    def test_state_with_greater_operator_value_not_match(self):
        constraint = create_constraint('>11', 11)
        result = constraint.check(TriggerInfo('state'))
        self.assertFalse(result)

    def test_state_with_less_or_equal_operator_value_match(self):
        constraint = create_constraint('<=11', 11)
        result = constraint.check(TriggerInfo('state'))
        self.assertTrue(result)

    def test_state_with_less_or_equal_operator_value_not_match(self):
        constraint = create_constraint('<=11', 12)
        result = constraint.check(TriggerInfo('state'))
        self.assertFalse(result)

    def test_state_with_less_operator_value_match(self):
        constraint = create_constraint('<11', 10)
        result = constraint.check(TriggerInfo('state'))
        self.assertTrue(result)

    def test_state_with_less_operator_value_not_match(self):
        constraint = create_constraint('<11', 11)
        result = constraint.check(TriggerInfo('state'))
        self.assertFalse(result)

    def test_state_list_match(self):
        constraint = create_constraint(['open', 'opening'], 'open')
        result = constraint.check(TriggerInfo('state'))
        self.assertTrue(result)

    def test_state_list_not_match(self):
        constraint = create_constraint(['open', 'opening'], 'closing')
        result = constraint.check(TriggerInfo('state'))
        self.assertFalse(result)
