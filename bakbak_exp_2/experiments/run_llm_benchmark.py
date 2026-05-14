"""
Score already-generated stories with the LLM-as-judge metric and compute
local, global, and category-level averages.

Expects stories at:
  experiments/{type}/<entity>/1/generated_story_{1..N}.txt
  experiments/{type}/<entity>/1/generated_story_baseline_{1..N}.txt
  experiments/{type}/<entity>/1/wikipedia_intro.txt

Writes per-entity:
  llm_score_{i}.json / llm_score_baseline_{i}.json  (individual runs)
  llm_score_avg.json / llm_score_baseline_avg.json   (local average)

Writes per experiment type:
  experiments/{type}/llm_summary.json                 (all levels combined)

Usage:
  python experiments/run_llm_benchmark.py --type event
  python experiments/run_llm_benchmark.py --type person
"""

import argparse
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.amjad.llm_score import compute_llm_score, load_text

N_RUNS = 5

CONFIG_DIRS = {
    "event": os.path.join(ROOT, "sample-data", "to_test", "events"),
    "person": os.path.join(ROOT, "sample-data", "to_test", "persons"),
}
EXPERIMENT_DIRS = {
    "event": os.path.join(ROOT, "experiments", "event"),
    "person": os.path.join(ROOT, "experiments", "person"),
}


def build_category_map(config_dir: str) -> dict[str, str]:
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
    keys = [k for k in dicts[0] if k != "reasoning"]
    result = {k: sum(d[k] for d in dicts) / len(dicts) for k in keys}
    result["reasoning"] = [d.get("reasoning", "") for d in dicts]
    return result


def score_run(story_path: str, wiki_path: str, score_path: str) -> dict:
    """Return cached score if available, otherwise compute and save."""
    if os.path.isfile(score_path):
        with open(score_path) as f:
            return json.load(f)
    scores = compute_llm_score(load_text(story_path), load_text(wiki_path))
    with open(score_path, "w") as f:
        json.dump(scores, f, indent=2)
    return scores


def score_entity(run_dir: str, wiki_path: str, prefix: str) -> dict | None:
    """Score N runs for one entity/modality. Returns local average or None if no stories."""
    individual = []
    for i in range(1, N_RUNS + 1):
        story_path = os.path.join(run_dir, f"generated_story_{prefix}{i}.txt")
        score_path = os.path.join(run_dir, f"llm_score_{prefix}{i}.json")
        if not os.path.isfile(story_path):
            print(f"    [MISSING] {os.path.basename(story_path)}")
            continue
        print(f"    Scoring run {i}...")
        individual.append(score_run(story_path, wiki_path, score_path))

    if not individual:
        return None

    avg = avg_dicts(individual)
    avg_path = os.path.join(run_dir, f"llm_score_{prefix}avg.json")
    with open(avg_path, "w") as f:
        json.dump(avg, f, indent=2)
    return avg


def main(entity_type: str):
    exp_dir = EXPERIMENT_DIRS[entity_type]
    config_dir = CONFIG_DIRS[entity_type]
    category_map = build_category_map(config_dir)

    entity_dirs = sorted([
        d for d in os.listdir(exp_dir)
        if os.path.isdir(os.path.join(exp_dir, d)) and not d.startswith("_")
    ])

    per_entity: dict[str, dict] = {}

    for entity in entity_dirs:
        run_dir = os.path.join(exp_dir, entity, "1")
        wiki_path = os.path.join(run_dir, "wikipedia_intro.txt")

        if not os.path.isdir(run_dir):
            print(f"[SKIP] {entity}: no run dir")
            continue
        if not os.path.isfile(wiki_path):
            print(f"[SKIP] {entity}: no wikipedia_intro.txt")
            continue

        print(f"\n{'='*60}")
        print(f"Entity: {entity}")
        print(f"{'='*60}")

        print("  [event-driven]")
        avg_event = score_entity(run_dir, wiki_path, prefix="")

        print("  [baseline]")
        avg_baseline = score_entity(run_dir, wiki_path, prefix="baseline_")

        if avg_event is None and avg_baseline is None:
            print(f"  [SKIP] no stories found")
            continue

        per_entity[entity] = {
            "event_driven": avg_event,
            "baseline": avg_baseline,
        }

        for label, avg in [("event-driven", avg_event), ("baseline", avg_baseline)]:
            if avg:
                fc = avg.get("factual_consistency", float("nan"))
                cov = avg.get("coverage", float("nan"))
                print(f"  {label}: factual_consistency={fc:.4f}  coverage={cov:.4f}")

    if not per_entity:
        print("No entities processed.")
        return

    # --- Global average ---
    numeric_keys = ["factual_consistency_raw", "coverage_raw", "factual_consistency", "coverage"]

    def global_avg(modality: str) -> dict:
        vals = [v[modality] for v in per_entity.values() if v.get(modality)]
        if not vals:
            return {}
        return {k: sum(d[k] for d in vals) / len(vals) for k in numeric_keys if k in vals[0]}

    global_averages = {
        "event_driven": global_avg("event_driven"),
        "baseline": global_avg("baseline"),
        "n_entities": len(per_entity),
    }

    # --- Category average ---
    by_category: dict[str, dict[str, list]] = defaultdict(lambda: {"event_driven": [], "baseline": []})
    for entity, scores in per_entity.items():
        category = category_map.get(entity, "unknown")
        for modality in ("event_driven", "baseline"):
            if scores.get(modality):
                by_category[category][modality].append(scores[modality])

    category_averages = {}
    for category, data in sorted(by_category.items()):
        category_averages[category] = {
            "n": len(data["event_driven"]),
            "event_driven": {
                k: sum(d[k] for d in data["event_driven"]) / len(data["event_driven"])
                for k in numeric_keys if data["event_driven"] and k in data["event_driven"][0]
            },
            "baseline": {
                k: sum(d[k] for d in data["baseline"]) / len(data["baseline"])
                for k in numeric_keys if data["baseline"] and k in data["baseline"][0]
            },
        }

    summary = {
        "n_runs_per_entity": N_RUNS,
        "per_entity": per_entity,
        "global_avg": global_averages,
        "by_category": category_averages,
    }

    out_path = os.path.join(exp_dir, "llm_summary.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Done. {len(per_entity)} entities scored.")
    print(f"\nGlobal avg (event-driven):")
    for k, v in global_averages["event_driven"].items():
        print(f"  {k}: {v:.4f}")
    print(f"\nGlobal avg (baseline):")
    for k, v in global_averages["baseline"].items():
        print(f"  {k}: {v:.4f}")
    print(f"\nBy category:")
    for cat, data in category_averages.items():
        ed = data["event_driven"]
        fc = ed.get("factual_consistency", float("nan"))
        cov = ed.get("coverage", float("nan"))
        print(f"  {cat} (n={data['n']}): factual_consistency={fc:.4f}  coverage={cov:.4f}")
    print(f"\nSummary saved to: {out_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=["event", "person"],
                        help="Experiment type to benchmark")
    args = parser.parse_args()
    main(args.type)
