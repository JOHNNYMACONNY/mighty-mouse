# Mighty Mouse

Mighty Mouse is an evaluation-driven harness that improves the reliability and efficiency of smaller language models. It enforces strict structural output (e.g. XML formatting) and multi-step verification workflows.

## Features

- **Evaluation-Driven Harness**: Provides a suite of reproducible benchmark tasks to rigorously measure a model's coding reliability.
- **Improved Efficiency**: Through iterative testing and refinement (the Lean Protocol), Mighty Mouse achieves significant speedups (e.g., a 29.5% reduction in latency across 15 paired tasks) without losing reliability.
- **Robust CLI**: A minimal CLI provides the tools to run diagnostics, execute benchmarks, and perform live or simulated demos.

## Quick Start

### Installation

Clone the repository and install it in editable mode:

```bash
git clone <repository-url>
cd mighty_mouse
pip install -e .
```

### Diagnostics

Check base package readiness:

```bash
mighty-mouse doctor
```

Check Ollama availability before a live run:

```bash
mighty-mouse doctor --live
```

### Running the Demo

You can run the demo in two modes:

1. **Simulated (Fast)**: Uses cached fixtures to show how the system operates immediately.
   ```bash
   mighty-mouse demo
   ```
2. **Live**: Runs a real evaluation against a local Ollama model.
   ```bash
   mighty-mouse demo --live --model gemma:2b
   ```

### Benchmarks

Run the five packaged benchmark tasks:

```bash
mighty-mouse benchmark
```

Or run task JSON files from a directory:

```bash
mighty-mouse benchmark --tasks-dir ./my-tasks
```

## Project Architecture

Mighty Mouse is designed to keep experimental scripts clearly separated from the stable harness:

- `src/mighty_mouse/orchestrator/`: The core agent logic and execution loops.
- `src/mighty_mouse/services/`: Benchmark and verification services.
- `src/mighty_mouse/commands/`: CLI command implementations.
- `src/mighty_mouse/resources/`: Packaged configurations, prompts, and demo tasks.
- `data/evidence/`: Frozen snapshots of past validation runs proving the efficiency gains of the protocol.

## Evidence

The `data/evidence` directory contains the raw JSONs and reports proving the efficacy of this harness across 15 paired tasks producing 30 condition runs. Evidence-grade metrics confirm a 100% pass rate on Tier 1 tasks while achieving a 29.5% average latency reduction when using the Lean protocol profile.

## License

MIT License
