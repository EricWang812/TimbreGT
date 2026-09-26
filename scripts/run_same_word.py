"""EXPLORATORY (not pre-registered, decides nothing): the same-word attacker on EasyCall.

In the pre-registered P1, impostor takes are other speakers saying any
command, and a different word is easier to reject. A realistic attacker who
knows the person's sound would say the same word. This rescoring keeps the P1
templates, margins, and genuine trials, and uses as impostors only other
evaluation speakers' probes of the same command. Reuses run_confirm's cached
embeddings. Writes docs/same_word_results.md (gitignored).
"""
import json
from collections import defaultdict

import numpy as np

from issuer.config import EVAL_SEED, GLOBAL_FLOOR, THRESHOLD_MARGIN
from issuer.verification import centroid, spread
from ml.constants import REPO_ROOT
from ml.evaluate import split_speakers
from ml.variants import rates
from scripts.run_confirm import GROUPS, embed_all, load, templates_p1


def rows_same_word(templates, speakers, vectors):
    probes_by_command = defaultdict(list)
    for t in templates:
        if t["speaker"] in speakers:
            probes_by_command[t["command"]] += [(t["speaker"], n) for n in t["probes"]]
    rows = []
    for t in templates:
        if t["speaker"] not in speakers:
            continue
        enrolled = np.stack([vectors[n] for n in t["enrollment"]])
        center = centroid(enrolled)
        impostors = [vectors[n] @ center for s, n in probes_by_command[t["command"]] if s != t["speaker"]]
        if not impostors:
            continue
        rows.append({"speaker": t["speaker"], "group": t["group"], "spread": spread(enrolled),
                     "genuine": np.array([vectors[n] @ center for n in t["probes"]]),
                     "impostor": np.array(impostors)})
    return rows


def main():
    confirmed = json.loads((REPO_ROOT / "docs" / "confirm_results.json").read_text("utf-8"))
    takes, _ = load(REPO_ROOT / "data" / "easycall")
    templates = templates_p1(takes)
    _, evaluation = split_speakers({t["speaker"]: t["group"] for t in templates}, EVAL_SEED)
    needed = {n for t in templates for n in t["enrollment"] + t["probes"]}
    ecapa = embed_all(needed, takes, "ecapa", REPO_ROOT / "data" / "confirm_cache")
    rows = rows_same_word(templates, set(evaluation), ecapa)
    lines = ["# EXPLORATORY: same-word impostors on EasyCall (live ECAPA)", "",
             "Not pre-registered; decides nothing. Impostors are other evaluation speakers saying the same command.", "",
             "| Margin | Group | Templates | Genuine / impostor trials | EER | FAR | FRR |", "|---|---|---:|---:|---:|---:|---:|"]
    for label, margin in (("live 0.12", THRESHOLD_MARGIN), ("P1-calibrated", confirmed["results"]["R"]["margin"])):
        for g in GROUPS:
            r = rates(rows, margin, GLOBAL_FLOOR, g)
            lines.append(f"| {label} ({margin:.3f}) | {g} | {r['speakers']} | {r['genuine_trials']} / {r['impostor_trials']} | "
                         f"{r['eer']:.2%} | {r['far']:.2%} | {r['frr']:.2%} |")
            print(lines[-1], flush=True)
    (REPO_ROOT / "docs" / "same_word_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
