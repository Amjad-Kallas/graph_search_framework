"""
Compute readability metrics for all generated stories and write results
alongside existing score files.

Metrics (all reference-free, intrinsic to the text):
  - flesch_reading_ease      : 0-100, higher = more readable
  - flesch_kincaid_grade     : US school grade level (higher = harder)
  - automated_readability_index (ARI): similar grade-level estimate

Expects stories at:
  experiments/{type}/<entity>/1/generated_story_{1..N}.txt
  experiments/{type}/<entity>/1/generated_story_baseline_{1..N}.txt

Writes per-entity:
  readability_{i}.json / readability_baseline_{i}.json  (individual runs)
  readability_avg.json / readability_baseline_avg.json   (local average)

Writes per experiment type:
  experiments/{type}/readability_summary.json            (all levels combined)

Usage:
  python src/amjad/metrics/readability_scores.py --type event
  python src/amjad/metrics/readability_scores.py --type person
  python src/amjad/metrics/readability_scores.py --type all
  python src/amjad/metrics/readability_scores.py --type all --force
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import textstat

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

N_RUNS = 5
METRICS = ["flesch_reading_ease", "flesch_kincaid_grade", "automated_readability_index"]

EXPERIMENT_DIRS = {
    "event": os.path.join(ROOT, "experiments", "event"),
    "person": os.path.join(ROOT, "experiments", "person"),
}


def compute_readability(text: str) -> dict:
    return {
        "flesch_reading_ease": textstat.flesch_reading_ease(text),
        "flesch_kincaid_grade": textstat.flesch_kincaid_grade(text),
        "automated_readability_index": textstat.automated_readability_index(text),
    }


def avg_dicts(dicts: list[dict]) -> dict:
    if not dicts:
        return {}
    return {k: sum(d[k] for d in dicts) / len(dicts) for k in METRICS}


def score_run(story_path: str, score_path: str, force: bool) -> dict:
    if not force and os.path.isfile(score_path):
        with open(score_path) as f:
            return json.load(f)
    with open(story_path, encoding="utf-8") as f:
        text = f.read().strip()
    scores = compute_readability(text)
    with open(score_path, "w") as f:
        json.dump(scores, f, indent=2)
    return scores


def score_entity(run_dir: str, prefix: str, force: bool) -> dict | None:
    metrics_dir = os.path.join(run_dir, "metrics")
    os.makedirs(metrics_dir, exist_ok=True)

    individual = []
    for i in range(1, N_RUNS + 1):
        story_path = os.path.join(run_dir, f"generated_story_{prefix}{i}.txt")
        score_path = os.path.join(metrics_dir, f"readability_{prefix}{i}.json")
        if not os.path.isfile(story_path):
            print(f"    [MISSING] {os.path.basename(story_path)}")
            continue
        individual.append(score_run(story_path, score_path, force))

    if not individual:
        return None

    avg = avg_dicts(individual)
    avg_path = os.path.join(metrics_dir, f"readability_{prefix}avg.json")
    with open(avg_path, "w") as f:
        json.dump(avg, f, indent=2)
    return avg


def process_type(entity_type: str, force: bool) -> dict[str, dict]:
    """Process one experiment type. Returns per_entity dict keyed by entity/run_id."""
    exp_dir = EXPERIMENT_DIRS[entity_type]

    entity_dirs = sorted([
        d for d in os.listdir(exp_dir)
        if os.path.isdir(os.path.join(exp_dir, d)) and not d.startswith("_")
    ])

    per_entity: dict[str, dict] = {}

    for entity in entity_dirs:
        entity_path = os.path.join(exp_dir, entity)
        run_subdirs = sorted([
            d for d in os.listdir(entity_path)
            if os.path.isdir(os.path.join(entity_path, d)) and d.isdigit()
        ], key=int)

        if not run_subdirs:
            print(f"[SKIP] {entity}: no numeric run dirs")
            continue

        for run_id in run_subdirs:
            run_dir = os.path.join(entity_path, run_id)

            print(f"\n{'='*60}")
            print(f"[{entity_type}] Entity: {entity}  run: {run_id}")
            print(f"{'='*60}")

            avg_event = score_entity(run_dir, prefix="", force=force)
            avg_baseline = score_entity(run_dir, prefix="baseline_", force=force)

            if avg_event is None and avg_baseline is None:
                print(f"  [SKIP] no stories found")
                continue

            key = f"{entity}/{run_id}"
            per_entity[key] = {
                "event_driven": avg_event,
                "baseline": avg_baseline,
            }

            for label, avg in [("event-driven", avg_event), ("baseline", avg_baseline)]:
                if avg:
                    fre = avg.get("flesch_reading_ease", float("nan"))
                    fkg = avg.get("flesch_kincaid_grade", float("nan"))
                    ari = avg.get("automated_readability_index", float("nan"))
                    print(f"  {label}: FRE={fre:.2f}  FK-Grade={fkg:.2f}  ARI={ari:.2f}")

    return per_entity


def build_summary(per_entity: dict[str, dict]) -> dict:
    def global_avg(modality: str) -> dict:
        vals = [v[modality] for v in per_entity.values() if v.get(modality)]
        return avg_dicts(vals) if vals else {}

    return {
        "n_runs_per_entity": N_RUNS,
        "per_entity": per_entity,
        "global_avg": {
            "event_driven": global_avg("event_driven"),
            "baseline": global_avg("baseline"),
            "n_entities": len(per_entity),
        },
    }


def print_summary(summary: dict, label: str):
    g = summary["global_avg"]
    print(f"\n{'='*60}")
    print(f"Done [{label}]. {g['n_entities']} entities processed.")
    print(f"\nGlobal avg (event-driven):")
    for k, v in g["event_driven"].items():
        print(f"  {k}: {v:.4f}")
    print(f"\nGlobal avg (baseline):")
    for k, v in g["baseline"].items():
        print(f"  {k}: {v:.4f}")
    print(f"{'='*60}")


def main(entity_types: list[str], force: bool):
    if len(entity_types) == 1:
        entity_type = entity_types[0]
        per_entity = process_type(entity_type, force)
        if not per_entity:
            print("No entities processed.")
            return
        summary = build_summary(per_entity)
        out_path = os.path.join(EXPERIMENT_DIRS[entity_type], "readability_summary.json")
        with open(out_path, "w") as f:
            json.dump(summary, f, indent=2)
        print_summary(summary, entity_type)
        print(f"\nSummary saved to: {out_path}")
    else:
        # all: process each type, write its own summary, then write a combined one
        all_per_entity: dict[str, dict] = {}
        for entity_type in entity_types:
            per_entity = process_type(entity_type, force)
            if not per_entity:
                continue
            summary = build_summary(per_entity)
            out_path = os.path.join(EXPERIMENT_DIRS[entity_type], "readability_summary.json")
            with open(out_path, "w") as f:
                json.dump(summary, f, indent=2)
            print_summary(summary, entity_type)
            print(f"\nSummary saved to: {out_path}")
            # prefix keys with type to avoid collisions in the combined summary
            for k, v in per_entity.items():
                all_per_entity[f"{entity_type}/{k}"] = v

        if not all_per_entity:
            print("No entities processed.")
            return

        combined = build_summary(all_per_entity)
        combined_path = os.path.join(
            os.path.dirname(EXPERIMENT_DIRS["event"]), "readability_summary_all.json"
        )
        with open(combined_path, "w") as f:
            json.dump(combined, f, indent=2)
        print_summary(combined, "all")
        print(f"\nCombined summary saved to: {combined_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=["event", "person", "all"],
                        help="Experiment type to process (or 'all' for both)")
    parser.add_argument("--force", action="store_true",
                        help="Recompute even if score files already exist")
    args = parser.parse_args()
    types = ["event", "person"] if args.type == "all" else [args.type]
    main(types, args.force)
