"""
Compute mean, variance, and std across the 5 score_{1..N}.json runs
(and score_baseline_{1..N}.json) for each entity in experiments/event and
experiments/person.

Writes:
  experiments/{type}/score_variance.json   — full per-entity + global results

Usage:
  python src/amjad/metrics/score_variance.py --type event
  python src/amjad/metrics/score_variance.py --type person
  python src/amjad/metrics/score_variance.py --type all
"""

import argparse
import json
import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

N_RUNS = 5
METRICS = ["bertscore", "lexical_recall", "title_cov", "noloop", "ctx_recall", "nohall", "storyscore"]

EXPERIMENT_DIRS = {
    "event":  os.path.join(ROOT, "experiments", "event"),
    "person": os.path.join(ROOT, "experiments", "person"),
}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _variance(values: list[float]) -> float:
    """Sample variance (ddof=1)."""
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return sum((v - m) ** 2 for v in values) / (len(values) - 1)


def _std(values: list[float]) -> float:
    return math.sqrt(_variance(values))


def load_scores(run_dir: str, prefix: str) -> list[dict]:
    scores = []
    for i in range(1, N_RUNS + 1):
        path = os.path.join(run_dir, f"score_{prefix}{i}.json")
        if os.path.isfile(path):
            with open(path) as f:
                scores.append(json.load(f))
    return scores


def stats_for_runs(scores: list[dict]) -> dict | None:
    if not scores:
        return None
    result = {"n": len(scores)}
    for key in METRICS:
        vals = [s[key] for s in scores if key in s]
        if not vals:
            continue
        result[key] = {
            "mean": _mean(vals),
            "variance": _variance(vals),
            "std": _std(vals),
            "values": vals,
        }
    return result


def process_type(entity_type: str) -> dict:
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

        for run_id in run_subdirs:
            run_dir = os.path.join(entity_path, run_id)

            ed_scores = load_scores(run_dir, prefix="")
            bl_scores = load_scores(run_dir, prefix="baseline_")

            if not ed_scores and not bl_scores:
                continue

            key = f"{entity}/{run_id}"
            per_entity[key] = {
                "event_driven": stats_for_runs(ed_scores),
                "baseline":     stats_for_runs(bl_scores),
            }

    def global_summary(modality: str) -> dict:
        entries = [v[modality] for v in per_entity.values() if v.get(modality)]
        if not entries:
            return {}
        summary = {}
        for key in METRICS:
            means = [e[key]["mean"] for e in entries if key in e]
            variances = [e[key]["variance"] for e in entries if key in e]
            if not means:
                continue
            summary[key] = {
                "mean_of_means":     _mean(means),
                "mean_of_variances": _mean(variances),
                "std_of_means":      _std(means),
            }
        return summary

    return {
        "n_runs_per_entity": N_RUNS,
        "per_entity": per_entity,
        "global": {
            "event_driven": global_summary("event_driven"),
            "baseline":     global_summary("baseline"),
            "n_entities":   len(per_entity),
        },
    }


def print_summary(entity_type: str, result: dict):
    print(f"\n{'='*64}")
    print(f"Type: {entity_type}  |  {result['global']['n_entities']} entities  |  {N_RUNS} runs each")
    print(f"{'='*64}")
    for modality in ("event_driven", "baseline"):
        g = result["global"][modality]
        if not g:
            continue
        label = "event-driven" if modality == "event_driven" else "baseline"
        print(f"\n  [{label}]")
        print(f"  {'metric':<22} {'mean':>10} {'mean-var':>12} {'std-of-means':>14}")
        print(f"  {'-'*60}")
        for key in METRICS:
            if key not in g:
                continue
            m  = g[key]["mean_of_means"]
            mv = g[key]["mean_of_variances"]
            sm = g[key]["std_of_means"]
            print(f"  {key:<22} {m:>10.4f} {mv:>12.6f} {sm:>14.6f}")


def main(types: list[str]):
    for entity_type in types:
        print(f"\nProcessing: {entity_type} ...")
        result = process_type(entity_type)

        out_path = os.path.join(EXPERIMENT_DIRS[entity_type], "score_variance.json")
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)

        print_summary(entity_type, result)
        print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--type", required=True, choices=["event", "person", "all"],
        help="Experiment type (or 'all' for both)"
    )
    args = parser.parse_args()
    types = ["event", "person"] if args.type == "all" else [args.type]
    main(types)
