import os
import sys
import json

# Setup environment before import
TEST_REGISTRY = "configs/skills/test_registry.yaml"
os.environ["SKILL_REGISTRY_PATH_OVERRIDE"] = TEST_REGISTRY

# Add src/mighty_mouse/orchestrator to path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))

from mighty_mouse_agent import _load_skills

def run_case(name, explicit_skills=None, task_data=None):
    print(f"\n--- Testing: {name} ---")
    try:
        overlays, meta, conflict = _load_skills(explicit_skills, task_data)
        
        # Build the 'extra' dict logic like in solve()
        extra = {
            "skill_ids": [s["id"] for s in meta],
            "overlay_enabled": bool(overlays),
            "auto_injected": any(s.get("auto_injected") for s in meta),
            "injection_reason": meta[0].get("injection_reason") if meta else (
                "CONFLICT_REJECTED" if conflict["conflict_detected"] else None
            ),
            "matched_tags": [tag for s in meta for tag in s.get("matched_tags", [])],
            "activation_mode": meta[0].get("activation_mode") if meta else None,
            "conflict_detected": conflict["conflict_detected"],
            "conflicting_skill_ids": conflict["conflicting_skill_ids"]
        }
        
        print(f"Overlays: {len(overlays)}")
        print(f"Meta: {json.dumps(extra, indent=2)}")
        return extra
    except SystemExit as e:
        print(f"Caught Expected Exit: {e}")
        return "EXIT_1"

if __name__ == "__main__":
    # 1. Single S1 match
    res = run_case("Single S1 Match", task_data={"tags": ["retry"]})
    assert res["skill_ids"] == ["S1-STATE"]
    assert res["auto_injected"] == True
    assert res["conflict_detected"] == False

    # 2. Single S2 match (Simulated)
    res = run_case("Single S2 Match", task_data={"tags": ["stream"]})
    assert res["skill_ids"] == ["S2-STREAM"]
    assert res["auto_injected"] == True

    # 3. S1 + S2 Conflict
    res = run_case("S1 + S2 Conflict", task_data={"tags": ["stream", "retry"]})
    assert res["conflict_detected"] == True
    assert set(res["conflicting_skill_ids"]) == {"S1-STATE", "S2-STREAM"}
    assert res["skill_ids"] == []
    assert res["overlay_enabled"] == False
    assert res["injection_reason"] == "CONFLICT_REJECTED"

    # 4. Explicit S1 (with conflict in tags)
    res = run_case("Explicit S1", explicit_skills="S1-STATE", task_data={"tags": ["stream", "retry"]})
    assert res["skill_ids"] == ["S1-STATE"]
    assert res["auto_injected"] == False
    assert res["conflict_detected"] == False # Explicit suppresses auto detection

    # 5. Explicit S2
    res = run_case("Explicit S2", explicit_skills="S2-STREAM")
    assert res["skill_ids"] == ["S2-STREAM"]

    # 6. Explicit Multi-Reject
    res = run_case("Explicit Multi-Reject", explicit_skills="S1-STATE,S2-STREAM")
    assert res == "EXIT_1"

    # 7. Unrelated task
    res = run_case("Unrelated Task", task_data={"tags": ["python"]})
    assert res["skill_ids"] == []
    assert res["conflict_detected"] == False

    print("\nALL CONFLICT POLICY TESTS PASSED.")
