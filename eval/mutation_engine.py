import json
import os
import subprocess
import sys
import shutil
import time
from datetime import datetime
import yaml

# Add src/mighty_mouse/orchestrator to path for GeminiClient
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))
from gemini_client import GeminiClient

# Config
RESULTS_PATH = "logs/benchmark_results.json"
MUTATION_LOG_PATH = "logs/mutation_log.jsonl"
SEGMENTS_DIR = "configs/prompt_segments"
AGENT_CONFIG = "configs/mighty_mouse_v1.yaml"
TIERS = ["tier_1", "tier_overnight", "tier_3", "tier_4", "tier_5", "tier_6", "tier_7"]

CATEGORY_TO_SEGMENT = {
    "SCOPE": "constraints.txt",
    "ADHERENCE": "discipline.txt",
    "LOGIC": "reasoning.txt",
    "VERIFICATION": "verification.txt",
    "REGRESSION": "discipline.txt",
    "EFFICIENCY": "reasoning.txt",
    "PARSER": "constraints.txt",
    "TIMEOUT": "timeout_policy"
}

def get_current_tier():
    state_path = "logs/perpetual_state.json"
    if os.path.exists(state_path):
        with open(state_path, 'r') as f:
            return json.load(f).get("current_tier", TIERS[0])
    return TIERS[0]

def get_replay_tiers(current_tier):
    idx = TIERS.index(current_tier)
    replays = []
    if idx > 0:
        replays.append(TIERS[idx-1])
    if idx > 1:
        replays.append(TIERS[idx-2])
    return replays

def analyze_failures():
    if not os.path.exists(RESULTS_PATH):
        return None
    with open(RESULTS_PATH, 'r') as f:
        data = json.load(f)
    
    results = data.get("results", [])
    failures = [r for r in results if r.get("status") == "fail"]
    if not failures:
        return None
    
    counts = {}
    for f in failures:
        cat = f.get("category", "LOGIC")
        counts[cat] = counts.get(cat, 0) + 1
    
    dominant = max(counts, key=counts.get)
    
    # Timeout Dominance Logic: Plurality OR 2+ instances
    is_timeout_dominant = (dominant == "TIMEOUT") or (counts.get("TIMEOUT", 0) >= 2)
    
    return dominant, is_timeout_dominant, failures, data.get("summary")

def generate_mutation(category, failures):
    segment_file = CATEGORY_TO_SEGMENT.get(category, "reasoning.txt")
    segment_path = os.path.join(SEGMENTS_DIR, segment_file)
    
    with open(segment_path, 'r') as f:
        current_content = f.read()
    
    examples = "\n".join([f"- Task: {f['task_id']}, Reason: {f['reason']}" for f in failures[:3]])
    
    prompt = f"""
You are a Prompt Engineering Expert for the Mighty Mouse project.
We are seeing failures in the category: {category}.
Representative failures:
{examples}

Current content of '{segment_file}':
{current_content}

Your goal is to provide a MINIMAL mutation to this segment to address these failures without breaking existing behavior.
Output your response in this JSON format:
{{
  "hypothesis": "Your specific hypothesis on why this change will help",
  "new_content": "The full new content for the segment"
}}
"""
    # Use a dummy config for mutation generation or the real one
    with open(AGENT_CONFIG, 'r') as f:
        cfg = yaml.safe_load(f)
    
    client = GeminiClient(config=cfg)
    try:
        response_text = client.generate_content("You are a prompt engineering expert.", prompt)
        # Find JSON block
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "{" in response_text:
            response_text = response_text[response_text.find("{"):response_text.rfind("}")+1]
        
        mutation = json.loads(response_text)
        return segment_file, mutation
    except Exception as e:
        print(f"[!] Mutation generation failed: {e}")
        return None, None

def run_tier(tier):
    print(f"[*] Testing tier: {tier}...")
    cmd = [sys.executable, "eval/run_parallel.py", "--tier", tier]
    subprocess.run(cmd, capture_output=True)
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH, 'r') as f:
            return json.load(f).get("summary")
    return None

def get_pass_rate(summary):
    if not summary: return 0
    rate_str = summary.get("success_rate", "0/0")
    passed, total = map(int, rate_str.split('/'))
    return (passed / total) if total > 0 else 0

def log_mutation(record):
    with open(MUTATION_LOG_PATH, 'a') as f:
        f.write(json.dumps(record) + "\n")

def main():
    print("=== Mighty Mouse Mutation Engine Starting ===")
    dominant_cat, is_timeout_dominant, failures, original_summary = analyze_failures()
    if not dominant_cat:
        print("[*] No failures to analyze. Exiting.")
        return

    if is_timeout_dominant:
        print("[!] TIMEOUT detected as dominant failure mode (Gemma 4 Reasoning Horizon reached).")
        print("[!] FREEZING mutations to reasoning.txt and discipline.txt.")
        print("[!] Recommendation: Run an efficiency/decomposition mini-spike instead of prompt expansion.")
        return

    current_tier = get_current_tier()
    replay_tiers = get_replay_tiers(current_tier)
    
    segment_file, mutation = generate_mutation(dominant_cat, failures)
    if not mutation:
        return

    segment_path = os.path.join(SEGMENTS_DIR, segment_file)
    backup_path = segment_path + ".bak"
    shutil.copy2(segment_path, backup_path)
    
    print(f"[*] Applying mutation to {segment_file}...")
    print(f"[*] Hypothesis: {mutation['hypothesis']}")
    
    with open(segment_path, 'w') as f:
        f.write(mutation['new_content'])
    
    # Evaluate
    new_summary = run_tier(current_tier)
    
    original_rate = get_pass_rate(original_summary)
    new_rate = get_pass_rate(new_summary)
    
    print(f"[*] Current Tier Results: {original_rate:.1%} -> {new_rate:.1%}")
    
    decision = "REJECT"
    if new_rate >= original_rate:
        # Replay tests
        decision = "PROMOTE"
        for rt in replay_tiers:
            rt_summary = run_tier(rt)
            # We don't have historical data for replay tiers easily available here, 
            # but we assume the previous prompt passed them (since it's the current config).
            # If it passes now, it's good.
            if get_pass_rate(rt_summary) < 0.90: # Tiers are only escalated at 90%
                print(f"[!] Mutation failed replay test on {rt}. Rejecting.")
                decision = "REJECT"
                break
    
    record = {
        "timestamp": datetime.now().isoformat(),
        "failure_category": dominant_cat,
        "segment_changed": segment_file,
        "hypothesis": mutation["hypothesis"],
        "before": original_summary,
        "after": new_summary,
        "replay_tiers_tested": replay_tiers,
        "decision": decision
    }
    
    if decision == "REJECT":
        print("[!] Mutation REJECTED. Restoring segment.")
        shutil.copy2(backup_path, segment_path)
    else:
        print("[+] Mutation PROMOTED.")
    
    log_mutation(record)
    os.remove(backup_path)

if __name__ == "__main__":
    main()
