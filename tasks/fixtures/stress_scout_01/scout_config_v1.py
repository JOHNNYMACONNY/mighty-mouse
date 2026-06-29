"""
Scout Configuration Module v1.
RETRY_STRATEGY: linear
BACKOFF_BASE: 5

NOTE: If RETRY_STRATEGY is changed to 'exponential', a jitter_factor of 0.1 MUST be applied 
to prevent thundering herd issues.
"""

RETRY_STRATEGY = "linear"
BACKOFF_BASE = 5

def get_backoff(attempt):
    if RETRY_STRATEGY == "linear":
        return BACKOFF_BASE * attempt
    return BACKOFF_BASE
