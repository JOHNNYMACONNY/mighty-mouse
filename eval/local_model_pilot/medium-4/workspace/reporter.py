import json


class ReportGenerator:

    def __init__(self, data: list[dict]):
        self.data = data

    def export_json(self) -> str:
        return json.dumps(self.data)
