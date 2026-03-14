import json
from openai import OpenAI
from config import VLLM_URL, MODEL_NAME


def generate_story(events):

    timeline = json.dumps(events, indent=2)

    prompt = f"""
        Convert the following event records into a chronological narrative.

        Rules:
        - Only use the information present in the records.
        - Do not add historical facts.
        - If information is missing, do not guess.

        Events:
        {timeline}
    """

    client = OpenAI(
        base_url=VLLM_URL,
        api_key="EMPTY"
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=512
    )

    return response.choices[0].message.content

