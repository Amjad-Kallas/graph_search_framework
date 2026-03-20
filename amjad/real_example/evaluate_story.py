import json
import argparse
from compute_story_score import compute_story_score


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def main():
    parser = argparse.ArgumentParser(
        description="Compute StoryScore from a generated story and a reference text."
    )

    parser.add_argument(
        "--story_file",
        required=True,
        help="Path to the generated story text file (LLM output)."
    )

    parser.add_argument(
        "--reference_file",
        required=True,
        help="Path to the reference text file (ground truth / paper / KG as text)."
    )

    parser.add_argument(
        "--output_file",
        default=None,
        help="Optional: path to save the score JSON."
    )

    args = parser.parse_args()

    # --- Load inputs ---
    story_text = load_text(args.story_file)
    reference_text = load_text(args.reference_file)

    # --- Build payload ---
    payload = {
        "outline": [{"title": "Story"}],
        "sections": [story_text],
        "persona": "",
        "paper_title": "",
        "paper_markdown": reference_text
    }

    # --- Compute score ---
    result = compute_story_score(payload)

    # --- Output ---
    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Score saved to: {args.output_file}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()