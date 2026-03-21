"""
iOS app launch performance harness for autoresearch experiments.
Builds the app, installs on simulator, measures cold launch time.

Usage:
    python prepare.py              # full build + measure (3 launches, median)
    python prepare.py --runs 5     # 5 launches instead of 3
    python prepare.py --skip-build # measure only (skip xcodebuild)

This is the IMMUTABLE harness. Do not modify.
"""

import os
import sys
import re
import time
import json
import argparse
import subprocess
import statistics

# ---------------------------------------------------------------------------
# Constants (fixed, do not modify)
# ---------------------------------------------------------------------------

TARGET_PATH = "/Users/alp/Development/Apps/iOS/MiddleEarth"
WORKSPACE = os.path.join(TARGET_PATH, "MiddleEarth.xcworkspace")
SCHEME = "MiddleEarth"
DEVICE_UDID = "231ABE22-DA2D-4348-AB47-781009F53A63"
DESTINATION = "platform=iOS Simulator,name=iPhone 17 Pro,OS=26.2"
BUNDLE_ID = "me.alp.middleearth"

AUTORESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
DERIVED_DATA_PATH = os.path.join(AUTORESEARCH_DIR, "Derived")
APP_PATH = os.path.join(DERIVED_DATA_PATH, "Build", "Products",
                        "Debug-iphonesimulator", "MiddleEarth.app")

# Baseline measurements from App Store v2.0 commit (11a74a6)
# Established from 3 median cold launches on a clean simulator
BASELINE = {
    "cold_launch_ms": 558,
    "service_registration_ms": 70,
    "swiftdata_init_ms": 56,
}

# Scoring weights for composite score (lower ms = better score)
SCORING_WEIGHTS = {
    "cold_launch_ms": 0.70,
    "service_registration_ms": 0.15,
    "swiftdata_init_ms": 0.15,
}

# Number of measurement runs (median is taken)
DEFAULT_RUNS = 3

# Timing marker patterns in app stdout
# Expected format: [LAUNCH T+Xms] and [REGISTRY T+Xms]
LAUNCH_PATTERN = re.compile(r"\[LAUNCH T\+(\d+)ms\].*MainView\.onAppear")
REGISTRY_PATTERN = re.compile(r"\[REGISTRY T\+(\d+)ms\].*All services registered")
SWIFTDATA_PATTERN = re.compile(r"\[REGISTRY T\+(\d+)ms\].*ModelContainer created")

# Files the agent is allowed to modify
MUTABLE_FILES = [
    "MiddleEarth/Core/DependencyInjection/AppRegistry.swift",
    "MiddleEarth/MiddleEarthApp.swift",
    "MiddleEarth/Views/MainView.swift",
    "MiddleEarth/Views/Common/SplashView.swift",
    "MiddleEarth/Services/AppBootstrapService.swift",
]

# ---------------------------------------------------------------------------
# Workspace generation
# ---------------------------------------------------------------------------

def ensure_workspace():
    """Generate Xcode workspace with Tuist if it doesn't exist."""
    if os.path.exists(WORKSPACE):
        return True
    print("Workspace not found, running tuist generate...")
    result = subprocess.run(
        ["tuist", "generate", "--no-open"],
        cwd=TARGET_PATH,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"tuist generate failed:\n{result.stderr}")
        return False
    return True

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_app():
    """Build the iOS app with xcodebuild. Returns (success, build_seconds)."""
    if not ensure_workspace():
        return False, 0.0

    print("Building app...")
    t0 = time.time()
    result = subprocess.run(
        [
            "xcodebuild", "build",
            "-workspace", WORKSPACE,
            "-scheme", SCHEME,
            "-destination", DESTINATION,
            "-derivedDataPath", DERIVED_DATA_PATH,
            "-quiet",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    t1 = time.time()
    build_seconds = t1 - t0

    if result.returncode != 0:
        print(f"Build FAILED ({build_seconds:.1f}s)")
        # Print last 30 lines of stderr for diagnostics
        lines = result.stderr.strip().split("\n")
        for line in lines[-30:]:
            print(f"  {line}")
        return False, build_seconds

    print(f"Build succeeded ({build_seconds:.1f}s)")
    return True, build_seconds

# ---------------------------------------------------------------------------
# Simulator management
# ---------------------------------------------------------------------------

def boot_simulator():
    """Boot the target simulator if not already booted."""
    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "-j"],
        capture_output=True, text=True,
    )
    devices = json.loads(result.stdout)
    for runtime, device_list in devices.get("devices", {}).items():
        for device in device_list:
            if device["udid"] == DEVICE_UDID:
                if device["state"] == "Booted":
                    return True
                print(f"Booting simulator {device['name']}...")
                subprocess.run(
                    ["xcrun", "simctl", "boot", DEVICE_UDID],
                    capture_output=True, text=True,
                )
                time.sleep(3)
                return True
    print(f"Simulator {DEVICE_UDID} not found!")
    return False


def install_app():
    """Install the built app on the simulator."""
    if not os.path.exists(APP_PATH):
        print(f"App not found at {APP_PATH}")
        return False

    if not boot_simulator():
        return False

    print("Installing app on simulator...")
    result = subprocess.run(
        ["xcrun", "simctl", "install", DEVICE_UDID, APP_PATH],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        print(f"Install failed: {result.stderr}")
        return False
    return True


def terminate_app():
    """Terminate the app if running."""
    subprocess.run(
        ["xcrun", "simctl", "terminate", DEVICE_UDID, BUNDLE_ID],
        capture_output=True, text=True,
    )
    time.sleep(0.5)

# ---------------------------------------------------------------------------
# Launch measurement
# ---------------------------------------------------------------------------

def measure_single_launch(run_index=0):
    """
    Cold launch the app and parse timing markers from stdout.
    Returns dict with timing values or None on failure.
    """
    terminate_app()
    # Allow process cleanup for cold launch
    time.sleep(2.0)

    print(f"  Launch {run_index + 1}: ", end="", flush=True)

    # Launch and capture stdout via simctl
    process = subprocess.Popen(
        ["xcrun", "simctl", "launch", "--console-pty", DEVICE_UDID, BUNDLE_ID],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    output_lines = []
    metrics = {}
    start_time = time.time()
    timeout = 30  # seconds

    try:
        while time.time() - start_time < timeout:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue
            output_lines.append(line)

            # Parse timing markers
            m = LAUNCH_PATTERN.search(line)
            if m:
                metrics["cold_launch_ms"] = int(m.group(1))

            m = REGISTRY_PATTERN.search(line)
            if m:
                metrics["service_registration_ms"] = int(m.group(1))

            m = SWIFTDATA_PATTERN.search(line)
            if m:
                metrics["swiftdata_init_ms"] = int(m.group(1))

            # Once we have the launch marker, we're done
            if "cold_launch_ms" in metrics:
                break
    except Exception as e:
        print(f"ERROR: {e}")
        return None
    finally:
        terminate_app()
        try:
            process.kill()
        except ProcessLookupError:
            pass

    if "cold_launch_ms" not in metrics:
        print("TIMEOUT (no timing markers found)")
        if output_lines:
            print("    Last 5 lines of output:")
            for line in output_lines[-5:]:
                print(f"      {line.rstrip()}")
        return None

    launch = metrics.get("cold_launch_ms", 0)
    reg = metrics.get("service_registration_ms", 0)
    swd = metrics.get("swiftdata_init_ms", 0)
    print(f"cold={launch}ms  reg={reg}ms  swd={swd}ms")
    return metrics


def measure_launch(num_runs=DEFAULT_RUNS):
    """
    Perform multiple cold launches and return median metrics.
    Returns (metrics_dict, all_runs) or (None, []) on failure.
    """
    all_runs = []
    for i in range(num_runs):
        result = measure_single_launch(i)
        if result is not None:
            all_runs.append(result)

    if not all_runs:
        return None, []

    # Take median of each metric
    median_metrics = {}
    for key in ["cold_launch_ms", "service_registration_ms", "swiftdata_init_ms"]:
        values = [r[key] for r in all_runs if key in r]
        if values:
            median_metrics[key] = int(statistics.median(values))
        else:
            median_metrics[key] = 0

    return median_metrics, all_runs

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_composite_score(metrics):
    """
    Compute composite score from metrics. Score = weighted average of
    (baseline / measured) ratios. Higher is better. 1.0 = baseline performance.
    Values > 1.0 mean improvement over baseline.
    """
    score = 0.0
    for key, weight in SCORING_WEIGHTS.items():
        baseline_val = BASELINE[key]
        measured_val = metrics.get(key, baseline_val)
        if measured_val <= 0:
            measured_val = 1  # avoid division by zero
        ratio = baseline_val / measured_val
        score += weight * ratio
    return round(score, 4)

# ---------------------------------------------------------------------------
# Full evaluation pipeline
# ---------------------------------------------------------------------------

def evaluate(num_runs=DEFAULT_RUNS, skip_build=False):
    """
    Full evaluation: build, install, measure.
    Returns dict with all metrics or None on failure.
    """
    build_seconds = 0.0

    if not skip_build:
        success, build_seconds = build_app()
        if not success:
            return None

    if not install_app():
        return None

    metrics, all_runs = measure_launch(num_runs)
    if metrics is None:
        return None

    metrics["build_seconds"] = round(build_seconds, 1)
    metrics["composite_score"] = compute_composite_score(metrics)
    metrics["all_runs"] = all_runs
    return metrics

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="iOS app launch performance harness"
    )
    parser.add_argument(
        "--runs", type=int, default=DEFAULT_RUNS,
        help=f"Number of measurement runs (default: {DEFAULT_RUNS})"
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip the build step (measure existing install)"
    )
    args = parser.parse_args()

    print(f"Target:     {TARGET_PATH}")
    print(f"Bundle ID:  {BUNDLE_ID}")
    print(f"Simulator:  {DEVICE_UDID}")
    print(f"Runs:       {args.runs}")
    print()

    result = evaluate(num_runs=args.runs, skip_build=args.skip_build)

    if result is None:
        print("\n--- EVALUATION FAILED ---")
        sys.exit(1)

    cold = result["cold_launch_ms"]
    reg = result.get("service_registration_ms", 0)
    swd = result.get("swiftdata_init_ms", 0)
    score = result["composite_score"]
    build_s = result["build_seconds"]

    print()
    print("---")
    print(f"cold_launch_ms:       {cold}")
    print(f"service_reg_ms:       {reg}")
    print(f"swiftdata_init_ms:    {swd}")
    print(f"composite_score:      {score}")
    print(f"build_seconds:        {build_s}")
