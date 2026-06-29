import argparse
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="Mighty Mouse CLI - High-reliability coding protocol for small models")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # doctor
    parser_doctor = subparsers.add_parser("doctor", help="Check system readiness and environment diagnostics")
    parser_doctor.add_argument("--live", action="store_true", help="Check Ollama health for live evaluations")

    # benchmark
    parser_benchmark = subparsers.add_parser("benchmark", help="Run benchmark evaluation tasks")
    parser_benchmark.add_argument("--generate", action="store_true", help="Generate the full 1,600-task corpus on-demand")
    parser_benchmark.add_argument("--tier", type=str, default="tier_1", help="Benchmark tier to run")

    # compare
    parser_compare = subparsers.add_parser("compare", help="Compare two benchmark runs")

    # research
    parser_research = subparsers.add_parser("research", help="Run autoresearch iteration")

    # report
    parser_report = subparsers.add_parser("report", help="Generate an analysis report for a run")

    # demo
    parser_demo = subparsers.add_parser("demo", help="Run the Mighty Mouse demo")
    parser_demo.add_argument("--live", action="store_true", help="Run real Ollama evaluation instead of simulation")
    parser_demo.add_argument("--model", type=str, help="Ollama model name (required if --live is used)")

    args = parser.parse_args()

    if args.command == "doctor":
        from mighty_mouse.commands.doctor_cmd import run_doctor
        # Check if the user passed --live? We didn't add it in argparse yet, let's add it.
        # Wait, I'll just check args.live if we add it, else False.
        live = getattr(args, "live", False)
        run_doctor(live=live)

    elif args.command == "benchmark":
        from mighty_mouse.commands.benchmark_cmd import run_benchmark
        run_benchmark(generate=args.generate, tier=args.tier)

    elif args.command == "demo":
        from mighty_mouse.commands.demo_cmd import run_demo
        run_demo(live=args.live, model=args.model)


if __name__ == "__main__":
    main()
