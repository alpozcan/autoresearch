---
name: autoresearch-ios
description: Autonomously optimize iOS app cold launch time using Karpathy's autoresearch pattern. Runs a hypothesize → modify → build → measure → keep/discard loop on your SwiftUI app.
disable-model-invocation: false
context: fork
---

# autoresearch-ios

Optimize the iOS app's cold launch time autonomously using the autoresearch pattern.

## What this skill does

This skill runs an autonomous optimization loop on your iOS app's startup code. It reads your Swift source files, forms a hypothesis about what might reduce cold launch time, makes the change, builds and measures on the iOS Simulator, and keeps the change if it improved — otherwise reverts. This loop repeats until you stop it.

The approach is adapted from [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) which originally optimized LLM training. We replace `val_bpb` with `cold_launch_ms` and `train.py` with Swift source files.

## Before you start

1. Read `program.md` in this repository for the full experiment protocol, constraints, optimization strategies, and output format.
2. Read `prepare.py` to understand the build-measure harness (do not modify it).
3. Update the constants in `prepare.py` to point to your iOS project:
   - `TARGET_PATH` — path to your Xcode project
   - `WORKSPACE` — your `.xcworkspace` path
   - `SCHEME` — your Xcode scheme name
   - `BUNDLE_ID` — your app's bundle identifier
   - `DEVICE_UDID` — your target simulator UDID (find with `xcrun simctl list devices`)
4. Update `MUTABLE_FILES` in `prepare.py` with the Swift files the agent is allowed to modify.
5. Update `BASELINE` in `prepare.py` with your app's current cold launch metrics.
6. Update `program.md` with your app's file paths, baseline metrics, and any app-specific constraints.

## Usage

```
/autoresearch-ios [number-of-experiments]
```

If no argument is given, the loop runs indefinitely until manually stopped.

## How it works

The skill follows the protocol defined in `program.md`:

1. **Read** the mutable Swift files listed in `program.md`
2. **Hypothesize** a change that might reduce `cold_launch_ms`
3. **Edit** the Swift file(s) in the target app
4. **Commit** the change in the target app repo
5. **Measure** by running `python prepare.py` (builds with xcodebuild, installs on simulator, runs 3 cold launches, takes median)
6. **Keep or discard** — if `cold_launch_ms` improved, keep; otherwise `git checkout` to revert
7. **Log** the result and repeat

## Constraints (from program.md)

- Only modify the files listed in `MUTABLE_FILES`
- Never modify `prepare.py`
- Never add new files or dependencies
- App must still launch and function correctly
- Primary metric: `cold_launch_ms` (lower = better)
- Each experiment should complete in 1-2 minutes

## Multi-model mode

For running multiple AI models in parallel comparison (like the original 10-model benchmark), use `run_models.py` instead:

```bash
export OPENROUTER_API_KEY="sk-or-..."
python run_models.py --experiments 15
python dashboard.py  # live results at http://localhost:8050
```

## Reference

See `program.md` for the complete experiment protocol including:
- Detailed optimization strategies (high/medium/low impact)
- Output format and result logging
- Crash handling guidelines
- The autonomous experiment loop specification

## Results from Middle Earth Explorer

202 experiments across 10 models optimized cold launch from 558ms to 189ms (-66%) for $17.05 total on OpenRouter. Full results at [github.com/alpozcan/autoresearch](https://github.com/alpozcan/autoresearch).
