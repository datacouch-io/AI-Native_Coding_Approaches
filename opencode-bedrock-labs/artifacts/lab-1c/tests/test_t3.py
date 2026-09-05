"""T3 acceptance - hidden from every model."""
import pytest
from solution import backoff_schedule


def test_plain_exponential():
    assert backoff_schedule(4, 1.0, 2.0, 100.0, 1000.0) == [1.0, 2.0, 4.0, 8.0]

def test_cap_clamps_each_delay():
    assert backoff_schedule(5, 1.0, 3.0, 5.0, 1000.0) == [1.0, 3.0, 5.0, 5.0, 5.0]

def test_zero_attempts():
    assert backoff_schedule(0, 1.0, 2.0, 10.0, 10.0) == []

def test_budget_truncates_last_delay():
    # 1 + 2 + 4 = 7; a 4th delay of 8 would reach 15, budget is 10 -> truncated to 3
    assert backoff_schedule(4, 1.0, 2.0, 100.0, 10.0) == [1.0, 2.0, 4.0, 3.0]

def test_budget_exhausted_exactly_omits_zero_delay():
    # 1 + 2 + 4 = 7 exactly equals the budget; a 4th delay would be 0 -> omitted
    assert backoff_schedule(4, 1.0, 2.0, 100.0, 7.0) == [1.0, 2.0, 4.0]

def test_budget_smaller_than_first_delay():
    assert backoff_schedule(3, 5.0, 2.0, 100.0, 2.0) == [2.0]

def test_zero_budget_returns_empty():
    assert backoff_schedule(3, 1.0, 2.0, 10.0, 0.0) == []

def test_rounding_to_three_places():
    out = backoff_schedule(3, 0.1, 3.0, 100.0, 1000.0)
    assert out == [0.1, 0.3, 0.9]

def test_factor_one_is_constant():
    assert backoff_schedule(3, 2.0, 1.0, 100.0, 1000.0) == [2.0, 2.0, 2.0]

@pytest.mark.parametrize("kwargs", [
    {"attempts": -1}, {"attempts": 1.5}, {"base": -1.0},
    {"factor": -2.0}, {"cap": -5.0}, {"max_elapsed": -1.0},
])
def test_invalid_inputs_raise(kwargs):
    args = {"attempts": 3, "base": 1.0, "factor": 2.0, "cap": 10.0, "max_elapsed": 100.0}
    args.update(kwargs)
    with pytest.raises(ValueError):
        backoff_schedule(**args)
