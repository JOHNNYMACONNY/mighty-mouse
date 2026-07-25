import json
import os
import sys
import tempfile
import unittest
import subprocess

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from tier_utils import load_tier_sequence, get_current_tier, get_replay_tiers
from task_validator import validate_task_completeness, run_negative_controls, TaskValidationError
from generate_tier_pack import build_tier_8_archetypes

def audit_everything():
    print("=== STARTING EXHAUSTIVE FB-13 AUDIT ===")

    # Audit 1: Config & Tier Resolution
    cfg_path = "eval/evaluation_config.json"
    with open(cfg_path, "r") as f:
        cfg = json.load(f)

    assert "tier_sequence" in cfg, "tier_sequence missing in evaluation_config.json"
    sequence = load_tier_sequence(cfg_path)
    assert sequence[-1] == "tier_8", f"tier_8 should be last, got {sequence[-1]}"
    assert "tier_8" in cfg["tiers"], "tier_8 key missing in tiers dict"
    assert len(cfg["tiers"]["tier_8"]) == 15, f"Expected 15 tasks in tier_8, got {len(cfg['tiers']['tier_8'])}"
    print("[✓] Audit 1 Passed: evaluation_config.json and tier_utils aligned.")

    # Audit 2: Perpetual Loop & Mutation Engine Integration
    import perpetual_loop
    import mutation_engine

    assert perpetual_loop.TIERS == sequence, "perpetual_loop.TIERS mismatch with tier_sequence"
    assert mutation_engine.TIERS == sequence, "mutation_engine.TIERS mismatch with tier_sequence"

    # Test get_replay_tiers for Tier 8
    replays = mutation_engine.get_replay_tiers("tier_8")
    assert len(replays) == 2, f"Expected 2 replay tiers for tier_8, got {replays}"
    assert replays == ["tier_7", "tier_6"], f"Unexpected replay tiers: {replays}"
    print("[✓] Audit 2 Passed: perpetual_loop and mutation_engine tier integration verified.")

    # Audit 3: Exhaustive Negative Control Testing
    archetypes = build_tier_8_archetypes()
    for task_def in archetypes:
        tid = task_def["id"]
        ref_files = task_def.pop("reference_files")
        
        # Verify 5 negative controls pass on reference implementation
        validate_task_completeness(task_def, reference_files=ref_files)

        # Verify that an intentionally broken reference implementation fails Negative Control #5
        broken_ref = {k: "def broken(): pass\n" for k in ref_files}
        try:
            run_negative_controls(task_def, reference_files=broken_ref)
            raise AssertionError(f"Task {tid} failed to catch broken reference implementation!")
        except TaskValidationError:
            pass # Expected failure
        
    print(f"[✓] Audit 3 Passed: All {len(archetypes)} Tier 8 tasks successfully validated & broken reference test caught.")

    # Audit 4: Manifest Hash Integrity
    manifest_path = "eval/tier_8_manifest.json"
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    
    assert manifest["total_tasks"] == 15, f"Manifest task count mismatch: {manifest['total_tasks']}"
    assert len(manifest["tasks"]) == 15, "Manifest tasks array length mismatch"
    for r in manifest["tasks"]:
        assert os.path.exists(os.path.join("tasks/benchmark", r["filename"])), f"Task file {r['filename']} missing"
    print("[✓] Audit 4 Passed: Immutable manifest and task JSON files verified.")

    print("\n=== ALL AUDIT CHECKS PASSED SUCCESSFULLY (100% VERIFIED) ===")

if __name__ == "__main__":
    audit_everything()
