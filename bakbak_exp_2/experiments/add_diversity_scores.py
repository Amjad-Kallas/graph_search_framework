"""
Compute inter-story diversity for each subject (event-driven vs baseline)
and patch the existing summary_avg_scores.json with a "diversity" key.

Usage:
  python experiments/add_diversity_scores.py event
  python experiments/add_diversity_scores.py person
"""

import os
import sys
import json
import argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.amjad.diversity_model import DiversityModel

MODEL_NAME = "BAAI/bge-base-en-v1.5"
DEVICE = "cpu"
N_RUNS = 5
EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))


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
        run_dir = os.path.join(base_dir, subject_dir, "1")

        event_stories = read_stories(run_dir, "generated_story_", N_RUNS)
        baseline_stories = read_stories(run_dir, "generated_story_baseline_", N_RUNS)

        event_div = sum(model.get_diversity(event_stories)) / N_RUNS
        baseline_div = sum(model.get_diversity(baseline_stories)) / N_RUNS

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
