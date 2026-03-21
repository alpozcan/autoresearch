# autoresearch — iOS cold launch optimization

This is an experiment to have an LLM optimize iOS app cold launch time autonomously.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar22`). The branch `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files**: Read these files for full context:
   - `README.md` — repository context.
   - `prepare.py` — fixed harness: build, install, measure, score. Do not modify.
   - The 5 mutable Swift files in the target app (listed below).
4. **Verify the target app**: Check that `/Users/alp/Development/Apps/iOS/MiddleEarth` exists and has a `Project.swift` or `MiddleEarth.xcworkspace`. If the workspace is missing, run `cd /Users/alp/Development/Apps/iOS/MiddleEarth && tuist generate --no-open`.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Target app

- **Path**: `/Users/alp/Development/Apps/iOS/MiddleEarth`
- **Workspace**: `MiddleEarth.xcworkspace`
- **Scheme**: `MiddleEarth`
- **Bundle ID**: `me.alp.middleearth`
- **Simulator**: iPhone 17 Pro (UDID: `231ABE22-DA2D-4348-AB47-781009F53A63`)

### Files you can modify

These are the only files you may edit. They live under `/Users/alp/Development/Apps/iOS/MiddleEarth/`:

1. `MiddleEarth/Core/DependencyInjection/AppRegistry.swift` — service container setup
2. `MiddleEarth/MiddleEarthApp.swift` — SwiftUI App entry point
3. `MiddleEarth/Views/MainView.swift` — root view after splash
4. `MiddleEarth/Views/Common/SplashView.swift` — splash/loading screen
5. `MiddleEarth/Services/AppBootstrapService.swift` — startup orchestration

### Baseline metrics

```
cold_launch_ms:       558
service_reg_ms:       70
swiftdata_init_ms:    56
```

## Experimentation

Each experiment builds the app and measures cold launch on the simulator. You launch measurement simply as: `python prepare.py > run.log 2>&1`

**What you CAN do:**
- Modify the 5 Swift files listed above. Everything is fair game: lazy initialization, dependency injection order, async loading, deferred work, prewarming, caching, SwiftData configuration, view hierarchy restructuring, etc.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only. It contains the fixed build, measurement, and scoring logic.
- Add new Swift files or new dependencies. Work within the existing file structure.
- Modify files outside the 5 listed above.
- Break the app's functionality. The app must still launch, display its UI, and work correctly.

**The goal is simple: get the lowest cold_launch_ms.** This is the primary metric, analogous to val_bpb in the original autoresearch. Lower is better.

**composite_score** is a secondary metric that also accounts for service_registration_ms and swiftdata_init_ms. It's reported for the dashboard but cold_launch_ms is what determines keep/discard.

**App correctness** is a hard constraint. If the app crashes on launch or fails to display its UI, that's a failed experiment regardless of timing.

## Output format

Once `prepare.py` finishes it prints a summary like this:

```
---
cold_launch_ms:       392
service_reg_ms:       31
swiftdata_init_ms:    42
composite_score:      0.8022
build_seconds:        18.5
```

You can extract the key metric from the log file:

```
grep "^cold_launch_ms:" run.log
```

## Logging results

When an experiment is done, log it to `results.tsv` (tab-separated, NOT comma-separated — commas break in descriptions).

The TSV has a header row and 5 columns:

```
commit	cold_launch_ms	composite_score	status	description
```

1. git commit hash (short, 7 chars) — this is the commit in the target app repo
2. cold_launch_ms achieved (e.g. 392) — use 0 for crashes
3. composite_score (e.g. 0.8022) — use 0.0000 for crashes
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried

Example:

```
commit	cold_launch_ms	composite_score	status	description
a1b2c3d	558	1.0000	keep	baseline
b2c3d4e	392	1.2500	keep	lazy service registration
c3d4e5f	610	0.9100	discard	eager preloading (slower)
d4e5f6g	0	0.0000	crash	removed required init (crash on launch)
```

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autoresearch/mar22`).

LOOP FOREVER:

1. Look at the state of the 5 mutable Swift files
2. Form a hypothesis about what change might reduce cold launch time
3. Edit the Swift file(s) in the target app
4. git commit (in the target app repo)
5. Run the measurement: `python /Users/alp/Development/autoresearch/prepare.py > run.log 2>&1`
6. Read out the results: `grep "^cold_launch_ms:\|^composite_score:" run.log`
7. If the grep output is empty, the run failed. Run `tail -n 50 run.log` to read the error and attempt a fix.
8. Record the results in results.tsv (NOTE: do not commit results.tsv, leave it untracked by git)
9. If cold_launch_ms improved (lower), you "advance", keeping the change
10. If cold_launch_ms is equal or worse, revert the Swift file changes (`git checkout -- <files>` in the target app repo)

## Optimization strategies to try

Here are some ideas, roughly ordered by expected impact:

### High impact
- **Lazy service registration**: Defer non-essential services until after first frame
- **Async bootstrap**: Move heavy init work off the main thread
- **Deferred SwiftData**: Initialize ModelContainer lazily or on background thread
- **View hierarchy simplification**: Flatten deep view hierarchies in MainView
- **Splash screen as launch screen**: Use a static splash that doesn't depend on services

### Medium impact
- **Service registration ordering**: Register critical-path services first
- **Reduce import overhead**: Minimize work done at module load time
- **Cache warm-up deferral**: Move any cache preloading to post-launch
- **Background thread init**: Use Task.detached for non-UI initialization

### Lower impact / experimental
- **Precomputed layouts**: Cache initial layout calculations
- **Reduce property wrappers**: Minimize @StateObject/@EnvironmentObject at launch
- **Static type registration**: Replace runtime reflection with static registration
- **Combine publisher optimization**: Reduce publisher chain setup at init time

## Timeout

Each experiment should take ~1-2 minutes for the build + 3 launches. If a run exceeds 5 minutes total, kill it and treat it as a failure.

## Crashes

If a run crashes (build failure, runtime crash, etc.), use your judgment: If it's a typo or simple fix, correct and re-run. If the approach is fundamentally broken, skip it, log "crash", and move on.

## NEVER STOP

Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep or away and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous. If you run out of ideas, think harder — re-read the Swift files for new angles, try combining previous near-misses, try more radical restructuring. The loop runs until the human interrupts you, period.
