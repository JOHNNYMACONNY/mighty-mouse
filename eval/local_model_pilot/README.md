# Local-model pilot tasks

These three tasks validate the study runner at low, medium, and high complexity. They are public, unscored, and permanently excluded from the scored capability corpus.

Each task uses a disposable workspace and executable acceptance checks. A pilot result can validate orchestration and evidence capture, but it cannot support a model-performance claim.

After both models are installed in Ollama, run a pilot into a new output directory:

```bash
python -m eval.run_local_model_pilot \
  --task eval/local_model_pilot/low/task.json \
  --output-dir /tmp/mighty-mouse-pilot-low \
  --gemma-model gemma4:e4b \
  --reference-model gpt-oss:20b
```

The coordinator refuses to overwrite a previous output directory. Inspect pilot diagnostics without treating them as scored evidence:

```bash
python -m eval.analyze_local_model_study \
  --allow-pilot \
  /tmp/mighty-mouse-pilot-low
```
