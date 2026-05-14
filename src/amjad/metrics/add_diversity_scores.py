"""
Compute inter-story diversity for each subject (event-driven vs baseline)
and patch the existing summary_avg_scores.json with a "diversity" key.

Usage:
  python src/amjad/metrics/add_diversity_scores.py event
  python src/amjad/metrics/add_diversity_scores.py person
"""

import os
import sys
import json
import argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from src.amjad.metrics.diversity_model import DiversityModel

MODEL_NAME = "BAAI/bge-base-en-v1.5"
DEVICE = "cpu"
N_RUNS = 5
EXPERIMENTS_DIR = os.path.join(ROOT, "experiments")


def read_stories(run_dir, prefix, n):
    stories = []
    for i in range(1, n + 1):
        path = os.path.join(run_dir, f"{prefix}{i}.txt")
        with open(path, encoding="utf-8") as f:
            stories.append(f.read())
    return stories


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("domain", choices=["event", "person"], help="Which experiment domain to process")
    args = parser.parse_args()

    base_dir = os.path.join(EXPERIMENTS_DIR, args.domain)
    summary_file = os.path.join(base_dir, "summary_avg_scores.json")

    with open(summary_file, encoding="utf-8") as f:
        summary = json.load(f)

    model = DiversityModel(MODEL_NAME, DEVICE)

    total_event_div = 0.0
    total_baseline_div = 0.0
    n_processed = 0

    for subject_dir, results in summary["per_event"].items():
        entity_path = os.path.join(base_dir, subject_dir)
        run_subdirs = sorted([
            d for d in os.listdir(entity_path)
            if os.path.isdir(os.path.join(entity_path, d)) and d.isdigit()
        ], key=int)

        if not run_subdirs:
            print(f"[SKIP] {subject_dir}: no numeric run dirs")
            continue

        all_event_div = []
        all_baseline_div = []

        for run_id in run_subdirs:
            run_dir = os.path.join(entity_path, run_id)
            try:
                event_stories = read_stories(run_dir, "generated_story_", N_RUNS)
                all_event_div.append(sum(model.get_diversity(event_stories)) / N_RUNS)
            except FileNotFoundError:
                pass
            try:
                baseline_stories = read_stories(run_dir, "generated_story_baseline_", N_RUNS)
                all_baseline_div.append(sum(model.get_diversity(baseline_stories)) / N_RUNS)
            except FileNotFoundError:
                pass

        event_div = sum(all_event_div) / len(all_event_div) if all_event_div else 0.0
        baseline_div = sum(all_baseline_div) / len(all_baseline_div) if all_baseline_div else 0.0

        results["event_driven"]["diversity"] = event_div
        results["baseline"]["diversity"] = baseline_div

        total_event_div += event_div
        total_baseline_div += baseline_div
        n_processed += 1

        print(f"{subject_dir}: event-driven={event_div:.4f}  baseline={baseline_div:.4f}")

    summary["global_avg"]["event_driven"]["diversity"] = total_event_div / n_processed
    summary["global_avg"]["baseline"]["diversity"] = total_baseline_div / n_processed

    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nGlobal avg diversity — event-driven: {summary['global_avg']['event_driven']['diversity']:.4f}")
    print(f"Global avg diversity — baseline:     {summary['global_avg']['baseline']['diversity']:.4f}")
    print(f"Updated: {summary_file}")


if __name__ == "__main__":
    main()
