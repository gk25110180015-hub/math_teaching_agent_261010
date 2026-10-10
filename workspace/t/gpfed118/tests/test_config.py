from math_agent.config import text_budgets
from math_agent.settings import Settings
import pytest


def test_yaml_single_backslash_and_validated_budgets():
    value=text_budgets()
    assert value.footnotesize.hard==400 and value.calibration_status=='uncalibrated'


def test_settings_refuses_public_host_and_unbounded_retries():
    with pytest.raises(ValueError):Settings(host='0.0.0.0')
    with pytest.raises(ValueError):Settings(max_network_retries=20)
