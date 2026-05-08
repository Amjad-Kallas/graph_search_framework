import json
from openai import OpenAI
from src.amjad.config import EURECOM_URL, MY_API


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def compute_llm_score(generated_text: str, reference_text: str) -> dict:
    client = OpenAI(base_url=EURECOM_URL, api_key=MY_API)

    prompt = f"""You are an expert evaluator of historical texts.

Given a reference text and a generated text, score the generated text on two criteria.
Use a scale of 1 to 5 for each:

- factual_consistency (1-10): Are the facts stated in the generated text (dates, causes, key figures, outcomes) consistent with what the reference says? Penalise contradictions, not omissions.
- coverage (1-10): Does the generated text address the key points present in the reference? A high score means the important topics are covered; a low score means major aspects are missing.

Reference text:
{reference_text.strip()}

Generated text:
{generated_text.strip()}

Respond with JSON only, no extra text:
{{"factual_consistency": <int 1-10>, "coverage": <int 1-10>, "reasoning": "<one short sentence per criterion>"}}"""

    response = client.chat.completions.create(
        model="Qwen/Qwen3-30B-A3B-Thinking-2507",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=4096,
    )

    raw = response.choices[0].message.content.strip()

    # Thinking models emit <think>...</think> before the actual output
    if "</think>" in raw:
        raw = raw.split("</think>", 1)[1].strip()

    # Strip markdown code fences if the model wraps its JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    parsed = json.loads(raw)

    return {
        "factual_consistency_raw": int(parsed["factual_consistency"]),
        "coverage_raw": int(parsed["coverage"]),
        "factual_consistency": (int(parsed["factual_consistency"]) - 1) / 9,
        "coverage": (int(parsed["coverage"]) - 1) / 9,
        "reasoning": parsed.get("reasoning", ""),
    }


if __name__ == "__main__":
    generated_story = "/home/kallas/project/graph_search_framework/experiments/world_war_2/generated_story_baseline.txt"
    reference_story = "/home/kallas/project/graph_search_framework/experiments/world_war_2/wikipedia_intro_World_War_II.txt"
    generated_text = load_text(generated_story)
    reference_text = load_text(reference_story)

    print(compute_llm_score(generated_text, reference_text))
