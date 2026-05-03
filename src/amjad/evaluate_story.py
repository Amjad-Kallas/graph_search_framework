import json
from src.amjad.compute_story_score import compute_story_score


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def evaluate_story(generated_story, reference_story, output_path=None):

    # --- Load inputs ---
    story_text = load_text(generated_story)
    reference_text = load_text(reference_story)

    # --- Build payload ---
    payload = {
        "outline": [],
        "sections": [{"narrative": story_text}],
        "persona": "evaluator",
        "paper_title": "Reference Doc",
        "paper_markdown": reference_text
    }

    # --- Compute score ---
    result = compute_story_score(payload)

    # --- Output ---
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Score saved to: {output_path}")
    else:
        print(json.dumps(result, indent=2))

    # noteamjad: title is still not provided ... deal with it later


if __name__ == "__main__":
    main_dir = "/home/kallas/project/graph_search_framework/experiments/world_war_1"

    reference_file             = f"{main_dir}/wikipedia_intro_World_War_I.txt"
    baseline_story             = f"{main_dir}/generated_story_baseline.txt"
    event_driven_story         = f"{main_dir}/generated_story.txt"

    print("=== Evaluating baseline story vs reference ===")
    evaluate_story(baseline_story, reference_file, output_path=f"{main_dir}/score_baseline.json")

    print("\n=== Evaluating event-driven story vs reference ===")
    evaluate_story(event_driven_story, reference_file, output_path=f"{main_dir}/score_event_driven.json")