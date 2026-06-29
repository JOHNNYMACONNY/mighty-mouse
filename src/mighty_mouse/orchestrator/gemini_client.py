import json
import os
import sys
import urllib.error
import urllib.request


class GeminiClient:
    """Model-agnostic client facade for Mighty Mouse.

    Supported providers:
      - gemini_api
      - openai_compat
      - ollama
      - sim (dev-only, requires allow_simulation: true)
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.provider = self.config.get("provider", "gemini_api")
        self.model_name = self.config.get("model")
        self.temperature = self.config.get("temperature", 0.2)
        self.max_tokens = self.config.get("max_tokens")
        self.allow_simulation = bool(self.config.get("allow_simulation", False))
        self.last_metadata = {}
        self._load_shims()
        self._resolve_provider()

    def _resolve_provider(self):
        if self.provider == "auto":
            if os.environ.get("GEMINI_API_KEY"):
                self.provider = "gemini_api"
                self.model_name = self.model_name or "gemini-2.5-flash"
            elif os.environ.get("OPENAI_BASE_URL"):
                self.provider = "openai_compat"
                self.model_name = self.model_name or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            else:
                raise ValueError(
                    "No live provider configured. Set provider in config, or export GEMINI_API_KEY / OPENAI_BASE_URL. "
                    "Simulation is opt-in only via provider=sim and allow_simulation=true."
                )

        if self.provider == "sim" and not self.allow_simulation:
            raise ValueError("Simulation provider is disabled unless allow_simulation=true is set in config.")

        if self.provider == "gemini_api":
            try:
                import google.generativeai as genai
            except ImportError as e:
                raise ImportError(
                    "google-generativeai is required for provider=gemini_api. Install project requirements first."
                ) from e

            api_key = os.environ.get(self.config.get("api_key_env", "GEMINI_API_KEY"))
            if not api_key:
                raise ValueError("Missing Gemini API key. Set GEMINI_API_KEY or configure api_key_env.")
            genai.configure(api_key=api_key)
            self._genai = genai
            self.model_name = self.model_name or "gemini-2.5-flash"
            self.model = genai.GenerativeModel(self.model_name)
        elif self.provider == "openai_compat":
            self.api_base = (self.config.get("api_base") or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
            self.api_key = os.environ.get(self.config.get("api_key_env", "OPENAI_API_KEY"), self.config.get("api_key", ""))
            self.model_name = self.model_name or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            if not self.api_base:
                raise ValueError("Missing api_base for openai_compat provider.")
        elif self.provider == "ollama":
            try:
                from .ollama_client import OllamaClient
            except ImportError:
                if os.path.dirname(__file__) not in sys.path:
                    sys.path.append(os.path.dirname(__file__))
                from ollama_client import OllamaClient
            self._ollama = OllamaClient(self.config)
            self.model_name = self._ollama.model_name
        elif self.provider != "sim":
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _load_shims(self):
        shim_path = os.path.join(os.path.dirname(__file__), "shims.json")
        try:
            with open(shim_path, "r") as f:
                self.shims = json.load(f)
        except Exception:
            self.shims = {}

    def generate_content(self, sys_instr, user_prompt):
        if self.provider == "ollama":
            res = self._ollama.generate_content(sys_instr, user_prompt)
            self.last_metadata = self._ollama.last_metadata
            return res

        if self.provider == "gemini_api":
            self.last_metadata = {
                "provider": self.provider,
                "model": self.model_name,
                "mode": "live",
            }
            import time
            start_time = time.time()
            
            response = None
            last_err = None
            for attempt in range(3):
                try:
                    response = self.model.generate_content(
                        f"SYSTEM: {sys_instr}\n\nUSER: {user_prompt}",
                        generation_config=self._genai.types.GenerationConfig(
                            temperature=self.temperature,
                            max_output_tokens=self.max_tokens,
                        ),
                    )
                    break
                except Exception as e:
                    last_err = e
                    if "429" in str(e) or "ResourceExhausted" in str(e):
                        wait = 30 * (attempt + 1)
                        print(f"[client] Quota exceeded (429). Retrying in {wait}s... (Attempt {attempt+1}/3)", file=sys.stderr)
                        time.sleep(wait)
                        continue
                    raise
            
            if response is None:
                raise last_err

            duration = time.time() - start_time
            
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            try:
                # Extract usage from response
                if hasattr(response, "usage_metadata"):
                    usage = {
                        "prompt_tokens": response.usage_metadata.prompt_token_count,
                        "completion_tokens": response.usage_metadata.candidates_token_count,
                        "total_tokens": response.usage_metadata.total_token_count,
                    }
            except Exception as e:
                print(f"[client] Warning: Failed to extract usage metadata: {e}", file=sys.stderr)

            self.last_metadata.update({
                "usage": usage,
                "latency_seconds": round(duration, 3)
            })
            return response.text

        if self.provider == "openai_compat":
            self.last_metadata = {
                "provider": self.provider,
                "model": self.model_name,
                "mode": "live",
                "api_base": self.api_base,
            }
            return self._generate_openai_compat(sys_instr, user_prompt)

        self.last_metadata = {
            "provider": self.provider,
            "model": self.model_name or "simulated-model",
            "mode": "simulation",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "latency_seconds": 0.0
        }
        return self._generate_simulated_content(sys_instr, user_prompt)

    def _generate_openai_compat(self, sys_instr, user_prompt):
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": sys_instr},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        req = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        import time
        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"openai_compat request failed: {e.code} {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"openai_compat request failed: {e}") from e
        duration = time.time() - start_time

        try:
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
            self.last_metadata.update({
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens") or 0,
                    "completion_tokens": usage.get("completion_tokens") or 0,
                    "total_tokens": usage.get("total_tokens") or 0,
                },
                "latency_seconds": round(duration, 3)
            })
            return content
        except Exception as e:
            raise RuntimeError(f"Unexpected openai_compat response: {body}") from e

    def _generate_simulated_content(self, sys_instr, user_prompt):
        has_chain = "Chain-of-Thought" in sys_instr
        has_disciplined = "Disciplined Scope" in sys_instr
        has_verify = "Self-Verification" in sys_instr

        tid = "unknown"
        if '"id": "' in user_prompt:
            tid = user_prompt.split('"id": "')[1].split('"')[0]

        round_2 = (
            "PREVIOUS ATTEMPT FAILED" in user_prompt
            or "Feedback:" in user_prompt
            or "fail" in user_prompt.lower()
        )

        success = True
        idx = 0
        try:
            parts = tid.split('_')
            idx = int(parts[1])

            instr_l = sys_instr.lower()
            if idx > 1400:
                has_precision = "precision" in instr_l or "extraction" in instr_l or "needle" in instr_l
                if not (has_precision or round_2):
                    success = False
            elif idx > 1200:
                is_hallucincation = (idx % 2 == 0) and not round_2
                has_reflection = "reflect" in instr_l or "self-correct" in instr_l or "loop" in instr_l
                if is_hallucincation:
                    success = False
                elif not has_reflection:
                    success = False
            elif idx > 1000:
                has_purge = "purge" in instr_l or "cull" in instr_l or "sanitize" in instr_l
                if not (has_purge or round_2):
                    success = False
            elif idx > 800:
                has_hygiene = "hygiene" in instr_l or "audit" in instr_l or "clean" in instr_l
                if not (has_hygiene or round_2):
                    success = False
            elif idx > 650:
                has_safety = "safety-first" in instr_l or "resolution" in instr_l or "integrity" in instr_l
                if not (has_safety or round_2):
                    success = False
            elif idx > 500:
                has_antagonist = "Antagonist" in sys_instr or "Hardening" in sys_instr or "Defensive" in sys_instr
                if not (has_antagonist or round_2):
                    success = False
            elif idx > 400:
                if not (has_verify or round_2):
                    success = False
            elif idx > 300:
                if not (has_disciplined or round_2):
                    success = False
            elif idx > 200:
                success = True
            elif idx > 100:
                if not ("Constraint" in user_prompt or round_2):
                    success = False
            elif idx >= 40:
                if not (has_verify or round_2):
                    success = False
            elif 30 <= idx < 40:
                if not (has_disciplined or round_2):
                    success = False
            elif 20 <= idx < 30:
                if not (has_chain or round_2):
                    success = False
        except Exception:
            pass

        if success:
            return self._generate_shim_response(tid, idx, round_2)
        return self._generate_fail_response(tid)

    def _generate_shim_response(self, tid, idx, round_2):
        if tid == "task_02_data_parse" and not round_2:
            return self._generate_fail_response(tid)

        shim = self.shims.get(tid)
        if not shim:
            prefix = tid[:7]
            shim = self.shims.get(prefix, {"fname": "stub.py", "code": "def stub(): pass", "extra": ""})

        fname = shim["fname"]
        code = shim["code"]
        extra_content = shim.get("extra", "")

        if idx > 650 and idx <= 800:
            extra_content += "\n# RESOLVED CONFLICT: Safety-First resolution applied."

        if 1000 < idx <= 1200:
            extra_content += "\n\n```delete:obsolete_shim.py\nPURGED\n```"
            extra_content += "\n# CASCADING SUCCESS: Structural dependencies resolved."

        if idx > 1400:
            code += "\n\n    def ping_singularity(self):\n        return 'singularity_verified'"

        if 800 < idx <= 1000:
            d_files = ["legacy_utils.py", "deprecated_api.py", "old_config.py"]
            d_file = d_files[idx % len(d_files)]
            extra_content += f"\n\n```python:{d_file}\n# DRIFT FIXED: Sanitized syntax errors and restored hygiene.\ndef fixed_drift(): pass\n```"

        meta_token = ""
        if idx > 650 and idx <= 800:
            meta_token = "\n# RESOLVED CONFLICT: Safety-First resolution applied."

        return f"""# Mighty Mouse Checklist - {tid}

## Phase 1: Planning
The objective for {tid} is to implement {fname} correctly according to specifications. We will identify all constraints and target files.
---
## Phase 2: Activity
The implementation of {fname} has been completed with comprehensive logic and adherence to the requested patterns.
---
## Phase 3: Verification
The code has been self-verified against the internal checklist. All logic gates for {tid} are passing.

```python:{fname}
{code}{meta_token}
```
{extra_content}"""

    def _generate_fail_response(self, tid):
        return f"""# Mighty Mouse Checklist - {tid}

## Phase 1: Planning
Failing this intentionally to test Round 2 recovery for {tid}.
---
## Phase 2: Activity
Injecting intentional error to trigger agentic reflection.
---
## Phase 3: Verification
Forced failure.

```python:error.py
def error(): raise ValueError('Simulated Failure')
```"""
