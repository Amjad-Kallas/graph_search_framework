"""
Run story generation (5 runs each, 2 modalities) + scoring for all subjects
in experiments/<domain>/<subject>/1/.

Usage:
  python src/amjad/metrics/run_generation.py event
  python src/amjad/metrics/run_generation.py person

Output per subject run folder:
  generated_story_1.txt          ... generated_story_5.txt          (event-driven)
  generated_story_baseline_1.txt ... generated_story_baseline_5.txt (no events)
  score_1.json                   ... score_5.json
  score_avg.json
  score_baseline_1.json          ... score_baseline_5.json
  score_baseline_avg.json

Final output:
  experiments/<domain>/summary_avg_scores.json
"""

import os
import sys
import json
import argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from src.amjad.generate_story import (
    generate_story_n_times,
    generate_story_baseline_n_times,
    score_stories_and_average,
)

N_RUNS = 5
EXPERIMENTS_DIR = os.path.join(ROOT, "experiments")


def name_from_folder(folder_name: str) -> str:
    return folder_name.replace("_", " ").title()


def run_all(domain: str):
    base_dir = os.path.join(EXPERIMENTS_DIR, domain)
    subject_dirs = sorted([
        d for d in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, d))
    ])

    per_subject_results = {}

    for subject_dir in subject_dirs:
        run_dir = os.path.join(base_dir, subject_dir, "1")
        timeline_file = os.path.join(run_dir, "event_timeline.txt")
        wiki_file = os.path.join(run_dir, "wikipedia_intro.txt")

        if not os.path.isfile(timeline_file):
            print(f"[SKIP] {subject_dir}: no event_timeline.txt")
            continue
        if not os.path.isfile(wiki_file):
            print(f"[SKIP] {subject_dir}: no wikipedia_intro.txt")
            continue

        main_subject = name_from_folder(subject_dir)
        print(f"\n{'='*60}")
        print(f"Subject: {main_subject}")
        print(f"{'='*60}")

        story_files = [f"{run_dir}/generated_story_{i}.txt" for i in range(1, N_RUNS + 1)]
        baseline_files = [f"{run_dir}/generated_story_baseline_{i}.txt" for i in range(1, N_RUNS + 1)]

        if all(os.path.isfile(f) for f in story_files):
            print(f"[1/4] Event-driven stories already exist, skipping generation.")
        else:
            print(f"[1/4] Generating {N_RUNS} event-driven stories...")
            story_files = generate_story_n_times(timeline_file, main_subject, n=N_RUNS)

        if all(os.path.isfile(f) for f in baseline_files):
            print(f"[2/4] Baseline stories already exist, skipping generation.")
        else:
            print(f"[2/4] Generating {N_RUNS} baseline stories...")
            baseline_files = generate_story_baseline_n_times(run_dir, main_subject, n=N_RUNS)

        print("[3/4] Scoring event-driven stories...")
        avg_scores = score_stories_and_average(
            story_files, wiki_file, run_dir, prefix="score"
        )

        print("[4/4] Scoring baseline stories...")
        avg_baseline = score_stories_and_average(
            baseline_files, wiki_file, run_dir, prefix="score_baseline"
        )

        per_subject_results[subject_dir] = {
            "event_driven": avg_scores,
            "baseline": avg_baseline,
        }

        print(f"  storyscore  event-driven: {avg_scores['storyscore']:.4f}")
        print(f"  storyscore  baseline:     {avg_baseline['storyscore']:.4f}")

    if not per_subject_results:
        print("No subjects processed.")
        return

    keys = list(next(iter(per_subject_results.values()))["event_driven"].keys())
    n_subjects = len(per_subject_results)

    global_avg = {
        "event_driven": {
            key: sum(v["event_driven"][key] for v in per_subject_results.values()) / n_subjects
            for key in keys
        },
        "baseline": {
            key: sum(v["baseline"][key] for v in per_subject_results.values()) / n_subjects
            for key in keys
        },
    }

    summary = {
        "n_runs_per_event": N_RUNS,
        "n_events": n_subjects,
        "per_event": per_subject_results,
        "global_avg": global_avg,
    }

    summary_file = os.path.join(base_dir, "summary_avg_scores.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Done. {n_subjects} subjects processed.")
    print(f"Global avg storyscore — event-driven: {global_avg['event_driven']['storyscore']:.4f}")
    print(f"Global avg storyscore — baseline:     {global_avg['baseline']['storyscore']:.4f}")
    print(f"Summary saved to: {summary_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("domain", choices=["event", "person"], help="Which experiment domain to process")
    args = parser.parse_args()
    run_all(args.domain)
