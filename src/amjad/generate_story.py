from openai import OpenAI
from src.amjad.config import VLLM_URL, MODEL_NAME, EURECOM_URL, MY_API
import os
import json


def _build_client():
    return OpenAI(base_url=EURECOM_URL, api_key=MY_API)


def _call_llm(client, prompt, target_words):
    safe_max_tokens = int(target_words * 4)
    response = client.chat.completions.create(
        model="Qwen/Qwen3-30B-A3B-Thinking-2507",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6,
        max_tokens=safe_max_tokens,
    )
    return response.choices[0].message.content


def generate_story(timeline_file, main_event, target_words=700):
    with open(timeline_file, "r", encoding="utf-8") as f:
        context = f.read()

    prompt = f"""You are a storytelling agent writing a narrative of {main_event} for a general audience.

Writing style:
- The primary goal is to be clear, accurate, and informative without losing engagement focus.
- Write in continuous paragraphs — no headers, bullet points, bold text, or markdown formatting.
- Keep an educational tone but go beyond a simple report of events. A light narrative quality is welcome (smooth transitions, causal explanations), but limit dramatic flourishes, literary scenes, and emotional language.
- Explain why events happened, not just what happened.


Use of provided events:
- The events below are your chronological guide. Follow their general sequence.
- You are free to skip events that do not serve your narrative goals.
- Add essential historical context where needed to keep the account coherent.

Length: Write approximately {target_words} words. The account must be complete — do not end mid-sentence.

Events (chronological guide):
{context}"""

    client = _build_client()
    story = _call_llm(client, prompt, target_words)

    folder = os.path.dirname(timeline_file)
    story_file = f"{folder}/generated_story.txt"

    with open(story_file, "w") as file:
        file.write(story)

    print(f"====\nStory generated successfully and saved to {story_file}")
    return story, story_file


def generate_story_n_times(timeline_file, main_event, n=5, target_words=700):
    """Generate n stories from the same timeline, saving each as generated_story_<i>.txt."""
    with open(timeline_file, "r", encoding="utf-8") as f:
        context = f.read()

    prompt = f"""You are a storytelling agent writing a narrative of {main_event} for a general audience.

Writing style:
- The primary goal is to be clear, accurate, and informative without losing engagement focus.
- Write in continuous paragraphs — no headers, bullet points, bold text, or markdown formatting.
- Keep an educational tone while allowing a light narrative flow and occasional stylistic flourishes to make the text more vivid and immersive.
- Use descriptive language sparingly and naturally, without turning the text into dramatic fiction or overly emotional prose.
- Explain why events happened, not just what happened.


Use of provided events:
- The events below are your chronological guide. Follow their general sequence.
- You are free to skip events that do not serve your narrative goals.
- Add essential historical context where needed to keep the account coherent.

Length: Write approximately {target_words} words. The account must be complete — do not end mid-sentence.

Events (chronological guide):
{context}"""

    client = _build_client()
    folder = os.path.dirname(timeline_file)
    story_files = []

    for i in range(1, n + 1):
        print(f"  Generating story {i}/{n} for {main_event}...")
        story = _call_llm(client, prompt, target_words)
        story_file = f"{folder}/generated_story_{i}.txt"
        with open(story_file, "w", encoding="utf-8") as f:
            f.write(story)
        story_files.append(story_file)
        print(f"  Saved: {story_file}")

    return story_files


def generate_story_baseline_n_times(output_folder, main_event, n=5, target_words=700):
    """Generate n baseline stories (no events provided), saving each as generated_story_baseline_<i>.txt."""
    prompt = f"""You are a storytelling agent writing a narrative of {main_event} for a general audience.

Writing style:
- The primary goal is to be clear, accurate, and informative without losing engagement focus.
- Write in continuous paragraphs — no headers, bullet points, bold text, or markdown formatting.
- Keep an educational tone but go beyond a simple report of events. A light narrative quality is welcome (smooth transitions, causal explanations), but limit dramatic flourishes, literary scenes, and emotional language.
- Explain why events happened, not just what happened.

Length: Write approximately {target_words} words. The account must be complete — do not end mid-sentence."""

    client = _build_client()
    story_files = []

    for i in range(1, n + 1):
        print(f"  Generating baseline story {i}/{n} for {main_event}...")
        story = _call_llm(client, prompt, target_words)
        story_file = f"{output_folder}/generated_story_baseline_{i}.txt"
        with open(story_file, "w", encoding="utf-8") as f:
            f.write(story)
        story_files.append(story_file)
        print(f"  Saved: {story_file}")

    return story_files


def score_stories_and_average(story_files, wiki_file, folder, prefix="score"):
    """Score each story, save individual scores, compute and save averaged scores.

    prefix controls the output filenames: <prefix>_1.json ... <prefix>_avg.json
    """
    from src.amjad.evaluate_story import evaluate_story

    all_scores = []

    for i, story_file in enumerate(story_files, start=1):
        score_file = f"{folder}/{prefix}_{i}.json"
        print(f"  Scoring story {i}/{len(story_files)}...")
        result, _ = evaluate_story(story_file, wiki_file, output_path=score_file)
        all_scores.append(result)

    avg_scores = {
        key: sum(s[key] for s in all_scores) / len(all_scores)
        for key in all_scores[0]
    }

    avg_file = f"{folder}/{prefix}_avg.json"
    with open(avg_file, "w", encoding="utf-8") as f:
        json.dump(avg_scores, f, indent=2)
    print(f"  Averaged scores saved to: {avg_file}")

    return avg_scores


def generate_story_baseline(output_folder, main_event, target_words=700):

    prompt = f"""You are a storytelling agent writing a narrative of {main_event} for a general audience.

Writing style:
- The primary goal is to be clear, accurate, and informative without losing engagement focus.
- Write in continuous paragraphs — no headers, bullet points, bold text, or markdown formatting.
- Keep an educational tone but go beyond a simple report of events. A light narrative quality is welcome (smooth transitions, causal explanations), but limit dramatic flourishes, literary scenes, and emotional language.
- Explain why events happened, not just what happened.


Length: Write approximately {target_words} words. The account must be complete — do not end mid-sentence."""

    client = _build_client()
    story = _call_llm(client, prompt, target_words)

    story_file = f"{output_folder}/generated_story_baseline.txt"

    with open(story_file, "w") as file:
        file.write(story)

    print(f"====\nBaseline story generated successfully and saved to {story_file}")
    return story, story_file


if __name__ == "__main__":
    from src.amjad.evaluate_story import evaluate_story

    BASE = "/home/kallas/project/graph_search_framework/experiments"

    events = [
        ("world_war_2",      "World War II"),
        ("cold_war",         "Cold War"),
        ("crusades",         "Crusades"),
        ("french_revolution","French Revolution"),
        ("vietnam_war",      "Vietnam War"),
    ]

    for folder_name, main_event in events:
        folder        = f"{BASE}/{folder_name}"
        timeline_file = f"{folder}/event_timeline.txt"
        wiki_file     = f"{folder}/wikipedia_intro.txt"

        print(f"\n{'='*60}")
        print(f"Event: {main_event}")
        print(f"{'='*60}")

        print("-- Generating event-driven story...")
        _, story_file = generate_story(timeline_file, main_event)

        print("-- Generating baseline story...")
        _, baseline_file = generate_story_baseline(folder, main_event)

        print("-- Scoring event-driven story...")
        evaluate_story(story_file, wiki_file, output_path=f"{folder}/score_event_driven.json")

        print("-- Scoring baseline story...")
        evaluate_story(baseline_file, wiki_file, output_path=f"{folder}/score_baseline.json")
