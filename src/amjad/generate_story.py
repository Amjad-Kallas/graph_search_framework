from openai import OpenAI
from src.amjad.config import VLLM_URL, MODEL_NAME, EURECOM_URL
import os

def generate_story(timeline_file, main_event, target_words=1000):

    # Load timeline text
    with open(timeline_file, "r", encoding="utf-8") as f:
        context = f.read()

    # Update the prompt with strict length and conclusion instructions
    prompt = f"""
        You are writing a concise, complete historical narrative about the {main_event}.

        Your primary task is to explicitly incorporate and connect the events provided below, treating them as the backbone of your story.

        Requirements:
        - Pacing and Length: Target approximately {target_words} words. You MUST pace your writing to ensure the story has a definitive beginning, middle, and ending. Do not let the narrative cut off abruptly. 
        - Structure: Organize the history into major chronological phases. 
        - Narrative Flow: Write a cohesive, high-level story that explains how the event started, how it evolved, and how it ultimately ended.

        Rules for Outside Information:
        - Use the "Provided Events" as your main foundation.
        - You may briefly add well-known historical context (e.g., root causes or the final aftermath) ONLY if necessary to bridge gaps between the provided events or to ensure a proper ending. 

        Provided Events:
        {context}
    """

    client = OpenAI(
        base_url=EURECOM_URL,
        api_key="sk-LX6J9reWpzrRfJhyV2moTg"
    )

    # Calculate a safe token limit (roughly 2 tokens per word to be safe)
    safe_max_tokens = int(target_words * 2)

    response = client.chat.completions.create(
        model="Qwen/Qwen3-30B-A3B-Thinking-2507",
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
    timeline_file_path = "/home/kallas/project/graph_search_framework/experiments/2026-04-30-13_56_47-informed_wikidata_french_revolution_2_pred_object_freq_domain_range__where_when__without_category_uri_iter__max_inf/event_timeline.txt"

    main_event = "World War I"
    story, _ = generate_story(timeline_file_path, main_event)