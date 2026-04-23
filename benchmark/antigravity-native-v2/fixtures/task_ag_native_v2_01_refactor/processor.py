from loader import DataLoader
from parser import DataParser

class DataProcessor:
    def __init__(self):
        self._loader = DataLoader()
        self._parser = DataParser()

    def process(self, source):
        raw_data = self._loader.load(source)
        return self._parser.parse(raw_data)
