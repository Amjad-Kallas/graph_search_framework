"""
Run story generation (5 runs each, 2 modalities) + scoring for all events
in experiments/event/<event>/1/.

Output per event run folder:
  generated_story_1.txt          ... generated_story_5.txt          (event-driven)
  generated_story_baseline_1.txt ... generated_story_baseline_5.txt (no events)
  score_1.json                   ... score_5.json
  score_avg.json
  score_baseline_1.json          ... score_baseline_5.json
  score_baseline_avg.json

Final output:
  experiments/event/summary_avg_scores.json
"""

import os
import sys
import json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from src.amjad.generate_story import (
    generate_story_n_times,
    generate_story_baseline_n_times,
    score_stories_and_average,
)

N_RUNS = 5
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def event_name_from_folder(folder_name: str) -> str:
    return folder_name.replace("_", " ").title()


def run_all():
    event_dirs = sorted([
        d for d in os.listdir(BASE_DIR)
        if os.path.isdir(os.path.join(BASE_DIR, d))
    ])

    per_event_results = {}

    for event_dir in event_dirs:
        run_dir = os.path.join(BASE_DIR, event_dir, "1")
        timeline_file = os.path.join(run_dir, "event_timeline.txt")
        wiki_file = os.path.join(run_dir, "wikipedia_intro.txt")

        if not os.path.isfile(timeline_file):
            print(f"[SKIP] {event_dir}: no event_timeline.txt")
            continue
        if not os.path.isfile(wiki_file):
            print(f"[SKIP] {event_dir}: no wikipedia_intro.txt")
            continue

        main_event = event_name_from_folder(event_dir)
        print(f"\n{'='*60}")
        print(f"Event: {main_event}")
        print(f"{'='*60}")

        story_files = [f"{run_dir}/generated_story_{i}.txt" for i in range(1, N_RUNS + 1)]
        baseline_files = [f"{run_dir}/generated_story_baseline_{i}.txt" for i in range(1, N_RUNS + 1)]

        if all(os.path.isfile(f) for f in story_files):
            print(f"[1/4] Event-driven stories already exist, skipping generation.")
        else:
            print(f"[1/4] Generating {N_RUNS} event-driven stories...")
            story_files = generate_story_n_times(timeline_file, main_event, n=N_RUNS)

        if all(os.path.isfile(f) for f in baseline_files):
            print(f"[2/4] Baseline stories already exist, skipping generation.")
        else:
            print(f"[2/4] Generating {N_RUNS} baseline stories...")
            baseline_files = generate_story_baseline_n_times(run_dir, main_event, n=N_RUNS)

        print("[3/4] Scoring event-driven stories...")
        avg_scores = score_stories_and_average(
            story_files, wiki_file, run_dir, prefix="score"
        )

        print("[4/4] Scoring baseline stories...")
        avg_baseline = score_stories_and_average(
            baseline_files, wiki_file, run_dir, prefix="score_baseline"
        )

        per_event_results[event_dir] = {
            "event_driven": avg_scores,
            "baseline": avg_baseline,
        }

        print(f"  storyscore  event-driven: {avg_scores['storyscore']:.4f}")
        print(f"  storyscore  baseline:     {avg_baseline['storyscore']:.4f}")

    if not per_event_results:
        print("No events processed.")
        return

    # Global averages for each modality
    keys = list(next(iter(per_event_results.values()))["event_driven"].keys())
    n_events = len(per_event_results)

    global_avg = {
        "event_driven": {
            key: sum(v["event_driven"][key] for v in per_event_results.values()) / n_events
            for key in keys
        },
        "baseline": {
            key: sum(v["baseline"][key] for v in per_event_results.values()) / n_events
            for key in keys
        },
    }

    summary = {
        "n_runs_per_event": N_RUNS,
        "n_events": n_events,
        "per_event": per_event_results,
        "global_avg": global_avg,
    }

    summary_file = os.path.join(BASE_DIR, "summary_avg_scores.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Done. {n_events} events processed.")
    print(f"Global avg storyscore — event-driven: {global_avg['event_driven']['storyscore']:.4f}")
    print(f"Global avg storyscore — baseline:     {global_avg['baseline']['storyscore']:.4f}")
    print(f"Summary saved to: {summary_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_all()
