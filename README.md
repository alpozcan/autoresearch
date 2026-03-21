# autoresearch — iOS edition

A fork of [karpathy/autoresearch](https://github.com/karpathy/autoresearch) adapted for iOS app cold launch optimization.

The original autoresearch lets an AI agent autonomously optimize an LLM training script, measuring val_bpb (validation bits per byte) as the single metric. This fork applies the same idea to iOS app startup performance: the agent modifies Swift source files, the harness builds and measures cold launch time on the simulator, and improvements are kept while regressions are discarded.

## How it works

The repo has the same minimal structure as the original:

- **`prepare.py`** — fixed harness: builds the iOS app with xcodebuild, installs on simulator, measures cold launch time via timing markers, computes composite score. Not modified by the agent.
- **`program.md`** — agent instructions. The agent reads this, then autonomously optimizes the target app's startup code in a keep/discard loop.
- **`run_models.py`** — multi-model runner. Runs experiments across 5 LLM models via OpenRouter API, tracking token usage, cost, and performance.
- **`dashboard.py`** — live web dashboard showing real-time progress, model comparison charts, and cost tracking.

The primary metric is **cold_launch_ms** (cold launch time in milliseconds) — lower is better.

## Target app

The target is a SwiftUI iOS app (MiddleEarth). The agent can modify 5 files that control startup:

1. `AppRegistry.swift` — service container / dependency injection
2. `MiddleEarthApp.swift` — SwiftUI App entry point
3. `MainView.swift` — root view
4. `SplashView.swift` — splash screen
5. `AppBootstrapService.swift` — startup orchestration

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Run a single measurement (build + 3 cold launches)
python prepare.py

# Run multi-model comparison (requires OPENROUTER_API_KEY in env or ~/.zshrc)
python run_models.py --experiments 10

# Start the live dashboard
python dashboard.py
# Open http://localhost:8050
```

## Multi-model comparison

`run_models.py` runs experiments across 5 models via OpenRouter:

| Model | Short name |
|-------|-----------|
| Claude Opus 4.6 | claude-opus |
| Claude Sonnet 4.6 | claude-sonnet |
| Gemini 2.5 Pro | gemini-pro |
| GPT-4.1 | gpt-4.1 |
| DeepSeek V3 | deepseek-v3 |

Each model gets its own git branch (`autoresearch/<model-name>`) in the target app and its own results directory (`results/<model-name>/`). The dashboard shows a live comparison.

## Running a single agent

For single-agent mode (like the original autoresearch), point your AI coding agent at this repo and prompt:

```
Read program.md and let's kick off a new experiment.
```

## Project structure

```
prepare.py       — iOS build + launch measurement harness (do not modify)
program.md       — agent instructions for single-agent mode
run_models.py    — multi-model OpenRouter runner
dashboard.py     — live web dashboard (http://localhost:8050)
requirements.txt — Python dependencies
results/         — per-model experiment histories (gitignored)
```

## Design choices

Inherited from the original autoresearch:

- **Single metric focus.** cold_launch_ms is the only thing that matters for keep/discard decisions.
- **Keep/discard loop.** Each experiment either improves the metric (keep) or doesn't (discard and revert).
- **Autonomous.** The agent runs indefinitely until manually stopped.
- **Minimal.** Small repo, few files, no complex infrastructure.

New in this fork:

- **Multi-model comparison.** Compare how different LLMs approach the same optimization problem.
- **Cost tracking.** Token usage and dollar cost per experiment, per model.
- **Live dashboard.** Real-time visualization of experiment progress.

## License

MIT
