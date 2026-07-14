from config_loader import load_settings


def request_timeout(environment):
    return load_settings(environment).timeout_seconds
