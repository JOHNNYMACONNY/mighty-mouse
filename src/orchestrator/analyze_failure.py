import json
import os
from datetime import datetime

def analyze():
    results_path = "logs/benchmark_results.json"
    lessons_path = ".gsd/autoresearch-lessons.md"
    
    if not os.path.exists(results_path):
        return

    with open(results_path, 'r') as f:
        results = json.load(f)

    failures = [r for r in results if r['status'] == 'fail']
    if not failures:
        return

    os.makedirs(os.path.dirname(lessons_path), exist_ok=True)
    
    with open(lessons_path, 'a') as f:
        f.write(f"\n## Failure Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Failures: {len(failures)}\n")
        
        for fail in failures:
            task_id = fail['task_id']
            reason = fail.get('reason', 'Unknown')
            # Categorize
            category = "LOGIC"
            if "Unexpected files" in reason: category = "SCOPE"
            if "Workflow failed" in reason: category = "ADHERENCE"
            
            f.write(f"- **{task_id}**: [{category}] {reason}\n")

if __name__ == "__main__":
    analyze()
