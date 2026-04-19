import json
import os
import sys

def score():
    log_file = "eval/results/benchmark_results.json"
    config_file = "eval/evaluation_config.json"
    
    if not os.path.exists(log_file):
        print("0.0")
        return

    try:
        with open(log_file, 'r') as f:
            results = json.load(f)
        with open(config_file, 'r') as f:
            config = json.load(f)
    except Exception as e:
        print("0.0")
        return

    if not results:
        print("0.0")
        return

    weights = config.get("weights", {"simple": 1.0, "complex": 3.0})
    metadata = config.get("task_metadata", {})
    
    total_weighted_points = 0
    passed_weighted_points = 0
    
    for res in results:
        task_id = res.get("task_id")
        task_key = task_id if task_id.endswith(".json") else f"{task_id}.json"
        
        task_type = metadata.get(task_key, "simple")
        weight = weights.get(task_type, 1.0)
        
        total_weighted_points += weight
        if res.get("status") == "success":
            passed_weighted_points += weight
            
    if total_weighted_points == 0:
        print("0.0")
        return

    success_rate = (passed_weighted_points / total_weighted_points) * 100
    print(f"{success_rate:.2f}")

if __name__ == "__main__":
    score()
