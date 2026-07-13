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


if __name__ == "__main__":
    main()
