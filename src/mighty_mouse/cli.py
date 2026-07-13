import argparse


def _positive_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed

def main():
    parser = argparse.ArgumentParser(description="Mighty Mouse CLI - High-reliability coding protocol for small models")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # doctor
    parser_doctor = subparsers.add_parser("doctor", help="Check system readiness and environment diagnostics")
    parser_doctor.add_argument("--live", action="store_true", help="Check Ollama health for live evaluations")

    # benchmark
    parser_benchmark = subparsers.add_parser("benchmark", help="Run benchmark evaluation tasks")
    parser_benchmark.add_argument("--tasks-dir", type=str, help="Explicit path to a directory of task JSONs")
    parser_benchmark.add_argument("--output-dir", type=str, help="Directory for logs and temporary workspaces")

    # demo
    parser_demo = subparsers.add_parser("demo", help="Run the Mighty Mouse demo")
    parser_demo.add_argument("--live", action="store_true", help="Run real Ollama evaluation instead of simulation")
    parser_demo.add_argument("--model", type=str, help="Ollama model name (required if --live is used)")
    parser_demo.add_argument("--output-dir", type=str, help="Directory for live-demo logs and temporary workspaces")

    # verify
    parser_verify = subparsers.add_parser("verify", help="Verify tests, lint, build, and changed-file scope")
    parser_verify.add_argument("workspace", help="Project directory to verify")
    parser_verify.add_argument("--test-command", help="Override the detected test command")
    parser_verify.add_argument("--lint-command", help="Override the detected lint command")
    parser_verify.add_argument("--build-command", help="Override the detected build command")
    parser_verify.add_argument(
        "--allowed-path",
        action="append",
        default=None,
        help="Allow changes under this path (repeatable)",
    )
    parser_verify.add_argument(
        "--timeout-sec",
        type=_positive_int,
        default=120,
        help="Timeout for each command in seconds (default: 120)",
    )
    parser_verify.add_argument("--json", action="store_true", help="Emit versioned JSON output")

    # protocol
    parser_protocol = subparsers.add_parser("protocol", help="Show a complexity-scaled coding protocol")
    parser_protocol.add_argument("task_description", help="Task the protocol will guide")
    parser_protocol.add_argument(
        "--complexity",
        choices=("low", "medium", "high"),
        default="medium",
        help="Protocol complexity (default: medium)",
    )
    parser_protocol.add_argument("--json", action="store_true", help="Emit versioned JSON output")

    # status
    parser_status = subparsers.add_parser("status", help="Show the read-only v2 Effective Policy")
    parser_status.add_argument("--state-dir", default=".mighty-mouse", help="Local v2 state directory")
    parser_status.add_argument("--mode", choices=("coding", "agentic", "hybrid"), required=True)
    parser_status.add_argument("--repository", required=True, help="Repository or project Scope")
    parser_status.add_argument("--task-category", choices=("unknown", "maintenance", "feature", "debugging", "refactoring"), default="unknown", help="Controlled Task Category")
    parser_status.add_argument("--model-class", required=True, help="Model class Scope")
    parser_status.add_argument("--model-digest", help="Exact model artifact digest")
    parser_status.add_argument("--model-artifact", help="Model artifact to fingerprint for exact identity")
    parser_status.add_argument("--execution-profile", default="unknown", help="Host execution profile")
    parser_status.add_argument("--capability", action="append", default=None, help="Observed model capability (repeatable)")
    parser_status.add_argument("--json", action="store_true", help="Emit versioned JSON output")

    for command, identifier, help_text in (
        ("preview", "candidate", "Run an explicit bounded Preview without changing Champion selection"),
        ("pin", "candidate", "Pin the current compatible Candidate for one exact Scope"),
    ):
        successor_parser = subparsers.add_parser(command, help=help_text)
        successor_parser.add_argument(f"{identifier}_id")
        if command == "preview":
            successor_parser.add_argument("--evidence-bundle-id", required=True)
        successor_parser.add_argument("--state-dir", default=".mighty-mouse", help="Local v2 state directory")
        successor_parser.add_argument("--mode", choices=("coding", "agentic", "hybrid"), required=True)
        successor_parser.add_argument("--repository", required=True, help="Repository or project Scope")
        successor_parser.add_argument("--task-category", choices=("unknown", "maintenance", "feature", "debugging", "refactoring"), default="unknown")
        successor_parser.add_argument("--model-class", required=True, help="Model class Scope")
        successor_parser.add_argument("--model-digest", help="Exact model artifact digest")
        successor_parser.add_argument("--model-artifact", help="Model artifact to fingerprint for exact identity")
        successor_parser.add_argument("--execution-profile", default="unknown", help="Host execution profile")
        successor_parser.add_argument("--capability", action="append", default=None, help="Observed model capability (repeatable)")
        successor_parser.add_argument("--json", action="store_true", help="Emit versioned JSON output")

    # run
    parser_run = subparsers.add_parser("run", help="Route one task through the v2 Autopilot boundary")
    parser_run.add_argument("--state-dir", default=".mighty-mouse", help="Local v2 state directory")
    parser_run.add_argument("--repository", required=True, help="Repository or project Scope")
    parser_run.add_argument("--task-category", choices=("unknown", "maintenance", "feature", "debugging", "refactoring"), default="unknown", help="Controlled Task Category")
    parser_run.add_argument("--model-class", required=True, help="Model class Scope")
    parser_run.add_argument("--inferred-mode", choices=("coding", "agentic"), required=True, help="Autopilot's inferred Mode")
    parser_run.add_argument("--confidence-percent", type=int, required=True, help="Autopilot routing confidence from 0 to 100")
    parser_run.add_argument("--mode", choices=("coding", "agentic", "hybrid"), help="Optional explicit user Mode override")
    parser_run.add_argument("--model-digest", help="Exact model artifact digest")
    parser_run.add_argument("--model-artifact", help="Model artifact to fingerprint for exact identity")
    parser_run.add_argument("--execution-profile", default="unknown", help="Host execution profile")
    parser_run.add_argument("--capability", action="append", default=None, help="Observed model capability (repeatable)")
    parser_run.add_argument("--handoff-file", help="JSON handoff produced by the Hybrid Investigation stage")
    parser_run.add_argument("--json", action="store_true", help="Emit versioned JSON output")

    # signals
    parser_signals = subparsers.add_parser("signals", help="Collect privacy-safe v2 Signals or view aggregate history")
    parser_signals.add_argument("action", choices=("collect", "pause", "resume", "compact", "purge", "history"))
    parser_signals.add_argument("--state-dir", default=".mighty-mouse", help="Local v2 state directory")
    parser_signals.add_argument("--signal-id", help="Controlled Signal identifier")
    parser_signals.add_argument("--repository", help="Repository Scope for collection")
    parser_signals.add_argument("--mode", choices=("coding", "agentic", "hybrid"), help="Mode Scope for collection")
    parser_signals.add_argument("--task-category", choices=("unknown", "maintenance", "feature", "debugging", "refactoring"), help="Controlled Task Category")
    parser_signals.add_argument("--model-class", help="Model class Scope for collection")
    parser_signals.add_argument("--model-digest", help="Exact model identity digest")
    parser_signals.add_argument("--execution-profile", help="Host execution profile")
    parser_signals.add_argument("--outcome", choices=("passed", "failed", "cancelled", "error"), help="Controlled task outcome")
    parser_signals.add_argument("--duration-ms", type=int, help="Task duration in milliseconds")
    parser_signals.add_argument("--retry-count", type=int, help="Retry count")
    parser_signals.add_argument("--verifier-category", choices=("tests", "build", "lint", "typecheck", "manual", "none"), help="Controlled verifier category")
    parser_signals.add_argument("--verifier-result", choices=("passed", "failed", "not_run"), help="Controlled verifier result")
    parser_signals.add_argument("--rating", type=int, choices=(1, 2, 3, 4, 5), help="Optional rating from 1 through 5")
    parser_signals.add_argument("--json", action="store_true", help="Emit versioned JSON output")

    # research
    parser_research = subparsers.add_parser("research", help="Start, stop, inspect, or run bounded v2 Background Research")
    parser_research.add_argument("action", choices=("start", "stop", "status", "run"))
    parser_research.add_argument("--state-dir", default=".mighty-mouse", help="Local v2 state directory")
    parser_research.add_argument("--repository", help="Repository Scope")
    parser_research.add_argument("--mode", choices=("coding", "agentic", "hybrid"), default="coding", help="Mode Scope")
    parser_research.add_argument("--task-category", choices=("unknown", "maintenance", "feature", "debugging", "refactoring"), default="unknown", help="Controlled Task Category")
    parser_research.add_argument("--model-class", help="Model class Scope")
    parser_research.add_argument("--model-digest", help="Exact model identity digest")
    parser_research.add_argument("--execution-profile", default="unknown", help="Host execution profile")
    parser_research.add_argument("--capability", action="append", default=None, help="Observed model capability (repeatable)")
    parser_research.add_argument("--protocol-version", default="v2", help="Frozen experiment protocol version")
    parser_research.add_argument("--candidate-cap", type=_positive_int, default=1, help="Maximum Candidates for this Generation")
    parser_research.add_argument("--max-tool-calls", type=_positive_int, default=1, help="Generation tool-call budget")
    parser_research.add_argument("--max-duration-ms", type=_positive_int, default=1000, help="Generation duration budget")
    parser_research.add_argument("--max-cost-units", type=_positive_int, default=1, help="Generation cost budget")
    parser_research.add_argument("--max-calls-per-minute", type=_positive_int, default=1, help="Generation rate budget")
    parser_research.add_argument("--seed", type=int, action="append", help="Frozen random seed (repeatable)")
    parser_research.add_argument("--task", action="append", help="Frozen development task identifier (repeatable)")
    parser_research.add_argument("--mutation-path", action="append", help="Declared Policy mutation surface (repeatable)")
    parser_research.add_argument("--thermal-state", choices=("normal", "warm", "critical"), default="normal", help="Observed thermal governor state")
    parser_research.add_argument("--requested-tool-calls", type=int, default=1, help="Requested execution tool calls")
    parser_research.add_argument("--requested-duration-ms", type=int, default=1, help="Requested execution duration")
    parser_research.add_argument("--requested-cost-units", type=int, default=1, help="Requested execution cost")
    parser_research.add_argument("--json", action="store_true", help="Emit versioned JSON output")

    args = parser.parse_args()

    if args.command == "doctor":
        from mighty_mouse.commands.doctor_cmd import run_doctor
        run_doctor(live=args.live)

    elif args.command == "benchmark":
        from mighty_mouse.commands.benchmark_cmd import run_benchmark
        run_benchmark(tasks_dir=args.tasks_dir, output_dir=args.output_dir)

    elif args.command == "demo":
        from mighty_mouse.commands.demo_cmd import run_demo
        run_demo(live=args.live, model=args.model, output_dir=args.output_dir)

    elif args.command == "verify":
        from mighty_mouse.commands.verify_cmd import run_verify
        run_verify(
            workspace=args.workspace,
            test_command=args.test_command,
            lint_command=args.lint_command,
            build_command=args.build_command,
            allowed_paths=args.allowed_path,
            timeout_sec=args.timeout_sec,
            json_output=args.json,
        )

    elif args.command == "protocol":
        from mighty_mouse.commands.protocol_cmd import run_protocol
        run_protocol(
            task_description=args.task_description,
            complexity=args.complexity,
            json_output=args.json,
        )

    elif args.command == "status":
        from mighty_mouse.commands.status_cmd import run_status
        run_status(
            state_dir=args.state_dir,
            mode=args.mode,
            repository=args.repository,
            task_category=args.task_category,
            model_class=args.model_class,
            model_digest=args.model_digest,
            model_artifact=args.model_artifact,
            execution_profile=args.execution_profile,
            capabilities=args.capability,
            json_output=args.json,
        )

    elif args.command == "preview":
        from mighty_mouse.commands.successor_cmd import run_preview
        run_preview(
            state_dir=args.state_dir, candidate_id=args.candidate_id, evidence_bundle_id=args.evidence_bundle_id,
            mode=args.mode, repository=args.repository, task_category=args.task_category, model_class=args.model_class,
            model_digest=args.model_digest, model_artifact=args.model_artifact,
            execution_profile=args.execution_profile, capabilities=args.capability, json_output=args.json,
        )

    elif args.command == "pin":
        from mighty_mouse.commands.successor_cmd import run_pin
        run_pin(
            state_dir=args.state_dir, candidate_id=args.candidate_id,
            mode=args.mode, repository=args.repository, task_category=args.task_category, model_class=args.model_class,
            model_digest=args.model_digest, model_artifact=args.model_artifact,
            execution_profile=args.execution_profile, capabilities=args.capability, json_output=args.json,
        )

    elif args.command == "run":
        from mighty_mouse.commands.run_cmd import run_run
        run_run(
            state_dir=args.state_dir,
            repository=args.repository,
            task_category=args.task_category,
            model_class=args.model_class,
            inferred_mode=args.inferred_mode,
            confidence_percent=args.confidence_percent,
            mode=args.mode,
            model_digest=args.model_digest,
            model_artifact=args.model_artifact,
            execution_profile=args.execution_profile,
            capabilities=args.capability,
            handoff_file=args.handoff_file,
            json_output=args.json,
        )

    elif args.command == "signals":
        from mighty_mouse.commands.signals_cmd import run_signals
        run_signals(
            action=args.action, state_dir=args.state_dir, signal_id=args.signal_id,
            repository=args.repository, mode=args.mode, task_category=args.task_category,
            model_class=args.model_class, model_digest=args.model_digest,
            execution_profile=args.execution_profile, outcome=args.outcome,
            duration_ms=args.duration_ms, retry_count=args.retry_count,
            verifier_category=args.verifier_category, verifier_result=args.verifier_result,
            rating=args.rating, json_output=args.json,
        )

    elif args.command == "research":
        from mighty_mouse.commands.research_cmd import run_research
        run_research(
            action=args.action, state_dir=args.state_dir, repository=args.repository, mode=args.mode,
            task_category=args.task_category, model_class=args.model_class, model_digest=args.model_digest,
            execution_profile=args.execution_profile, capabilities=args.capability, protocol_version=args.protocol_version,
            candidate_cap=args.candidate_cap, max_tool_calls=args.max_tool_calls, max_duration_ms=args.max_duration_ms,
            max_cost_units=args.max_cost_units, max_calls_per_minute=args.max_calls_per_minute, seed=args.seed, task=args.task, mutation_path=args.mutation_path,
            thermal_state=args.thermal_state, requested_tool_calls=args.requested_tool_calls,
            requested_duration_ms=args.requested_duration_ms, requested_cost_units=args.requested_cost_units,
            json_output=args.json,
        )


if __name__ == "__main__":
    main()
