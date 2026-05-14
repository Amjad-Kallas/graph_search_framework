import json
from openai import OpenAI
from src.amjad.config import EURECOM_URL, MY_API_2


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def compute_llm_score(generated_text: str, reference_text: str, max_retries: int = 3) -> dict:
    client = OpenAI(base_url=EURECOM_URL, api_key=MY_API_2)

    prompt = f"""You are an expert evaluator of historical texts.

...
Use a scale of 1 to 10 for each:

- ask chatgpt for: metrics to evaluate of text, commonly used by text or story evaluator, not on the content, but how it is presented.


Generated text:
{generated_text.strip()}

Respond with JSON only, no extra text:
{{"factual_consistency": <int 1-10>, "coverage": <int 1-10>, "reasoning": "<one short sentence per criterion>"}}"""

    last_error = None
    for attempt in range(max_retries):
        response = client.chat.completions.create(
            model="mistral/magistral-medium-latest",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=8192,
        )

        raw = (response.choices[0].message.content or "").strip()

        # Thinking models emit <think>...</think> before the actual output
        if "</think>" in raw:
            raw = raw.split("</think>", 1)[1].strip()

        # Strip markdown code fences if the model wraps its JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            parsed = json.loads(raw)
            fc = int(parsed["factual_consistency"])
            cov = int(parsed["coverage"])
            return {
                "factual_consistency_raw": fc,
                "coverage_raw": cov,
                "factual_consistency": (fc - 1) / 9,
                "coverage": (cov - 1) / 9,
                "reasoning": parsed.get("reasoning", ""),
            }
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            last_error = e
            print(f"  [RETRY {attempt + 1}/{max_retries}] Malformed response: {e}")
            print(f"  [RAW] {repr(raw[:300])}")

    raise ValueError(f"LLM returned malformed output after {max_retries} attempts: {last_error}")


if __name__ == "__main__":
    generated_story = "/home/kallas/project/graph_search_framework/experiments/world_war_2/generated_story_baseline.txt"
    reference_story = "/home/kallas/project/graph_search_framework/experiments/world_war_2/wikipedia_intro_World_War_II.txt"
    generated_text = load_text(generated_story)
    reference_text = load_text(reference_story)

    print(compute_llm_score(generated_text, reference_text))
