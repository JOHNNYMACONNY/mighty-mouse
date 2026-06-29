import argparse

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


if __name__ == "__main__":
    main()
