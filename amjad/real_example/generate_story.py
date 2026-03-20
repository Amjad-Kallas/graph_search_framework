from openai import OpenAI
from config import VLLM_URL, MODEL_NAME

def generate_story(timeline_file, target_words=200):

    # Load timeline text
    with open(timeline_file, "r", encoding="utf-8") as f:
        context = f.read()

    # Update the prompt with strict length and conclusion instructions
    prompt = f"""
You are given a set of historical events extracted from a knowledge graph.

Write a coherent historical narrative describing the sequence of events.
Explain the main developments and present them chronologically.

INSTRUCTIONS:
1. Summarize the events so the entire story is strictly under {target_words} words.
2. Ensure the narrative has a proper, definitive conclusion. Do not leave the story hanging.
3. OUTPUT ONLY THE STORY. Do not include any introductory greetings, titles, or concluding remarks. Start immediately with the first sentence of the narrative and stop immediately after the final punctuation mark.

Events:
{context}
"""

    client = OpenAI(
        base_url=VLLM_URL,
        api_key="EMPTY"
    )

    # Calculate a safe token limit (roughly 2 tokens per word to be safe)
    safe_max_tokens = int(target_words * 2)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=safe_max_tokens 
    )

    return response.choices[0].message.content

# Pass your desired word count here
story = generate_story("event_timeline.txt", target_words=200)

with open("generated_story.txt", "w") as file:
    file.write(story)

print("DONE!")