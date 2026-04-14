import csv
import re
from collections import deque
from src.hdt_interface import HDTInterface


# -------------------------
# Helpers
# -------------------------

def extract_year(value):
    if not value:
        return ""
    # Matches any standalone 3 or 4 digit number (e.g., "476", "1789", "1945")
    match = re.search(r'\b\d{3,4}\b', str(value)) 
    return match.group(0) if match else ""


def get_event_year(interface, event_uri):
    """
    Try to extract a year from HDT using date predicates
    """
    date_preds = [
        "http://dbpedia.org/ontology/date",
        "http://dbpedia.org/ontology/startDate",
        "http://dbpedia.org/ontology/endDate"
    ]

    for p in date_preds:
        triples = interface.get_triples(subject=event_uri, predicate=p)
        for _, _, o in triples:
            clean_o = interface.clean_hdt_object(o)
            year = extract_year(clean_o)
            if year:
                return year

    return ""


# -------------------------
# Main extraction
# -------------------------

def extract_war_rows(interface, start_event, max_iter=2, max_rows=500):

    rows = []
    idx = 1

    visited = set()
    queue = deque([(start_event, 1)])

    seen_pairs = set()  # for deduplication

    # predicates
    ingoing_preds = [
        "http://dbpedia.org/property/partof",
        "http://dbpedia.org/ontology/isPartOfMilitaryConflict"
    ]



    outgoing_preds = [
        "http://dbpedia.org/ontology/battle",
        "http://dbpedia.org/property/battles"
    ]

    CAUSE_PREDS = [
        "http://dbpedia.org/ontology/cause",
        "http://dbpedia.org/property/causes",
        "http://dbpedia.org/ontology/result",
        "http://dbpedia.org/property/result",
        "http://dbpedia.org/ontology/event"
    ]

    while queue and idx <= max_rows:

        current_event, iteration = queue.popleft()

        if current_event in visited:
            continue
        visited.add(current_event)

        # -------------------------
        # INGOING (sub-events)
        # -------------------------
        for predicate in ingoing_preds:

            triples = interface.get_triples(
                subject="",
                predicate=predicate,
                object=current_event
            )

            for s, p, o in triples:

                if not s.startswith("http://dbpedia.org/resource/"):
                    continue

                key = (s, o)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)

                # get year
                year = get_event_year(interface, s)

                if not year:
                    year = extract_year(s)

                rows.append([
                    idx, s, p, o,
                    "ingoing", iteration, year
                ])
                idx += 1

                # enqueue for next iteration
                if iteration < max_iter:
                    queue.append((s, iteration + 1))

        if idx > max_rows:
            break

        # -------------------------
        # CAUSES (generic)
        # -------------------------
        for predicate in CAUSE_PREDS:

            triples = interface.get_triples(
                subject=current_event,
                predicate=predicate,
                object=""
            )

            for s, p, o in triples:

                if not o.startswith("http://dbpedia.org/resource/"):
                    continue

                key = (s, o, "cause")
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)

                rows.append([
                    idx, s, p, o,
                    "cause", iteration, ""   # causes usually don’t need year
                ])
                idx += 1

        # -------------------------
        # OUTGOING (optional)
        # -------------------------
        for predicate in outgoing_preds:

            triples = interface.get_triples(
                subject=current_event,
                predicate=predicate,
                object=""
            )

            for s, p, o in triples:

                if not o.startswith("http://dbpedia.org/resource/"):
                    continue

                key = (s, o)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)

                year = get_event_year(interface, o)

                if not year:
                    year = extract_year(o)

                rows.append([
                    idx, s, p, o,
                    "outgoing", iteration, year
                ])
                idx += 1

                if iteration < max_iter:
                    queue.append((o, iteration + 1))

        if idx > max_rows:
            break

    return rows


# -------------------------
# CSV writer
# -------------------------

def write_csv(rows, filename):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "subject", "predicate", "object",
            "type_df", "iteration", "regex_helper"
        ])
        writer.writerows(rows)


# -------------------------
# Run
# -------------------------

if __name__ == '__main__':

    interface = HDTInterface()

    TARGET_EVENT = "http://dbpedia.org/resource/World_War_I"

    print(f"Extracting triples for: {TARGET_EVENT.split('/')[-1].replace('_', ' ')}...\n")

    rows = extract_war_rows(
        interface,
        TARGET_EVENT,
        max_iter=2,     # increase depth here
        max_rows=500    # safety limit
    )

    write_csv(rows, "french_revolution_triples.csv")

    print(f"Saved {len(rows)} triples")