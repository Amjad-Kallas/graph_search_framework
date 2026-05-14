import re
import os
from openai import OpenAI
from tqdm import tqdm
from src.amjad.config import EURECOM_URL, MY_API


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client():
    return OpenAI(base_url=EURECOM_URL, api_key=MY_API)


def parse_ttl_events(ttl_file):
    events = []

    with open(ttl_file, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.split(" .")

    for block in blocks:
        if "a sem:Event" not in block:
            continue

        name_match = re.search(r"ng:([^\s]+)\s+a\s+sem:Event", block)
        if not name_match:
            continue
        name = name_match.group(1).replace("_", " ")

        date_match = re.search(r'sem:hasTimeStamp\s+"([^"]+)"', block)
        date = date_match.group(1) if date_match else "unknown"

        place_match = re.search(r"sem:hasPlace\s+ng:([^\s;]+)", block)
        place = place_match.group(1).replace("_", " ") if place_match else "unknown"

        events.append({"name": name, "date": date, "place": place})

    return events


def format_events_for_llm(events):
    lines = []
    for i, e in enumerate(events, 1):
        line = f"{i}. {e['name']} ({e['date']}, {e['place']})"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Original selection-based reranker (kept for backwards compatibility)
# ---------------------------------------------------------------------------
'''
def rerank_events(events, main_event, events_file, target_k=35):
    prompt = f"""
        You are selecting the most important events to build a coherent historical narrative about {main_event}.

        Your task is to choose the BEST subset of events from the list below.

        STRICT RULES:
        - Select EXACTLY {target_k} events (not more, not less)
        - ONLY select from the provided list (DO NOT invent or rename events)
        - Keep event names EXACTLY as written
        - If an event is unclear, you may discard it

        SELECTION CRITERIA:
        - Importance: Prefer events with major military, political, or strategic impact
        - Diversity:
        - Include different regions (Western Front, Eastern Front, Middle East, naval, etc.)
        - Narrative quality: The selected events should allow building a coherent story

        AVOID:
        - Redundant similar events (e.g., too many minor battles of same type)
        - Overly local or low-impact events
        - Non-events (fronts, lines, generic entities)

        OUTPUT FORMAT:
        Return ONLY a plain list of selected events (one per line, no explanations).

        EVENT LIST:
        {events}
    """

    client = _make_client()
    response = client.chat.completions.create(
        model="Qwen/Qwen3-30B-A3B-Thinking-2507",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=8000
    )

    msg = response.choices[0].message
    raw = msg.content or getattr(msg, "reasoning_content", None)
    if raw is None:
        raise ValueError("Model returned no content. Try increasing max_tokens.")
    selected_events = raw.strip()

    folder = os.path.dirname(events_file)
    output_file = f"{folder}/selected_events.txt"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(selected_events)

    print(f"====\nSelected events saved to {output_file}")
    return selected_events, output_file'''


# ---------------------------------------------------------------------------
# New: LLM numeric scoring
# ---------------------------------------------------------------------------

def _score_batch(batch, main_event, client):
    """Score a single batch of events. Returns dict[name -> raw score 0-10]."""
    numbered = "\n".join(
        f"{i+1}. {e['name']}: {e['comment']}"
        for i, e in enumerate(batch)
    )

    prompt = f"""
    You are selecting and scoring historical EVENTS for building a coherent narrative about "{main_event}".

    SCORING RULES (0–10):
    - 9–10: Crucial turning point or defining moment of {main_event}
    - 7–8: Important event with clear impact
    - 4–6: Secondary or supporting relevance
    - 1–3: Minor or weak relevance
    - 0: Irrelevant, unrecognizable, or you have no knowledge of it

    IMPORTANT: If you do not recognize an event or cannot assess its relevance to "{main_event}", assign it a score of 0.
    Do NOT guess or inflate scores for unfamiliar events.

    OUTPUT FORMAT (STRICT):
    <event name>: <score>

    EVENTS:
    {numbered}
    """

    response = client.chat.completions.create(
        model="Qwen/Qwen3-30B-A3B-Thinking-2507",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2000,
    )

    msg = response.choices[0].message
    raw = msg.content or getattr(msg, "reasoning_content", "") or ""

    scores = {}
    for line in raw.splitlines():
        line = line.strip()
        m = re.match(r"^(.+?):\s*([0-9]+(?:\.[0-9]+)?)\s*$", line)
        if m:
            scores[m.group(1).strip()] = float(m.group(2))
    return scores


def score_events_llm(events_with_comments, main_event, batch_size=20):
    """
    Ask the LLM to assign a relevance score (0-10) to each event given
    its description, relative to *main_event*.  Events are sent in batches
    of *batch_size* to avoid gateway timeouts.

    Parameters
    ----------
    events_with_comments : list[dict]
        Each dict must have "name" and "comment" keys.
    main_event : str
    batch_size : int

    Returns
    -------
    dict[str, float]  event_name -> score normalised to [0, 1]
    """
    client = _make_client()
    batches = [events_with_comments[i:i + batch_size]
               for i in range(0, len(events_with_comments), batch_size)]

    all_scores = {}
    for batch in tqdm(batches, desc="LLM scoring batches", unit="batch"):
        batch_scores = _score_batch(batch, main_event, client)
        all_scores.update(batch_scores)

    # Normalise 0-10 -> 0-1
    return {name: s / 10.0 for name, s in all_scores.items()}


# ---------------------------------------------------------------------------
# Combined reranker
# ---------------------------------------------------------------------------

def rerank_events_combined(
    ttl_file,
    main_event,
    target_k=35,
    wiki_weight=0.4,
    llm_weight=0.6,
    use_llm=True,
):
    """
    Score every event in *ttl_file* using two signals:
      1. Semantic similarity of the event's rdfs:comment to the Wikipedia
         introduction of *main_event*  (via sentence-transformers).
      2. LLM relevance score (0-10, normalised to 0-1).

    Both scores are normalised to [0, 1] then combined linearly.
    The top *target_k* events are returned and written to disk.

    Returns
    -------
    selected : list[dict]   top-k event dicts (name, date, place, comment, combined_score)
    output_file : str       path to the written results file
    """
    from src.amjad.wikipedia_similarity import (
        parse_ttl_events_with_comments,
        get_wikipedia_intro_full,
        compute_wiki_similarity_scores,
    )

    assert abs(wiki_weight + llm_weight - 1.0) < 1e-6, "Weights must sum to 1"

    # 1. Parse events
    events = parse_ttl_events_with_comments(ttl_file)
    print(f"Parsed {len(events)} events with comments from TTL.")

    # 2. Wikipedia similarity
    print(f"Fetching Wikipedia intro for '{main_event}' ...")
    wiki_intro = get_wikipedia_intro_full(main_event, output_dir=os.path.dirname(ttl_file))
    wiki_scores = compute_wiki_similarity_scores(events, wiki_intro)
    print("Wikipedia similarity scores computed.")

    # Min-max normalise wiki scores to [0, 1]
    wiki_vals = list(wiki_scores.values())
    w_min, w_max = min(wiki_vals), max(wiki_vals)
    w_range = w_max - w_min if w_max > w_min else 1.0
    wiki_scores_norm = {k: (v - w_min) / w_range for k, v in wiki_scores.items()}

    # 3. LLM scoring
    if use_llm:
        llm_scores = score_events_llm(events, main_event)
        print(f"LLM returned scores for {len(llm_scores)} / {len(events)} events.")
    else:
        llm_scores = {}
        wiki_weight, llm_weight = 1.0, 0.0
        print("LLM scoring disabled — using Wikipedia similarity only.")

    # 4. Combine
    combined = []
    for e in events:
        name = e["name"]
        ws = wiki_scores_norm.get(name, 0.0)
        ls = llm_scores.get(name, 0.0)
        combined_score = wiki_weight * ws + llm_weight * ls
        combined.append({**e, "wiki_score": ws, "llm_score": ls, "combined_score": combined_score})

    combined.sort(key=lambda x: x["combined_score"], reverse=True)
    selected = combined[:target_k]

    # 5. Print all scores
    col = 50
    header = f"{'#':<4} {'Event':<{col}} {'combined':>8}  {'wiki':>6}  {'llm':>6}"
    sep = "-" * len(header)
    print(f"\n{sep}\n{header}\n{sep}")
    for rank, e in enumerate(combined, 1):
        marker = "***" if rank <= target_k else "   "
        print(
            f"{rank:<4} {e['name']:<{col}.{col}}{marker} "
            f"{e['combined_score']:>8.3f}  {e['wiki_score']:>6.3f}  {e['llm_score']:>6.3f}"
        )
    print(sep)

    # 6. Write outputs
    folder = os.path.dirname(ttl_file)

    def _fmt(e, rank):
        return (
            f"{rank:>3}. {e['name']}"
            f"  |  combined={e['combined_score']:.3f}"
            f"  wiki={e['wiki_score']:.3f}"
            f"  llm={e['llm_score']:.3f}"
        )

    # All events ranked
    all_scores_file = os.path.join(folder, "scores_all.txt")
    with open(all_scores_file, "w", encoding="utf-8") as f:
        f.write(f"All {len(combined)} events ranked by combined score "
                f"(wiki_weight={wiki_weight}, llm_weight={llm_weight})\n")
        f.write(f"Top {target_k} marked with ***\n\n")
        for rank, e in enumerate(combined, 1):
            marker = " ***" if rank <= target_k else ""
            f.write(_fmt(e, rank) + marker + "\n")

    # Top-k only (plain names, one per line)
    selected_file = os.path.join(folder, "selected_events_combined.txt")
    with open(selected_file, "w", encoding="utf-8") as f:
        for e in selected:
            f.write(e["name"] + "\n")

    print(f"\nScores (all events) -> {all_scores_file}")
    print(f"Selected top-{target_k}  -> {selected_file}")
    return selected, selected_file


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ttl_path = (
        "/home/kallas/project/graph_search_framework/experiments/world_war_2/output_ng.ttl"
    )
    main_event = "World War II"

    selected, out = rerank_events_combined(ttl_path, main_event, target_k=35, use_llm=False)
