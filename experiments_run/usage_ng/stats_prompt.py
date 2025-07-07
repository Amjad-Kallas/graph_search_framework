# -*- codinf: utf-8 -*-
"""
Stats on the prompts
"""
import os
import subprocess

COMMAND_NB_TRIPLES = """
sed -n '/```triples/,/```$/p' "{}" | sed '1d;$d' | wc -l
"""
FOLDER = "experiments_run/usage_ng/qa_prompt_answer"
FOLDER_DB = os.path.join(FOLDER, "gpt_triples_dbpedia/prompts")
FOLDER_EC = os.path.join(FOLDER, "gpt_triples_eckg/prompts")

def get_nb_triples(folder: str):
    """
    Get the average number of triples in the prompts
    """
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".txt")]
    nb_triples = []
    for file in files:
        cmd = COMMAND_NB_TRIPLES.format(file)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        nb_triples.append(int(result.stdout.strip()))
    return nb_triples, len(files)

def main():
    """ main """
    nt_db, nb_db = get_nb_triples(FOLDER_DB)
    nt_ec, nb_ec = get_nb_triples(FOLDER_EC)
    print(f"Average number of triples in DBpedia prompts: {sum(nt_db) / nb_db:.2f} over {nb_db} files")
    print(f"Average number of triples in EventKG prompts: {sum(nt_ec) / nb_ec:.2f} over {nb_ec} files")
    print(f"Min/Max number of triples in DBpedia prompts: {min(nt_db)} / {max(nt_db)}")
    print(f"Min/Max number of triples in EventKG prompts: {min(nt_ec)} / {max(nt_ec)}")
    return


if __name__ == "__main__":
    main()
