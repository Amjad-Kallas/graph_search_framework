"""
Compute per-category average scores for person or event experiments.

Categories are determined by which subfolder the config lives in under
sample-data/to_test/{events,persons}/.

  Events:  long_known / short_known / unknown
  Persons: known / unknown

Output:
  experiments/event/summary_avg_scores_by_category.json
  experiments/person/summary_avg_scores_by_category.json

Usage:
  python src/amjad/metrics/compute_category_avg.py --type event
  python src/amjad/metrics/compute_category_avg.py --type person
"""

import argparse
import json
import os
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

CONFIG_DIRS = {
    "event": os.path.join(ROOT, "sample-data", "to_test", "events"),
    "person": os.path.join(ROOT, "sample-data", "to_test", "persons"),
}
EXPERIMENT_DIRS = {
    "event": os.path.join(ROOT, "experiments", "event"),
    "person": os.path.join(ROOT, "experiments", "person"),
}


def build_category_map(config_dir: str) -> dict[str, str]:
    """Return {entity_name: category} by scanning config subdirectories."""
    mapping = {}
    for category in os.listdir(config_dir):
        cat_path = os.path.join(config_dir, category)
        if not os.path.isdir(cat_path):
            continue
        for fname in os.listdir(cat_path):
            if not fname.endswith(".json"):
                continue
            entity = fname.replace("_config_wikidata.json", "")
            mapping[entity] = category
    return mapping


def avg_dicts(dicts: list[dict]) -> dict:
    if not dicts:
        return {}
    keys = dicts[0].keys()
    return {k: sum(d[k] for d in dicts) / len(dicts) for k in keys}


def load_scores(run_dir: str) -> tuple[dict | None, dict | None]:
    avg_path = os.path.join(run_dir, "score_avg.json")
    baseline_path = os.path.join(run_dir, "score_baseline_avg.json")
    event_driven = None
    baseline = None
    if os.path.isfile(avg_path):
        with open(avg_path) as f:
            event_driven = json.load(f)
    if os.path.isfile(baseline_path):
        with open(baseline_path) as f:
            baseline = json.load(f)
    return event_driven, baseline


def main(entity_type: str):
    config_dir = CONFIG_DIRS[entity_type]
    exp_dir = EXPERIMENT_DIRS[entity_type]

    category_map = build_category_map(config_dir)

    by_category: dict[str, dict[str, list]] = defaultdict(lambda: {"event_driven": [], "baseline": []})

    for entity, category in sorted(category_map.items()):
        entity_path = os.path.join(exp_dir, entity)
        if not os.path.isdir(entity_path):
            print(f"[SKIP] {entity}: no experiment dir")
            continue

        run_subdirs = sorted([
            d for d in os.listdir(entity_path)
            if os.path.isdir(os.path.join(entity_path, d)) and d.isdigit()
        ], key=int)

        if not run_subdirs:
            print(f"[SKIP] {entity}: no numeric run dirs")
            continue

        for run_id in run_subdirs:
            run_dir = os.path.join(entity_path, run_id)
            event_driven, baseline = load_scores(run_dir)
            if event_driven is None and baseline is None:
                print(f"[SKIP] {entity}/{run_id}: no score files found")
                continue
            if event_driven:
                by_category[category]["event_driven"].append(event_driven)
            if baseline:
                by_category[category]["baseline"].append(baseline)

    result = {}
    for category, scores in sorted(by_category.items()):
        result[category] = {
            "n": len(scores["event_driven"]),
            "event_driven": avg_dicts(scores["event_driven"]),
            "baseline": avg_dicts(scores["baseline"]),
        }

    out_path = os.path.join(exp_dir, "summary_avg_scores_by_category.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nWrote {out_path}")
    for cat, data in result.items():
        print(f"  {cat}: n={data['n']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=["event", "person"],
                        help="Which experiment type to process")
    args = parser.parse_args()
    main(args.type)
