import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import os

os.environ["CUDA_VISIBLE_DEVICES"] = "2"

MODEL_NAME = "meta-llama/Llama-3.2-3B-Instruct"

# Load once (outside function for efficiency)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    dtype=torch.float16,            # use GPU efficiently
    device_map="auto",               # automatically uses GPU
    #load_in_8bit=True
)

#model.config.use_cache = False

def generate_story(timeline_file, target_words=200):

    with open(timeline_file, "r", encoding="utf-8") as f:
        context = f.read()

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

    # Chat template (important for Llama 3 instruct)
    messages = [
        {"role": "user", "content": prompt}
    ]

    inputs = tokenizer.apply_chat_template(
        messages,
        return_tensors="pt",
        return_dict=True
    )

    input_ids = inputs["input_ids"].to(model.device)
    attention_mask = inputs["attention_mask"].to(model.device)

    # Rough token limit
    max_new_tokens = int(target_words * 2)

    with torch.no_grad():
        output = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            temperature=0.3,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )

    # Decode only generated part
    generated_tokens = output[0][input_ids.shape[-1]:]
    story = tokenizer.decode(generated_tokens, skip_special_tokens=True)

    folder = os.path.dirname(timeline_file)
    story_file = f"{folder}/generated_story.txt"

    with open(story_file, "w") as f:
        f.write(story)

    print(f"====\nStory generated successfully and saved to {story_file}")

    return story, story_file


if __name__ == "__main__":
    timeline_file_path = "/home/kallas/project/graph_search_framework/experiments/2026-03-21-20_52_56-informed_dbpedia_french_revolution_1_pred_object_freq_domain_range_what_where_when_who_wikilink_without_category_uri_iter__max_inf/event_timeline.txt"


    story, _ = generate_story(timeline_file_path)

