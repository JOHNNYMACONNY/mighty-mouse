import os

class ConfigLoader:
    def load_config(self, defaults):
        config = {}
        for key, val in defaults.items():
            config[key] = os.environ.get(key, val)
        return config
