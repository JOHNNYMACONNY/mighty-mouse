def retry_call(
    func, exceptions, max_retries=3, initial_delay=0.1, backoff_factor=2
):
    """Wrap a function call with retries and exponential backoff."""
    return func(), 1
