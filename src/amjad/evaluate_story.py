import json
from src.amjad.compute_story_score import compute_story_score
from src.amjad.llm_score import compute_llm_score


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def evaluate_story(generated_story, reference_story, output_path=None, llm_output_path=None):

    # --- Load inputs ---
    story_text = load_text(generated_story)
    reference_text = load_text(reference_story)

    # --- Automatic metrics ---
    payload = {
        "outline": [],
        "sections": [{"narrative": story_text}],
        "persona": "evaluator",
        "paper_title": "Reference Doc",
        "paper_markdown": reference_text
    }
    result = compute_story_score(payload)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Automatic score saved to: {output_path}")
    else:
        print(json.dumps(result, indent=2))

    # --- LLM-as-judge ---
    '''llm_result = compute_llm_score(story_text, reference_text)

    if llm_output_path:
        with open(llm_output_path, "w", encoding="utf-8") as f:
            json.dump(llm_result, f, indent=2)
        print(f"LLM score saved to: {llm_output_path}")
    else:
        print(json.dumps(llm_result, indent=2))'''

    llm_result = None
    return result, llm_result


if __name__ == "__main__":
    main_dir = "/home/kallas/project/graph_search_framework/experiments/world_war_2"

    reference_file     = f"{main_dir}/wikipedia_intro.txt"
    baseline_story     = f"{main_dir}/generated_story_baseline.txt"
    event_driven_story = f"{main_dir}/generated_story.txt"

    print("=== Evaluating baseline story vs reference ===")
    evaluate_story(
        baseline_story, reference_file,
        output_path=f"{main_dir}/score_baseline.json",
        llm_output_path=f"{main_dir}/score_baseline_llm.json",
    )

    print("\n=== Evaluating event-driven story vs reference ===")
    evaluate_story(
        event_driven_story, reference_file,
        output_path=f"{main_dir}/score_event_driven.json",
        llm_output_path=f"{main_dir}/score_event_driven_llm.json",
    )
