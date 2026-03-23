# autoresearch — iOS Edition

A fork of [karpathy/autoresearch](https://github.com/karpathy/autoresearch) adapted for iOS app cold launch optimization. 5+ frontier AI models race to find the best startup optimizations on a production SwiftUI app.

> *"The goal is not to emulate a single PhD student, it's to emulate a research community of them."* — [Andrej Karpathy](https://x.com/karpathy/status/2030705271627284816)

## Results

**Target app:** [Middle Earth Explorer](https://apps.apple.com/app/middle-earth-explorer/id6746390838) — a SwiftUI iOS app with 11 SwiftData entity types, 1600+ seeded records, 51 locations, 90+ events, and 43-language localization.

**Baseline:** 558ms cold launch

| Model | Best (ms) | Improvement | Experiments | Keeps | Cost |
|-------|-----------|-------------|-------------|-------|------|
| **Claude Opus 4.6** | **189ms** | **-66%** | 30 | 8 | $3.60 |
| Gemini 2.5 Pro | 278ms | -50% | 25 | 7 | $2.25 |
| DeepSeek V3 | 344ms | -38% | 21 | 6 | $0.06 |
| Claude Sonnet 4.6 | 353ms | -37% | 30 | 3 | $1.50 |
| GPT-4.1 | 413ms | -26% | 11 | 4 | $0.27 |

**Total: ~117 experiments across 5 models for $12.28 on [OpenRouter](https://openrouter.ai).**

<!-- TODO: Add chart screenshots after all models finish -->
<!-- ![Cold Launch Over Time](assets/timeline.png) -->
<!-- ![Best Cold Launch by Model](assets/comparison.png) -->

## How It Works

The original [autoresearch](https://github.com/karpathy/autoresearch) lets an AI agent autonomously optimize LLM training, measuring `val_bpb` as the metric. This fork applies the same loop to iOS app startup performance:

1. **Agent reads** the mutable Swift files and proposes an optimization
2. **Harness builds** the app with `xcodebuild` and installs on iOS Simulator
3. **Harness measures** cold launch time (median of 3 launches via `xcrun simctl`)
4. **Keep or discard** — if cold launch improved, keep the change and commit; otherwise revert
5. **Repeat** — agent sees results from previous experiments and proposes the next hypothesis

Each model runs on its own `git branch`, completely isolated from other models' experiments.

## Karpathy's Autoresearch Adaptation

| Original (LLM training) | iOS Fork |
|---|---|
| `prepare.py` — data preparation | `prepare.py` — xcodebuild + simctl harness |
| `train.py` — training script | Swift source files (modified by agent) |
| `val_bpb` — validation metric | `cold_launch_ms` — cold launch time |
| `program.md` — agent instructions | `program.md` — iOS optimization constraints |
| Single model | Multi-model comparison via OpenRouter |

See [Karpathy's original tweet](https://x.com/karpathy/status/2030371219518931079) introducing autoresearch.

## Project Structure

```
prepare.py        — iOS build + launch measurement harness (immutable)
program.md        — Agent instructions and iOS constraints
run_models.py     — Multi-model experiment runner (OpenRouter API)
dashboard.py      — Live web dashboard (http://localhost:8050)
requirements.txt  — Python dependencies
results/          — Per-model experiment histories (JSON)
```

## Configuration

Before running, update the paths in `prepare.py` to point to your iOS project:

```python
TARGET_PATH = "/path/to/your/ios/project"
WORKSPACE = os.path.join(TARGET_PATH, "YourApp.xcworkspace")
SCHEME = "YourApp"
BUNDLE_ID = "com.yourcompany.yourapp"
```

Also update `program.md` with your app's file paths and baseline metrics.

## Quick Start

```bash
# Clone
git clone https://github.com/alpozcan/autoresearch.git
cd autoresearch

# Install dependencies
pip install -r requirements.txt

# Set your OpenRouter API key
export OPENROUTER_API_KEY="sk-or-..."

# Run experiments (all models, 10 each)
python run_models.py --experiments 10

# Run a specific model
python run_models.py --models claude-opus --experiments 30

# Start the live dashboard
python dashboard.py
# Open http://localhost:8050

# Run a single measurement (build + 3 cold launches)
python prepare.py
```

## Multi-Model Comparison

`run_models.py` runs experiments across multiple models via [OpenRouter](https://openrouter.ai):

| Model | OpenRouter ID | Input $/1M | Output $/1M |
|-------|---------------|------------|-------------|
| Claude Opus 4.6 | `anthropic/claude-opus-4.6` | $5.00 | $25.00 |
| Claude Sonnet 4.6 | `anthropic/claude-sonnet-4.6` | $3.00 | $15.00 |
| Gemini 2.5 Pro | `google/gemini-2.5-pro` | $1.25 | $10.00 |
| GPT-4.1 | `openai/gpt-4.1` | $2.00 | $8.00 |
| DeepSeek V3 | `deepseek/deepseek-chat-v3-0324` | $0.20 | $0.77 |

## Target App

The target is [Middle Earth Explorer](https://apps.apple.com/app/middle-earth-explorer/id6746390838), a production SwiftUI iOS app. The agent can modify 5 files that control startup:

| File | Role |
|------|------|
| `AppRegistry.swift` | Service container, dependency injection |
| `MiddleEarthApp.swift` | SwiftUI App entry point, launch sequence |
| `MainView.swift` | Root view, tab construction |
| `SplashView.swift` | Splash screen |
| `AppBootstrapService.swift` | Startup orchestration |

## Key Findings

**Opus's 3 breakthrough experiments** accounted for 78% of total improvement:
- **#1** Parallel ModelContainer init — 558ms → 441ms (-117ms)
- **#6** Lazy tab construction — 414ms → 307ms (-107ms)
- **#23** Sync ModelContainer in App.init() — 258ms → 194ms (-64ms)

**Model personalities emerged:**
- **Opus** — "High-risk researcher." Made architectural changes no other model attempted.
- **Gemini** — "Steady climber." Consistent improvement, zero regressions after token fix.
- **DeepSeek** — "Budget champion." 38% improvement for $0.06 (1.7% of Opus's cost).
- **Sonnet** — "Cautious engineer." Stayed in the service layer, never touched view hierarchy.
- **GPT-4.1** — "Stubborn surgeon." 100% success rate for 4 experiments, then 7 identical crashes.

**Hit rate comparison:** Karpathy found 20 optimizations in 700 LLM experiments (2.9%). Opus found 8 in 30 iOS experiments (27%).

## Dashboard

The live dashboard at `http://localhost:8050` shows:
- Real-time experiment progress for all models
- Cold launch timeline chart (lower = better)
- Best cold launch by model (bar chart)
- Model leaderboard (ranked by best result)
- Recent experiments table with keep/discard status
- Cost tracking per model

## Design Principles

Inherited from the original autoresearch:
- **Single metric focus.** `cold_launch_ms` drives all keep/discard decisions.
- **Keep/discard loop.** Each experiment either improves or gets reverted.
- **Autonomous.** Models run without human intervention.
- **Minimal.** Small repo, few files, no complex infrastructure.

New in this fork:
- **Multi-model comparison.** 5+ models race on the same optimization problem.
- **Cost tracking.** Token usage and dollar cost per experiment, per model.
- **Live dashboard.** Real-time Plotly.js visualization with auto-refresh.
- **iOS toolchain.** xcodebuild + simctl harness for build-measure cycles.

## Acknowledgments

This project is a fork of [karpathy/autoresearch](https://github.com/karpathy/autoresearch) by [Andrej Karpathy](https://x.com/karpathy). The original concept of autonomous AI-driven research loops inspired this iOS adaptation.

## License

MIT — see [LICENSE](LICENSE) for details.
