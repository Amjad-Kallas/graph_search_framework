from openai import OpenAI
from config import VLLM_URL, MODEL_NAME


def generate_story(timeline_file):

    # Load timeline text
    with open(timeline_file, "r", encoding="utf-8") as f:
        context = f.read()

    prompt = f"""
You are given a set of historical events extracted from a knowledge graph.

Write a coherent historical narrative describing the sequence of events.
Explain the main developments and present them chronologically.

Events:
{context}
"""

    client = OpenAI(
        base_url=VLLM_URL,
        api_key="EMPTY"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=512
    )

    return response.choices[0].message.content


story = generate_story("event_timeline.txt")
print(story)