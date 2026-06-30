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


if __name__ == "__main__":
    main()
