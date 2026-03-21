from openai import OpenAI
from src.amjad.config import VLLM_URL, MODEL_NAME
import os

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
        2. Use ONLY the information provided in the events. Do not add any facts, context, or knowledge not explicitly present.
        3. Ensure the narrative has a proper, definitive conclusion. Do not leave the story hanging.
        4. OUTPUT ONLY THE STORY. Do not include any introductory greetings, titles, or concluding remarks. Start immediately with the first sentence of the narrative and stop immediately after the final punctuation mark.

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

    print("====\nStory generated successfully and saved to generated_story.txt")

    return story, story_file

    # noteamjad: title missing