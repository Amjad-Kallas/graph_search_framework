import os
import re
import time
import requests
from sentence_transformers import SentenceTransformer, util


def parse_ttl_events_with_comments(ttl_file):
    """
    Parse a SEM Turtle file and return a list of dicts:
      {name, date, place, comment}
    Only events that have an rdfs:comment are included.
    """
    with open(ttl_file, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.split(" .")
    events = []

    for block in blocks:
        if "a sem:Event" not in block:
            continue

        name_match = re.search(r"ng:([^\s]+)\s+a\s+sem:Event", block)
        if not name_match:
            continue
        name = name_match.group(1).replace("_", " ")

        comment_match = re.search(r'rdfs:comment\s+"((?:[^"\\]|\\.)*)"', block, re.DOTALL)
        if not comment_match:
            continue
        comment = comment_match.group(1).replace("\\n", " ").strip()

        date_match = re.search(r'sem:hasTimeStamp\s+"([^"]+)"', block)
        date = date_match.group(1) if date_match else "unknown"

        place_match = re.search(r"sem:hasPlace\s+ng:([^\s;,]+)", block)
        place = place_match.group(1).replace("_", " ") if place_match else "unknown"

        events.append({"name": name, "date": date, "place": place, "comment": comment})

    return events


def get_wikipedia_intro(main_event_name):
    """
    Fetch the introductory section of a Wikipedia article via the REST API.
    Returns the plain-text intro string (short summary, ~200-300 words).
    """
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + main_event_name.replace(" ", "_")
    resp = requests.get(url, headers={"User-Agent": "ChronoGrapher/1.0"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("extract", "")


def _query_exintro(wiki_host, title, retries=5, backoff=10):
    """Return the full plain-text intro section from a Wikipedia instance, or '' on failure."""
    url = f"https://{wiki_host}/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts",
        "exintro": 1,
        "explaintext": 1,
        "titles": title,
        "format": "json",
    }
    for attempt in range(retries):
        resp = requests.get(url, params=params, headers={"User-Agent": "ChronoGrapher/1.0"}, timeout=10)
        if resp.status_code == 429:
            wait = backoff * (2 ** attempt)
            print(f"Wikipedia 429 — retrying in {wait}s ({attempt + 1}/{retries}) ...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        page = next(iter(pages.values()))
        if page.get("missing") is not None:
            return ""
        return page.get("extract", "")
    raise RuntimeError(f"Wikipedia API still returning 429 after {retries} retries for '{title}'")


def get_wikipedia_intro_full(main_event_name, output_dir=None):
    """
    Fetch the full plain-text introduction section (all paragraphs before the
    first section header) from English Wikipedia.
    """
    intro = _query_exintro("en.wikipedia.org", main_event_name.replace(" ", "_"))

    if output_dir and intro:
        wiki_file = os.path.join(output_dir, "wikipedia_intro.txt")
        with open(wiki_file, "w", encoding="utf-8") as f:
            f.write(intro)
        print(f"Wikipedia intro saved to {wiki_file}")

    return intro


def compute_wiki_similarity_scores(events, wiki_intro, model_name="BAAI/bge-base-en-v1.5"):
    """
    Compute cosine similarity between each event's rdfs:comment and the Wikipedia
    intro of the main event.  Returns a dict {event_name: score} where scores are
    raw cosine similarities in [-1, 1] (typically [0, 1] for these texts).
    """
    model = SentenceTransformer(model_name)

    anchor_emb = model.encode(wiki_intro, convert_to_tensor=True)
    comments = [e["comment"] for e in events]
    comment_embs = model.encode(comments, convert_to_tensor=True)

    scores = util.cos_sim(comment_embs, anchor_emb).squeeze(1).tolist()

    return {e["name"]: float(s) for e, s in zip(events, scores)}
