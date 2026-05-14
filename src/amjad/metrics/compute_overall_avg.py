"""
Compute the overall average diversity (and all other metrics) across both
experiments/event/summary_avg_scores.json and
experiments/person/summary_avg_scores.json.

Weights each subject equally (pools all per-subject scores, not just the
two domain-level averages).

Usage:
  python src/amjad/metrics/compute_overall_avg.py
"""

import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

SUMMARY_FILES = {
    "event":  os.path.join(ROOT, "experiments", "event",   "summary_avg_scores.json"),
    "person": os.path.join(ROOT, "experiments", "person",  "summary_avg_scores.json"),
}


def main():
    all_event_driven: list[dict] = []
    all_baseline: list[dict] = []

    for domain, path in SUMMARY_FILES.items():
        with open(path, encoding="utf-8") as f:
            summary = json.load(f)
        per = summary["per_event"]
        for subject, scores in per.items():
            if scores.get("event_driven"):
                all_event_driven.append(scores["event_driven"])
            if scores.get("baseline"):
                all_baseline.append(scores["baseline"])

    def avg_over(records: list[dict]) -> dict:
        if not records:
            return {}
        keys = records[0].keys()
        return {k: sum(r[k] for r in records) / len(records) for k in keys}

    overall = {
        "n_subjects": len(all_event_driven),
        "event_driven": avg_over(all_event_driven),
        "baseline": avg_over(all_baseline),
    }

    print(f"\nOverall average across {overall['n_subjects']} subjects (event + person)\n")
    print(f"  {'metric':<22} {'event-driven':>14} {'baseline':>12}")
    print(f"  {'-'*50}")
    for k in overall["event_driven"]:
        ed = overall["event_driven"][k]
        bl = overall["baseline"].get(k, float("nan"))
        print(f"  {k:<22} {ed:>14.4f} {bl:>12.4f}")

    out_path = os.path.join(ROOT, "experiments", "overall_avg_scores.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(overall, f, indent=2)
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
