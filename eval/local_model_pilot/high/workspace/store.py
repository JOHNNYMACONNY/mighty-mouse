import json
from pathlib import Path


class CompletionStore:
    def __init__(self, path):
        self.path = Path(path)

    def completed_ids(self):
        if not self.path.exists():
            return set()
        payload = json.loads(self.path.read_text())
        return set(payload.get("completed", []))

    def mark_completed(self, job_id):
        completed = self.completed_ids()
        completed.add(job_id)
        self.path.write_text(json.dumps({"completed": sorted(completed)}))
