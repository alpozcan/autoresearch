"""
Multi-model autoresearch runner.
Runs iOS cold launch optimization experiments across multiple LLM models
via OpenRouter API, tracking performance, cost, and token usage.

Usage:
    python run_models.py                          # run all models, 50 experiments each
    python run_models.py --experiments 10          # 10 experiments per model
    python run_models.py --models claude-sonnet    # run only matching models
    python run_models.py --sequential              # run models one at a time
"""

import os
import sys
import re
import json
import time
import shutil
import argparse
import subprocess
import statistics
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODELS = [
    {
        "id": "anthropic/claude-opus-4.6",
        "short": "claude-opus",
        "cost_per_1m_input": 5.00,
        "cost_per_1m_output": 25.00,
    },
    {
        "id": "anthropic/claude-sonnet-4.6",
        "short": "claude-sonnet",
        "cost_per_1m_input": 3.00,
        "cost_per_1m_output": 15.00,
    },
    {
        "id": "google/gemini-2.5-pro",
        "short": "gemini-pro",
        "cost_per_1m_input": 1.25,
        "cost_per_1m_output": 10.00,
    },
    {
        "id": "openai/gpt-4.1",
        "short": "gpt-4.1",
        "cost_per_1m_input": 2.00,
        "cost_per_1m_output": 8.00,
    },
    {
        "id": "deepseek/deepseek-chat-v3-0324",
        "short": "deepseek-v3",
        "cost_per_1m_input": 0.20,
        "cost_per_1m_output": 0.77,
    },
]

AUTORESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_APP_DIR = "/Users/alp/Development/Apps/iOS/MiddleEarth"
RESULTS_DIR = os.path.join(AUTORESEARCH_DIR, "results")
DEFAULT_EXPERIMENTS = 30

MUTABLE_FILES = [
    "MiddleEarth/Core/DependencyInjection/AppRegistry.swift",
    "MiddleEarth/MiddleEarthApp.swift",
    "MiddleEarth/Views/MainView.swift",
    "MiddleEarth/Views/Common/SplashView.swift",
    "MiddleEarth/Services/AppBootstrapService.swift",
]

# ---------------------------------------------------------------------------
# OpenRouter API key
# ---------------------------------------------------------------------------

def get_api_key():
    """Read OpenRouter API key from env or ~/.zshrc."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        result = subprocess.run(
            ["grep", "OPENROUTER_API_KEY", os.path.expanduser("~/.zshrc")],
            capture_output=True, text=True,
        )
        for line in result.stdout.strip().split("\n"):
            m = re.search(r'"([^"]+)"', line)
            if m:
                return m.group(1)
    except Exception:
        pass
    print("ERROR: OPENROUTER_API_KEY not found in env or ~/.zshrc")
    sys.exit(1)

# ---------------------------------------------------------------------------
# OpenRouter API
# ---------------------------------------------------------------------------

def call_openrouter(api_key, model_id, messages, max_tokens=4096):
    """
    Call OpenRouter API. Returns (response_text, usage_dict, elapsed_seconds).
    """
    import urllib.request
    import urllib.error

    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = json.dumps({
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("HTTP-Referer", "https://github.com/alp/autoresearch")

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"  API error {e.code}: {error_body[:200]}")
        return None, {}, time.time() - t0
    except Exception as e:
        print(f"  API error: {e}")
        return None, {}, time.time() - t0

    elapsed = time.time() - t0
    usage = body.get("usage", {})
    choices = body.get("choices", [])
    text = choices[0]["message"]["content"] if choices else ""
    return text, usage, elapsed

# ---------------------------------------------------------------------------
# File management
# ---------------------------------------------------------------------------

def read_mutable_files():
    """Read current contents of all mutable Swift files."""
    contents = {}
    for rel_path in MUTABLE_FILES:
        full_path = os.path.join(TARGET_APP_DIR, rel_path)
        if os.path.exists(full_path):
            with open(full_path, "r") as f:
                contents[rel_path] = f.read()
    return contents


def backup_mutable_files():
    """Create backup of mutable files. Returns dict of path->content."""
    return read_mutable_files()


def restore_mutable_files(backup):
    """Restore mutable files from backup."""
    for rel_path, content in backup.items():
        full_path = os.path.join(TARGET_APP_DIR, rel_path)
        with open(full_path, "w") as f:
            f.write(content)


def apply_patch(response_text, current_files):
    """
    Parse model response for file edits and apply them.
    Expects code blocks with file paths, e.g.:

    ```swift
    // FILE: MiddleEarth/MiddleEarthApp.swift
    <full file content>
    ```

    Returns (success, files_changed, lines_changed).
    """
    # Pattern: ```swift or ``` followed by // FILE: <path>
    file_pattern = re.compile(
        r"```(?:swift)?\s*\n"
        r"// FILE:\s*(.+?)\s*\n"
        r"(.*?)"
        r"```",
        re.DOTALL,
    )

    matches = file_pattern.findall(response_text)
    if not matches:
        # Try alternative pattern: just look for full file replacements
        alt_pattern = re.compile(
            r"```(?:swift)?\s*\n"
            r"(.*?)"
            r"```",
            re.DOTALL,
        )
        alt_matches = alt_pattern.findall(response_text)
        if not alt_matches:
            return False, 0, 0

    files_changed = 0
    total_lines_changed = 0

    for file_path, content in matches:
        file_path = file_path.strip()
        # Normalize path
        if not any(file_path.endswith(mf.split("/")[-1]) for mf in MUTABLE_FILES):
            continue

        # Find the matching mutable file
        target_rel = None
        for mf in MUTABLE_FILES:
            if file_path.endswith(mf.split("/")[-1]) or file_path == mf:
                target_rel = mf
                break

        if target_rel is None:
            continue

        full_path = os.path.join(TARGET_APP_DIR, target_rel)
        old_content = current_files.get(target_rel, "")
        new_content = content.strip() + "\n"

        if new_content != old_content:
            with open(full_path, "w") as f:
                f.write(new_content)
            files_changed += 1
            old_lines = old_content.count("\n")
            new_lines = new_content.count("\n")
            total_lines_changed += abs(new_lines - old_lines) + sum(
                1 for a, b in zip(
                    old_content.split("\n"), new_content.split("\n")
                ) if a != b
            )

    return files_changed > 0, files_changed, total_lines_changed

# ---------------------------------------------------------------------------
# Measurement (uses prepare.py)
# ---------------------------------------------------------------------------

def run_measurement():
    """Run prepare.py and parse results. Returns metrics dict or None."""
    result = subprocess.run(
        [sys.executable, os.path.join(AUTORESEARCH_DIR, "prepare.py")],
        capture_output=True, text=True, timeout=600,
        cwd=AUTORESEARCH_DIR,
    )

    output = result.stdout + "\n" + result.stderr

    if result.returncode != 0:
        print(f"  Measurement failed (exit {result.returncode})")
        lines = output.strip().split("\n")
        for line in lines[-10:]:
            print(f"    {line}")
        return None

    metrics = {}
    for line in output.split("\n"):
        m = re.match(r"^(cold_launch_ms|service_reg_ms|swiftdata_init_ms|composite_score|build_seconds):\s+(.+)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            try:
                metrics[key] = float(val) if "." in val else int(val)
            except ValueError:
                pass

    if "cold_launch_ms" not in metrics:
        print("  Could not parse cold_launch_ms from output")
        return None

    return metrics

# ---------------------------------------------------------------------------
# Experiment prompt
# ---------------------------------------------------------------------------

def build_prompt(model_short, experiment_num, current_files, history):
    """Build the prompt for the model."""
    system = (
        "You are an iOS performance engineer optimizing cold launch time for a SwiftUI app. "
        "You will be given the current source code of 5 Swift files that control app startup. "
        "Your goal: reduce cold_launch_ms (lower is better). Baseline is 558ms.\n\n"
        "RULES:\n"
        "- You may only modify the 5 files listed below\n"
        "- The app must still launch correctly and display its UI\n"
        "- Return COMPLETE file contents for any file you change\n"
        "- Use this exact format for each file:\n"
        "```swift\n"
        "// FILE: <relative/path/to/file.swift>\n"
        "<complete file content>\n"
        "```\n"
        "- Start your response with a one-line HYPOTHESIS of what you're trying\n"
        "- Only include files you actually changed\n"
    )

    user_parts = [f"Experiment #{experiment_num}\n"]

    if history:
        user_parts.append("Previous experiments (most recent last):")
        for h in history[-10:]:
            status = h.get("status", "?")
            desc = h.get("description", "?")
            cold = h.get("cold_launch_ms", "?")
            user_parts.append(f"  #{h.get('num', '?')}: {cold}ms ({status}) — {desc}")
        user_parts.append("")

    user_parts.append("Current file contents:\n")
    for rel_path, content in current_files.items():
        user_parts.append(f"--- {rel_path} ---")
        user_parts.append(content)
        user_parts.append("")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_parts)},
    ]
    return messages

# ---------------------------------------------------------------------------
# Per-model experiment runner
# ---------------------------------------------------------------------------

def run_model_experiments(model_config, api_key, num_experiments):
    """Run all experiments for a single model."""
    model_id = model_config["id"]
    model_short = model_config["short"]
    cost_in = model_config["cost_per_1m_input"]
    cost_out = model_config["cost_per_1m_output"]

    print(f"\n{'='*60}")
    print(f"MODEL: {model_id}")
    print(f"{'='*60}")

    # Setup results directory
    model_results_dir = os.path.join(RESULTS_DIR, model_short)
    os.makedirs(model_results_dir, exist_ok=True)

    # Load existing history
    history_path = os.path.join(model_results_dir, "history.json")
    if os.path.exists(history_path):
        with open(history_path, "r") as f:
            history = json.load(f)
    else:
        history = []

    start_experiment = len(history) + 1

    # Setup git branch from the App Store v2.0 baseline commit
    branch_name = f"autoresearch/{model_short}"
    subprocess.run(
        ["git", "checkout", "autoresearch/baseline"],
        cwd=TARGET_APP_DIR, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "checkout", "-B", branch_name],
        cwd=TARGET_APP_DIR, capture_output=True, text=True,
    )

    best_cold_launch = 558  # baseline from App Store v2.0
    total_cost = sum(h.get("cost_usd", 0) for h in history)
    total_input_tokens = sum(h.get("input_tokens", 0) for h in history)
    total_output_tokens = sum(h.get("output_tokens", 0) for h in history)

    for exp_num in range(start_experiment, start_experiment + num_experiments):
        print(f"\n--- Experiment {exp_num}/{start_experiment + num_experiments - 1} ({model_short}) ---")

        # Backup current files
        backup = backup_mutable_files()
        current_files = read_mutable_files()

        # Build prompt and call API
        messages = build_prompt(model_short, exp_num, current_files, history)
        response_text, usage, api_elapsed = call_openrouter(
            api_key, model_id, messages
        )

        if response_text is None:
            print("  API call failed, skipping")
            entry = {
                "num": exp_num,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "api_error",
                "cold_launch_ms": 0,
                "composite_score": 0.0,
                "description": "API call failed",
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "api_seconds": round(api_elapsed, 1),
            }
            history.append(entry)
            _save_history(history, history_path)
            continue

        # Parse usage
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost = (input_tokens * cost_in + output_tokens * cost_out) / 1_000_000
        total_cost += cost
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

        # Extract hypothesis
        hypothesis = ""
        first_line = response_text.strip().split("\n")[0]
        if first_line.upper().startswith("HYPOTHESIS"):
            hypothesis = first_line.split(":", 1)[-1].strip() if ":" in first_line else first_line
        else:
            hypothesis = first_line[:100]

        print(f"  Hypothesis: {hypothesis}")
        print(f"  Tokens: {input_tokens} in / {output_tokens} out | Cost: ${cost:.4f} | API: {api_elapsed:.1f}s")

        # Apply patch
        patch_ok, files_changed, lines_changed = apply_patch(response_text, current_files)
        if not patch_ok:
            print("  No valid file changes found in response, skipping")
            entry = {
                "num": exp_num,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "no_patch",
                "cold_launch_ms": 0,
                "composite_score": 0.0,
                "description": hypothesis,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost, 6),
                "api_seconds": round(api_elapsed, 1),
                "files_changed": 0,
                "lines_changed": 0,
            }
            history.append(entry)
            _save_history(history, history_path)
            continue

        print(f"  Patch: {files_changed} files, ~{lines_changed} lines changed")

        # Run measurement
        metrics = run_measurement()

        if metrics is None:
            print("  Measurement failed, reverting")
            restore_mutable_files(backup)
            entry = {
                "num": exp_num,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "crash",
                "cold_launch_ms": 0,
                "composite_score": 0.0,
                "description": hypothesis,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost, 6),
                "api_seconds": round(api_elapsed, 1),
                "files_changed": files_changed,
                "lines_changed": lines_changed,
                "build_seconds": 0,
            }
            history.append(entry)
            _save_history(history, history_path)
            continue

        cold = metrics["cold_launch_ms"]
        score = metrics.get("composite_score", 0.0)
        build_s = metrics.get("build_seconds", 0)

        # Decide keep/discard
        if cold < best_cold_launch:
            status = "keep"
            best_cold_launch = cold
            print(f"  KEEP: {cold}ms (improved from {best_cold_launch}ms)")
            # Commit in target app
            subprocess.run(
                ["git", "add"] + [os.path.join(TARGET_APP_DIR, f) for f in MUTABLE_FILES],
                cwd=TARGET_APP_DIR, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"autoresearch/{model_short} exp#{exp_num}: {hypothesis[:60]}"],
                cwd=TARGET_APP_DIR, capture_output=True, text=True,
            )
        else:
            status = "discard"
            print(f"  DISCARD: {cold}ms (baseline best: {best_cold_launch}ms)")
            restore_mutable_files(backup)

        entry = {
            "num": exp_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "cold_launch_ms": cold,
            "composite_score": score,
            "description": hypothesis,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "api_seconds": round(api_elapsed, 1),
            "files_changed": files_changed,
            "lines_changed": lines_changed,
            "build_seconds": build_s,
        }
        history.append(entry)
        _save_history(history, history_path)

        print(f"  Running total: ${total_cost:.2f} | {total_input_tokens + total_output_tokens:,} tokens")

    # Final summary for this model
    keeps = [h for h in history if h["status"] == "keep"]
    best = min((h["cold_launch_ms"] for h in keeps), default=558)
    print(f"\n{model_short} summary: {len(history)} experiments, best={best}ms, cost=${total_cost:.2f}")

    return history


def _save_history(history, path):
    """Save history to JSON file."""
    with open(path, "w") as f:
        json.dump(history, f, indent=2)

# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def generate_comparison():
    """Print comparison table across all models."""
    print(f"\n{'='*70}")
    print("MULTI-MODEL COMPARISON")
    print(f"{'='*70}")
    print(f"{'Model':<20} {'Best ms':>8} {'Experiments':>12} {'Keeps':>6} {'Cost':>10}")
    print("-" * 70)

    for model in MODELS:
        model_short = model["short"]
        history_path = os.path.join(RESULTS_DIR, model_short, "history.json")
        if not os.path.exists(history_path):
            continue
        with open(history_path, "r") as f:
            history = json.load(f)

        keeps = [h for h in history if h["status"] == "keep"]
        best = min((h["cold_launch_ms"] for h in keeps), default=558)
        total_cost = sum(h.get("cost_usd", 0) for h in history)
        print(f"{model_short:<20} {best:>8} {len(history):>12} {len(keeps):>6} ${total_cost:>9.2f}")

    print("-" * 70)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-model iOS optimization runner")
    parser.add_argument("--experiments", type=int, default=DEFAULT_EXPERIMENTS,
                        help=f"Experiments per model (default: {DEFAULT_EXPERIMENTS})")
    parser.add_argument("--models", type=str, default=None,
                        help="Comma-separated model short names to run (default: all)")
    parser.add_argument("--sequential", action="store_true",
                        help="Run models sequentially (default: sequential anyway)")
    args = parser.parse_args()

    api_key = get_api_key()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Filter models if specified
    if args.models:
        filter_names = [n.strip().lower() for n in args.models.split(",")]
        selected = [m for m in MODELS if any(f in m["short"].lower() for f in filter_names)]
        if not selected:
            print(f"No models matched: {args.models}")
            print(f"Available: {', '.join(m['short'] for m in MODELS)}")
            sys.exit(1)
    else:
        selected = MODELS

    print(f"Models: {', '.join(m['short'] for m in selected)}")
    print(f"Experiments per model: {args.experiments}")
    print(f"Results directory: {RESULTS_DIR}")

    for model in selected:
        try:
            run_model_experiments(model, api_key, args.experiments)
        except KeyboardInterrupt:
            print("\nInterrupted!")
            break
        except Exception as e:
            print(f"\nError with {model['short']}: {e}")
            import traceback
            traceback.print_exc()
            continue

    generate_comparison()
