class DataPipeline:

    def __init__(self, data: list[dict]):
        self.data = data

    def clean_headers(self) -> list[dict]:
        # Bug: returns the cleaned list, but doesn't store it in self.data!
        cleaned = []
        for row in self.data:
            cleaned.append({k.lower().strip(): v for k, v in row.items()})
        return cleaned

    def calculate_total(self) -> list[dict]:
        # Bug: raises KeyError if keys aren't lowercase or are missing
        for row in self.data:
            row["total"] = float(row["price"]) * int(row["quantity"])
        return self.data

    def filter_inactive(self) -> list[dict]:
        return [row for row in self.data if row.get("status") == "active"]

    def run(self) -> list[dict]:
        self.clean_headers()
        self.calculate_total()
        return self.filter_inactive()
