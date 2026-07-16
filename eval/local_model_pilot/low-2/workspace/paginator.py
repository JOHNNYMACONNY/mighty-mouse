def get_page(items: list, page: int, page_size: int) -> list:
    """Return the items on the given 1-indexed page.
    
    If items is empty, return an empty list.
    If page is out of range, return an empty list.
    """
    if not items:
        return []
    if page < 1:
        return []
    start = (page - 1) * page_size
    # Bug: off-by-one error (should be start + page_size)
    end = start + page_size - 1 
    if start >= len(items):
        return []
    return items[start:end]
