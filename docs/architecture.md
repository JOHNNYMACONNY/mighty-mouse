# Mighty Mouse Architecture

Canonical ownership map for current repository code, package metadata, and
verified import consumers. No future-state design. Update map when ownership,
package boundaries, or dependency direction changes.

## Authority and scope

- Source code, `pyproject.toml`, `mcp/pyproject.toml`, import consumers, and CI
  package checks provide architecture evidence.
- This document describes current ownership and dependency direction.
- ADRs, specifications, and research notes retain narrower decision or
  experiment authority. Research notes do not replace current-code evidence.
- No deprecation, removal, or future convergence claim follows from subsystem
  classification below.

## Subsystem map

| Context | Current paths | Ownership |
| --- | --- | --- |
| Core public runtime | `src/mighty_mouse/verifier/`, `src/mighty_mouse/protocols/`, `src/mighty_mouse/host/`, `src/mighty_mouse/commands/`, `src/mighty_mouse/cli.py` | `mighty-mouse` distribution. Project verification, versioned protocols, host integration, and CLI entry point. |
| Adaptive v2 domain/runtime | `src/mighty_mouse/v2/` | Shipped core subsystem. Records, state store, policy engine, routing/runtime, research/evaluation models, promotion, signals, telemetry, claims, bundles, status, and migration. |
| Compatibility seams | `src/mighty_mouse/v2/foundation.py`, `src/mighty_mouse/v2/seams.py`, `src/mighty_mouse/v2/__init__.py` | `foundation.py` re-export façade over deep v2 modules. `seams.py` typed Candidate, Signal, mutation-surface, verification-result, and mutation-adapter contracts. Public exports and import shape require compatibility review. |
| MCP transport/integration | `mcp/`, `mcp/src/mighty_mouse_mcp/` | Separate `mighty-mouse-mcp` distribution. Stdio server, tool hooks, host setup, verification, protocol, and signal recording. MCP imports core packages. |
| Research/evaluation | `eval/` | Repository research, benchmark, evaluator, mutation, autoresearch, local-model, and characterization context. `AutoresearchCycle` and `AutoresearchLoop` belong here. Eval consumes shipped core/v2/orchestrator seams; shipped core does not depend on eval. |
| Original local-model execution | `src/mighty_mouse/orchestrator/` | Retained local-model agent subsystem: Gemini client, model execution engine, response parser, agent, and swarm orchestration. Current eval consumers exist. No deprecated/dead classification. |
| Services and compatibility adapters | `src/mighty_mouse/services/` | Benchmark service plus verifier adapter shims. Command paths consume benchmark service; verifier shims delegate to `mighty_mouse.verifier`. Verifier authority remains in `src/mighty_mouse/verifier/`. |
| Evidence and study data | `data/evidence/` | Frozen historical, bare-control, and real-project evidence. Research input/output; no runtime ownership. |
| Build and release infrastructure | `pyproject.toml`, `mcp/pyproject.toml`, `.github/workflows/`, `scripts/` | Core and MCP packaging, CI, PyPI publication, portfolio synchronization, and changed-line quality checks. |

## Dependency direction

1. Core package metadata ships `mighty_mouse*` from `src/`; core runtime has no
   import path into `eval/` or `mighty_mouse_mcp`.
2. MCP package metadata depends on `mighty-mouse`; MCP may import core verifier,
   protocol, host, and v2 modules. Core must not import MCP transport.
3. `eval/` may consume core, v2, and orchestrator modules for research and
   evaluation. Core and MCP source must not depend on `eval/`.
4. `src/mighty_mouse/v2/` owns adaptive domain/runtime behavior. `foundation.py`
   and `seams.py` provide compatibility-sensitive paths consumed by host, MCP,
   eval, and v2 modules.
5. `src/mighty_mouse/services/verifiers/` provides adapter compatibility around
   core verifier functions. New verification semantics belong in
   `src/mighty_mouse/verifier/`.
6. `eval/autoresearch_cycle.py` may consume v2 seam types, but cycle lifecycle
   and loop operations remain research/evaluation ownership. No runtime-to-eval
   dependency follows from those type imports.

## Where new work belongs

| Work | First inspection point |
| --- | --- |
| Verification semantics, result contracts, scope, adherence, test execution | `src/mighty_mouse/verifier/` |
| Complexity-scaled protocol content | `src/mighty_mouse/protocols/` |
| Host identity, execution profile, tool contract, host-to-policy integration | `src/mighty_mouse/host/` and relevant `src/mighty_mouse/v2/` modules |
| Adaptive policy, records, promotion, signals, telemetry, bundles, claims | `src/mighty_mouse/v2/` |
| MCP tools, stdio transport, MCP-specific hooks | `mcp/` |
| Benchmarks, experiments, mutation, autoresearch, evaluation-only orchestration | `eval/` |
| Original local-model execution behavior | `src/mighty_mouse/orchestrator/` |
| Compatibility re-exports, typed boundary contracts, or service adapters | Existing seam or adapter path, after consumer/import review |
| Historical evidence, experiment artifacts, packaging, CI, release checks | `data/evidence/`, `docs/`, `pyproject.toml`, `mcp/pyproject.toml`, `.github/workflows/`, `scripts/` |

## Compatibility-sensitive surfaces

- `src/mighty_mouse/v2/foundation.py` re-exports records, store, promotion,
  and engine symbols. Preserve import paths while changing deep module layout.
- `src/mighty_mouse/v2/seams.py` defines frozen data contracts and
  `PolicyMutationAdapter`. Preserve field names, literals, and protocol
  behavior before changing eval or mutation code.
- `src/mighty_mouse/v2/__init__.py` exposes policy, engine, signal, and
  telemetry symbols. Treat exports as compatibility surface.
- `src/mighty_mouse/orchestrator/__init__.py` exposes Gemini, model-engine, and
  response-parser symbols. Inspect current consumers before moving or folding
  original execution code into v2.
- `src/mighty_mouse/services/verifiers/` contains delegating shims. Preserve
  caller paths while moving verifier implementation.
- `mcp/pyproject.toml` and `mcp/src/mighty_mouse_mcp/server.py` encode separate
  distribution and core-import direction. Check both package metadata and
  source imports before changing transport boundaries.
- `eval/autoresearch_cycle.py` and `eval/perpetual_loop.py` consume v2 seam
  types while retaining eval-owned lifecycle and concrete operation wiring.

## Non-decisions

- Original orchestrator remains separately classified; no deprecation or
  convergence policy established.
- Services remain mixed benchmark and compatibility context; no wholesale
  migration inferred.
- Research notes remain research or planning authority for their stated scope;
  they do not silently become current ownership declarations.
- Future refactors require fresh consumer, package, and test evidence against
  boundaries above.
