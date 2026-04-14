from openai import OpenAI
from src.amjad.config import VLLM_URL, MODEL_NAME
import os

def generate_story(timeline_file, target_words=400):

    # Load timeline text
    with open(timeline_file, "r", encoding="utf-8") as f:
        context = f.read()

    # Update the prompt with strict length and conclusion instructions
    prompt = f"""
        You are given a list of events related to a main historical event.

        Using ONLY these events as a base, write a coherent historical narrative.

        Requirements:
        - Write a coherent historical narrative of NO LONGER THAN {target_words} words.
        - Explain how the main event started (you may add missing key causes if needed)
        - Organize the events into major phases
        - Focus on the most important events (do not list everything)
        - Explain how the event evolved and ended (you may add missing ending events)
        - Maintain chronological order

        Rules:
        - You may add a few well-known events if they are missing (e.g. causes or ending)
        - Do NOT invent obscure or unknown events
        - Prefer a clear, high-level story over listing details

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

    story = response.choices[0].message.content

    folder = os.path.dirname(timeline_file)
    story_file = f"{folder}/generated_story.txt"

    with open(story_file, "w") as file:
        file.write(story)

    print(f"====\nStory generated successfully and saved to {story_file}")

    return story, story_file

    # noteamjad: title missing

if __name__ == "__main__":
    timeline_file_path = "/home/kallas/project/graph_search_framework/experiments/2026-03-21-20_52_56-informed_dbpedia_french_revolution_1_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/event_timeline.txt"


    story, _ = generate_story(timeline_file_path)