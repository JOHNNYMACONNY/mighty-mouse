from paginator import get_page


def test_empty_items():
    assert get_page([], 1, 5) == []


def test_page_one():
    items = list(range(10))
    assert get_page(items, 1, 5) == [0, 1, 2, 3, 4]


def test_page_two():
    items = list(range(10))
    assert get_page(items, 2, 5) == [5, 6, 7, 8, 9]


def test_out_of_bounds():
    items = list(range(10))
    assert get_page(items, 3, 5) == []


def test_page_zero_or_negative():
    items = list(range(10))
    assert get_page(items, 0, 5) == []
    assert get_page(items, -1, 5) == []
