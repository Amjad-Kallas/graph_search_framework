import csv
import re
from src.hdt_interface import HDTInterface


def extract_year(value):
    match = re.search(r'(18|19|20)\d{2}', value)
    return match.group(0) if match else ""


def extract_biography_rows(interface, person_uri, iteration=1):
    """
    Extract biography triples and return them in raw ChronoGrapher-style rows
    """
    bio_predicates = {
        "http://dbpedia.org/ontology/birthDate",
        "http://dbpedia.org/ontology/birthPlace",
        "http://dbpedia.org/ontology/deathDate",
        "http://dbpedia.org/ontology/deathPlace",
        "http://dbpedia.org/ontology/spouse",
        "http://dbpedia.org/ontology/battle",
        "http://dbpedia.org/ontology/award",
        "http://dbpedia.org/ontology/title",
        "http://dbpedia.org/ontology/knownFor"
    }

    rows = []
    idx = 1

    for predicate in bio_predicates:
        triples = interface.get_triples(subject=person_uri, predicate=predicate)

        for s, p, o in triples:
            clean_o = interface.clean_hdt_object(o)

            # Extract year (from literal or URI)
            regex_helper = extract_year(clean_o)

            row = [
                idx,
                s,
                p,
                clean_o,
                "outgoing",   # biography = outgoing from person
                iteration,
                regex_helper
            ]

            rows.append(row)
            idx += 1

    return rows


def write_csv(rows, filename):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "subject", "predicate", "object",
            "type_df", "iteration", "regex_helper"
        ])
        writer.writerows(rows)


if __name__ == '__main__':
    interface = HDTInterface()

    TARGET_PERSON = "http://dbpedia.org/resource/Albert_Einstein"

    print(f"Extracting triples for: {TARGET_PERSON.split('/')[-1].replace('_', ' ')}...\n")

    rows = extract_biography_rows(interface, TARGET_PERSON)

    write_csv(rows, "einstein_triples.csv")

    print(f"Saved {len(rows)} triples to einstein_triples.csv")