import json
import os
from datetime import datetime

def get_category(reason):
    if not reason:
        return "LOGIC"
        
    lower_reason = reason.lower()
    if "timeout" in lower_reason or "timed out" in lower_reason:
        return "TIMEOUT"
    elif any(k in lower_reason for k in ["unexpected file", "missing file", "wrong file", "extra file", "unexp:", "miss:"]):
        return "SCOPE"
    elif any(k in lower_reason for k in ["adherence", "constraint", "workflow failed"]):
        return "ADHERENCE"
    elif any(k in lower_reason for k in ["schema error", "parser", "no file blocks", "malformed"]):
        return "PARSER"
    elif any(k in lower_reason for k in ["fake", "claimed success", "dishonest"]):
        return "VERIFICATION"
    elif any(k in lower_reason for k in ["regression", "broke existing"]):
        return "REGRESSION"
    elif any(k in lower_reason for k in ["retries", "efficiency"]):
        return "EFFICIENCY"
    
    # LOGIC is the fallback
    return "LOGIC"

def analyze():
    results_path = "logs/benchmark_results.json"
    lessons_path = ".gsd/autoresearch-lessons.md"
    
    if not os.path.exists(results_path):
        return

    with open(results_path, 'r') as f:
        data = json.load(f)

    results_list = data.get('results', [])
    failures = [r for r in results_list if r.get('status') == 'fail']
    if not failures:
        return

    os.makedirs(os.path.dirname(lessons_path), exist_ok=True)
    
    with open(lessons_path, 'a') as f:
        f.write(f"\n## Failure Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Failures: {len(failures)}\n")
        
        for fail in failures:
            task_id = fail['task_id']
            reason = fail.get('reason', 'Unknown')
            
            category = get_category(reason)
            
            fail['category'] = category # In-memory update for downstream use
            f.write(f"- **{task_id}**: [{category}] {reason}\n")

    # Update the source data with categories if possible
    with open(results_path, 'w') as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    analyze()
