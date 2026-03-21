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
        "outline": [{"title": "Story"}],
        "sections": [{"title": "Story", "narrative": story_text}],
        "persona": "",
        "paper_title": "",
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