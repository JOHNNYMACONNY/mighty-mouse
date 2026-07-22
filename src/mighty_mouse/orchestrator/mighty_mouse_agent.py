import argparse
import json
import os
import sys
import time

import yaml

from gemini_client import GeminiClient
from response_parser import ResponseParser

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_REGISTRY_PATH = os.getenv("SKILL_REGISTRY_PATH_OVERRIDE", os.path.join(_REPO_ROOT, "configs", "skills", "registry.yaml"))


def _load_skills(explicit_skills=None, task_data=None):
    """Load and filter skills based on registry and explicit requests."""
    if not os.path.exists(SKILL_REGISTRY_PATH):
        return [], [], {"conflict_detected": False, "conflicting_skill_ids": []}
    
    with open(SKILL_REGISTRY_PATH, 'r') as f:
        data = yaml.safe_load(f)
        all_skills = data.get("skills", [])
    
    active_overlays = []
    skill_meta_telemetry = []
    conflict_detected = False
    conflicting_skill_ids = []

    explicit_list = []
    if explicit_skills:
        explicit_list = [s.strip() for s in explicit_skills.split(",")]
        # Case 1: Multiple explicit skills rejected
        if len(explicit_list) > 1:
            print(f"[agent] ERROR: Multiple explicit skills requested: {explicit_list}. Stacking is prohibited.", file=sys.stderr)
            sys.exit(1)

    task_tags = []
    if isinstance(task_data, dict):
        task_tags = task_data.get("tags", [])

    # Step 1: Identify candidates
    injection_candidates = []
    
    if explicit_list:
        # Case 2: Explicit selection suppresses auto-injection
        for s in all_skills:
            s_id = s.get("skill_id")
            if s_id in explicit_list:
                if s.get("status") == "RETIRED":
                    print(f"[agent] WARNING: Skipping retired skill {s_id}", file=sys.stderr)
                    continue
                injection_candidates.append({
                    "skill": s,
                    "reason": "explicitly_requested",
                    "matched_tags": []
                })
    else:
        # Case 3: Auto-injection matching
        for s in all_skills:
            s_id = s.get("skill_id")
            status = s.get("status")
            activation_mode = s.get("activation_mode", "manual")
            trigger_tags = s.get("trigger_tags", [])
            
            if status == "ACTIVE" and activation_mode == "narrow":
                matched = list(set(task_tags) & set(trigger_tags))
                if matched:
                    injection_candidates.append({
                        "skill": s,
                        "reason": "auto_injected (tag_match)",
                        "matched_tags": matched
                    })

    # Step 2: Handle Conflicts (Fail-Closed)
    final_targets = []
    if not explicit_list and len(injection_candidates) > 1:
        conflict_detected = True
        conflicting_skill_ids = [c["skill"]["skill_id"] for c in injection_candidates]
        print(f"[agent] CONFLICT DETECTED: Multiple skills match tags {task_tags}: {conflicting_skill_ids}. Failing closed.", file=sys.stderr)
    else:
        final_targets = injection_candidates

    # Step 3: Load Overlays
    for target in final_targets:
        s = target["skill"]
        s_id = s.get("skill_id")
        o_path = s.get("overlay_path")
        repo_root = _REPO_ROOT
        abs_o_path = os.path.join(repo_root, o_path) if not os.path.isabs(o_path) else o_path
        
        if os.path.exists(abs_o_path):
            with open(abs_o_path, 'r') as f:
                active_overlays.append(f.read())
                skill_meta_telemetry.append({
                    "id": s_id, 
                    "status": s.get("status"),
                    "activation_mode": s.get("activation_mode", "manual"),
                    "auto_injected": target["reason"] != "explicitly_requested",
                    "injection_reason": target["reason"],
                    "matched_tags": target["matched_tags"]
                })
        else:
            print(f"[agent] ERROR: Skill overlay file not found: {abs_o_path}", file=sys.stderr)

    # Validation for unknown skills requested explicitly
    for exp_id in explicit_list:
        if not any(s.get("skill_id") == exp_id for s in all_skills):
            print(f"[agent] ERROR: Unknown skill requested: {exp_id}", file=sys.stderr)
            sys.exit(1)

    conflict_meta = {
        "conflict_detected": conflict_detected,
        "conflicting_skill_ids": conflicting_skill_ids
    }
    return active_overlays, skill_meta_telemetry, conflict_meta



def _hygiene_audit(workspace_root, task_data=None):
    """Purge OS junk and stale ghost files before implementation."""
    removed_count = 0
    # 1. Purge AppleDouble/DS_Store junk
    for root, dirs, files in os.walk(workspace_root):
        for f in files:
            if f.startswith("._") or f == ".DS_Store":
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass
    
    # 2. Metadata-driven Pre-run Cleanup
    allowed_paths = set()
    if isinstance(task_data, dict):
        allowed_paths.update(task_data.get("expected_files", []))
        fixture_dir = task_data.get("fixture_dir")
        if fixture_dir:
            # Resolve fixtures relative to repo root (assumed to be ../.. from workspace)
            repo_root = os.path.abspath(os.path.join(workspace_root, "../.."))
            fixture_abs = os.path.join(repo_root, fixture_dir)
            if os.path.exists(fixture_abs):
                for root, _, files in os.walk(fixture_abs):
                    for f in files:
                        rel = os.path.relpath(os.path.join(root, f), fixture_abs)
                        allowed_paths.add(rel)

    # Universal metadata (non-code artifacts)
    allowed_paths.update([".gitignore", "CHECKLIST.md", "test_script.py", "test_runner.py", "requirements.txt", "START-HERE-ANTIGRAVITY.md"])
    
    # Identify Stale Ghosts (.py files in root NOT in allowed_paths and NOT in .mighty/)
    root_files = [f for f in os.listdir(workspace_root) if os.path.isfile(os.path.join(workspace_root, f))]
    for f in root_files:
        # We only purge root-level .py files to avoid deep-tree false positives
        if f.endswith(".py") and f not in allowed_paths:
            # .mighty is a directory, so root files won't be in it, but just in case:
            if not f.startswith(".mighty"):
                try:
                    os.remove(os.path.join(workspace_root, f))
                    print(f"[hygiene] Purged stale ghost: {f}", file=sys.stderr)
                    removed_count += 1
                except OSError:
                    pass
    return removed_count


def _write_run_metadata(client, workspace, task_input, p_cfg, feedback_str=None, usage_history=None, extra=None):
    logs_dir = os.path.join(workspace or os.getcwd(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    metadata = {
        "model": p_cfg.get("model", "unknown"),
        "mode": p_cfg.get("mode", "production"),
        "provider": p_cfg.get("provider", "unknown"),
        "task_input": task_input,
        "workspace": workspace or os.getcwd(),
        "feedback_supplied": bool(feedback_str),
        "usage": client.last_metadata.get("usage"),
        "latency_seconds": client.last_metadata.get("latency_seconds"),
        "usage_history": usage_history or [client.last_metadata]
    }
    if extra:
        metadata.update(extra)
    with open(os.path.join(logs_dir, "last_agent_run.json"), "w") as f:
        json.dump(metadata, f, indent=2)


def solve(p_cfg_path, task_input, feedback_str=None, workspace=None, explicit_skills=None, temperature=None, stage="unified", plan_file=None):
    p_cfg_path = os.path.abspath(p_cfg_path)
    task_input = os.path.abspath(task_input)
    if workspace:
        workspace = os.path.abspath(workspace)
        if not os.path.exists(workspace):
            os.makedirs(workspace, exist_ok=True)
            
    original_cwd = os.getcwd()
    try:
        if workspace:
            os.chdir(workspace)
        return _solve_inner(p_cfg_path, task_input, feedback_str, workspace, explicit_skills, temperature=temperature, stage=stage, plan_file=plan_file)
    finally:
        os.chdir(original_cwd)

def _solve_inner(p_cfg_path, task_input, feedback_str=None, workspace=None, explicit_skills=None, temperature=None, stage="unified", plan_file=None):
    task_data = None
    if os.path.exists(task_input):
        with open(task_input, 'r') as f:
            try:
                task_data = json.load(f)
            except Exception:
                pass

    if os.path.exists(task_input):
        with open(task_input, 'r') as f:
            try:
                task_data = json.load(f)
            except Exception:
                pass
    
    stale_removed = _hygiene_audit(os.getcwd(), task_data=task_data)

    with open(p_cfg_path, 'r') as f:
        p_cfg = yaml.safe_load(f)
    if temperature is not None:
        p_cfg["temperature"] = float(temperature)
    cfg_dir = os.path.dirname(os.path.abspath(p_cfg_path))

    segments = []
    for rel_path in p_cfg.get('prompt_segments', []):
        abs_p = os.path.join(cfg_dir, rel_path)
        if os.path.exists(abs_p):
            with open(abs_p, 'r') as f:
                segments.append(f.read())

    sys_prompt_rel = p_cfg.get('system_prompt_path', 'system_prompt.txt')
    abs_sys = os.path.join(cfg_dir, sys_prompt_rel)
    system_prompt = ""
    if os.path.exists(abs_sys):
        with open(abs_sys, 'r') as f:
            system_prompt = f.read()

    # 4. Load Skill Overlays
    skill_overlays, skill_meta, conflict_meta = _load_skills(explicit_skills=explicit_skills, task_data=task_data)

    
    # 5. Construct Final Prompt
    overlay_block = ""
    if skill_overlays:
        overlay_block = "\n\n=== DYNAMIC SKILL OVERLAYS ===\n\n" + "\n\n---\n\n".join(skill_overlays)

    full_sys = "\n\n".join(segments + [system_prompt])
    if overlay_block:
        full_sys += overlay_block

    if os.path.exists(task_input):
        with open(task_input, 'r') as f:
            try:
                task_data = json.load(f)
                task_str = json.dumps(task_data, indent=2)
            except Exception:
                with open(task_input, 'r') as f2:
                    task_str = f2.read()
    else:
        task_str = task_input

    FORMAT_REMINDER = (
        "\n⚠️ MANDATORY OUTPUT FORMAT ⚠️\n"
        "1. CREATE/MODIFY: You MUST output every file you create or modify using this exact format:\n"
        "```python:path/to/file.py\n"
        "# your code here\n"
        "```\n"
        "2. DELETE: To delete/purge/remove a file, use a fenced block with language `delete:path/to/file`.\n"
        "   - Correct (MUST include an empty line inside the block):\n"
        "     ```delete:obsolete_shim.py\n"
        "\n"
        "     ```\n"
        "   - Incorrect: ```python:delete:obsolete_shim.py\n"
        "   - Incorrect: ```text:delete:obsolete_shim.py\n"
        "   - Incorrect: ```delete:obsolete_shim.py``` (Missing internal newline)\n"
        "   - The fence language MUST start exactly with the word 'delete:'.\n"
        "Do NOT simulate deletion by writing comments, tombstones, empty content, `# PURGE`, `# DELETE`, or similar text into the file.\n"
        "Only delete files when the task authorizes deletion through 'deletable_files' or explicit task instructions.\n\n"
        "Responses without at least one valid fenced block will be REJECTED.\n\n"
    )

    DISALLOWED_PATTERNS = (
        "\n<disallowed_patterns>\n"
        "- Do NOT create unused helper functions, stub files, or unnecessary abstractions.\n"
        "- Do NOT swallow exceptions with silent try/except pass blocks.\n"
        "- Do NOT modify files outside the authorized scope.\n"
        "- Do NOT output dummy values, fake data, or placeholder strings.\n"
        "</disallowed_patterns>\n"
    )

    plan_content = ""
    if stage == "coder":
        plan_path = plan_file or os.path.join("logs", "stage1_plan.md")
        if plan_path and os.path.exists(plan_path):
            with open(plan_path, "r") as f:
                plan_content = f.read()
        elif plan_file:
            plan_content = plan_file

    if stage == "planner":
        PLANNER_REMINDER = (
            "⚠️ STAGE 1: PLANNER MODE ⚠️\n"
            "Analyze the codebase and task requirements. Output a detailed architectural blueprint inside <plan>...</plan> tags.\n"
            "Include:\n"
            "1. <context_audit>: Relevant files, symbols, and dependencies.\n"
            "2. <scope_definition>: Strict list of files to edit/create.\n"
            "3. <adversarial_plan>: Zero-deletion checks and risk analysis.\n"
            "4. <proposed_changes>: Concrete steps and file-by-file changes.\n\n"
        )
        user_prompt = f"{PLANNER_REMINDER}Create an execution blueprint for the following task:\n{task_str}\n"
    else:
        user_prompt = f"{FORMAT_REMINDER}Implement the following task:\n{task_str}\n"
        if plan_content:
            user_prompt = f"<stage1_blueprint>\n{plan_content}\n</stage1_blueprint>\n\n" + user_prompt

    if feedback_str:
        user_prompt += f"\n\n<execution_feedback>\nPREVIOUS ATTEMPT FAILED. FEEDBACK:\n{feedback_str}\n</execution_feedback>\n"
    user_prompt += DISALLOWED_PATTERNS

    client = GeminiClient(config=p_cfg)
    allowed_delete_paths = []
    if isinstance(task_data, dict):
        allowed_delete_paths = task_data.get("deletable_files", [])

    MAX_ATTEMPTS = 2
    usage_history = []
    current_user_prompt = user_prompt
    output_paths = []
    schema_error = False

    # Control and telemetry state for Output Coverage Recovery
    cumulative_output_paths = []
    coverage_recovery_attempts = 0
    coverage_recovery_triggered = False
    coverage_missing_files = []
    coverage_recovery_success = False
    coverage_recovery_disallowed_reason = None
    pass_type = "clean"

    # Extract conflict and routing validation properties
    conflict_detected = conflict_meta.get("conflict_detected", False)
    injection_reason = ""
    if skill_meta:
        injection_reason = skill_meta[0].get("injection_reason", "")
    elif conflict_detected:
        injection_reason = "CONFLICT_REJECTED"

    task_id = task_data.get("id", "") if isinstance(task_data, dict) else ""
    task_tags = task_data.get("tags", []) if isinstance(task_data, dict) else []
    expected_files = task_data.get("expected_files", []) if isinstance(task_data, dict) else []

    is_conflict_routing_validation = (
        task_id.startswith("obs_task_conflict_") or
        any(tag in task_tags for tag in ["conflict", "routing", "stacking"])
    )

    base_max_attempts = MAX_ATTEMPTS
    effective_max_attempts = base_max_attempts
    attempt = 1
    while attempt <= effective_max_attempts:
        print(f"[agent] Attempt {attempt}/{effective_max_attempts} starting...", file=sys.stderr)
        sys.stdout.flush()
        try:
            response = client.generate_content(full_sys, current_user_prompt)
            usage_history.append(dict(client.last_metadata))

            # DEBUG: Save raw response to a permanent global log directory
            global_logs_dir = os.path.join(_REPO_ROOT, "logs", "raw_responses")
            os.makedirs(global_logs_dir, exist_ok=True)
            task_id_str = task_id if task_id else 'unknown'
            ts = int(time.time())
            with open(os.path.join(global_logs_dir, f"raw_{task_id_str}_attempt_{attempt}_{ts}.txt"), "w") as f:
                f.write(response)

        except Exception as e:
            print(f"[agent] ERROR during generation: {e}", file=sys.stderr)
            if attempt < effective_max_attempts:
                print("[agent] Retrying...", file=sys.stderr)
                time.sleep(2)
                attempt += 1
                continue
            else:
                print("[agent] CRITICAL: Maximum attempts reached. Failing task.", file=sys.stderr)
                pass_type = "failed"
                break

        if stage == "planner":
            plan_dest = plan_file or os.path.join(_REPO_ROOT, "logs", "stage1_plan.md")
            os.makedirs(os.path.dirname(os.path.abspath(plan_dest)), exist_ok=True)
            with open(plan_dest, "w") as f:
                f.write(response)
            print(f"[Stage 1 Planner] Architectural blueprint saved to {plan_dest}", file=sys.stderr)
            output_paths = [plan_dest]
            pass_type = "clean"
            break

        output_paths = ResponseParser.parse_and_write(
            response,
            workspace_root=workspace or os.getcwd(),
            allowed_delete_paths=allowed_delete_paths,
        )
        cumulative_output_paths.extend(output_paths)

        schema_error = False
        if not output_paths:
            schema_error = True
            if attempt < effective_max_attempts:
                print("[agent] SCHEMA ERROR: No file blocks found. Retrying with explicit schema correction...", file=sys.stderr)
                current_user_prompt += "\n\nCRITICAL ERROR: No code blocks were found in your previous response. You MUST use the correct XML/Markdown format with file paths (e.g., ```python:path/to/file.py)."
                attempt += 1
                continue
            else:
                print("[agent] CRITICAL: Schema error persists after retry.", file=sys.stderr)
                pass_type = "failed"
                break

        # Strictly verify parsed files against expected implementation files
        missing_files = [f for f in expected_files if f not in cumulative_output_paths]
        if missing_files:
            coverage_missing_files = missing_files  # Record context immediately
            disallowed_reason = None
            if schema_error:
                disallowed_reason = "SCHEMA_ERROR"
            elif conflict_detected:
                disallowed_reason = "CONFLICT_DETECTED"
            elif injection_reason == "CONFLICT_REJECTED":
                disallowed_reason = "CONFLICT_REJECTED"
            elif is_conflict_routing_validation:
                disallowed_reason = "CONFLICT_ROUTING_VALIDATION_TASK"
            elif not expected_files:
                disallowed_reason = "EMPTY_EXPECTED_FILES"
            elif any(f in allowed_delete_paths for f in missing_files):
                disallowed_reason = "DELETABLE_FILE_EXCLUSION"
            elif coverage_recovery_attempts >= 1:
                disallowed_reason = "MAX_ATTEMPTS_REACHED"

            if disallowed_reason:
                coverage_recovery_disallowed_reason = disallowed_reason
                print(f"[agent] Missing expected files {missing_files} detected but recovery is forbidden: {disallowed_reason}", file=sys.stderr)
                pass_type = "failed"
                break
            else:
                # Trigger Output Coverage Recovery
                coverage_recovery_attempts += 1
                coverage_recovery_triggered = True
                print(f"[agent] Missing expected files detected: {missing_files}. Issuing targeted recovery reprompt...", file=sys.stderr)
                
                missing_list_str = "\n".join([f"- {f}" for f in missing_files])
                recovery_prompt = (
                    f"\n\nCRITICAL OMISSION DETECTED:\n"
                    f"Your previous response failed to provide the implementation for the following required files:\n"
                    f"{missing_list_str}\n\n"
                    f"You MUST provide the complete implementation for these files now using the correct format (```python:path/to/file.py).\n"
                    f"Do NOT rewrite files you have already provided. Only provide the missing file blocks."
                )
                current_user_prompt += recovery_prompt
                effective_max_attempts = base_max_attempts + 1
                attempt += 1
                continue
        else:
            if coverage_recovery_triggered:
                coverage_recovery_success = True
                pass_type = "recovered"
                print("[agent] Coverage recovery successfully recovered missing expected files.", file=sys.stderr)
            else:
                pass_type = "clean"
            break

    # Unify final outputs
    output_paths = list(set(cumulative_output_paths))

    workspace_root = workspace or os.getcwd()
    deleted_files = [
        path for path in output_paths
        if path in allowed_delete_paths and not os.path.exists(os.path.join(workspace_root, path))
    ]
    written_files = [path for path in output_paths if path not in deleted_files]
    _write_run_metadata(
        client,
        workspace,
        task_input,
        p_cfg,
        feedback_str,
        usage_history=usage_history,
        extra={
            "task_id": task_data.get("id") if isinstance(task_data, dict) else None,
            "output_files": output_paths,
            "written_files": written_files,
            "deleted_files": deleted_files,
            "schema_error": schema_error,
            "attempts": len(usage_history),
            "stale_ghost_files_removed_pre_run": stale_removed,
            "skill_ids": [s["id"] for s in skill_meta],
            "overlay_enabled": bool(skill_overlays),
            "auto_injected": any(s.get("auto_injected") for s in skill_meta),
            "injection_reason": skill_meta[0].get("injection_reason") if skill_meta else (
                "CONFLICT_REJECTED" if conflict_meta["conflict_detected"] else None
            ),
            "matched_tags": [tag for s in skill_meta for tag in s.get("matched_tags", [])],
            "activation_mode": skill_meta[0].get("activation_mode") if skill_meta else None,
            "conflict_detected": conflict_meta["conflict_detected"],
            "conflicting_skill_ids": conflict_meta["conflicting_skill_ids"],
            "coverage_recovery_triggered": coverage_recovery_triggered,
            "coverage_missing_files": coverage_missing_files,
            "coverage_recovery_attempts": coverage_recovery_attempts,
            "coverage_recovery_success": coverage_recovery_success,
            "coverage_recovery_disallowed_reason": coverage_recovery_disallowed_reason,
            "pass_type": pass_type
        },
    )



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("task")
    parser.add_argument("--feedback", help="Feedback from previous run")
    parser.add_argument("--workspace", help="Path to isolated workspace")
    parser.add_argument("--skills", help="Comma-separated list of skill IDs to enable")
    parser.add_argument("--temperature", type=float, help="LLM sampling temperature override")
    parser.add_argument("--stage", choices=["planner", "coder", "unified"], default="unified", help="Execution stage mode")
    parser.add_argument("--plan-file", help="Path to Stage 1 plan file or plan text input")
    args = parser.parse_args()

    cfg_abs = os.path.abspath(args.config)
    task_abs = os.path.abspath(args.task)

    solve(
        cfg_abs,
        task_abs,
        feedback_str=args.feedback,
        workspace=args.workspace,
        explicit_skills=args.skills,
        temperature=args.temperature,
        stage=args.stage,
        plan_file=args.plan_file
    )
