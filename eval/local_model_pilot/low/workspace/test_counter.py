from counter import bounded_increment


def test_increments_below_limit():
    assert bounded_increment(2, 5) == 3


def test_stops_at_limit():
    assert bounded_increment(5, 5) == 5


def test_stops_above_limit():
    assert bounded_increment(7, 5) == 5
