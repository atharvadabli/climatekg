#!/usr/bin/env python3
"""Measure exact State-to-State connectivity in finalized ClimateKG papers."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


def load_papers(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("data/*/final/final_paper.json"))
    ]


def audit(papers: list[dict[str, Any]], max_path_length: int = 4) -> dict[str, Any]:
    claims = [claim for paper in papers for claim in paper["claims"]]
    endpoints: dict[str, tuple[str, str]] = {}
    papers_by_state: dict[str, set[str]] = defaultdict(set)
    occurrences: Counter[str] = Counter()
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    undirected: dict[str, set[str]] = defaultdict(set)

    for paper in papers:
        state_by_value = {
            (state["concept"], state["state"]): state["id"] for state in paper["states"]
        }
        for claim in paper["claims"]:
            source = state_by_value[(claim["from"]["concept"], claim["from"]["state"])]
            target = state_by_value[(claim["to"]["concept"], claim["to"]["state"])]
            endpoints[claim["id"]] = (source, target)
            outgoing[source].append({"claim": claim, "target": target})
            undirected[source].add(target)
            undirected[target].add(source)
            occurrences.update((source, target))
            papers_by_state[source].add(paper["paper"]["id"])
            papers_by_state[target].add(paper["paper"]["id"])

    components: list[list[str]] = []
    unseen = set(undirected)
    while unseen:
        seed = next(iter(unseen))
        queue = deque([seed])
        component = []
        unseen.remove(seed)
        while queue:
            node = queue.popleft()
            component.append(node)
            for neighbor in undirected[node] & unseen:
                unseen.remove(neighbor)
                queue.append(neighbor)
        components.append(component)

    path_counts: dict[str, int] = {"1": len(claims)}
    cross_paper_counts: dict[str, int] = {"1": 0}
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    frontier = [([edge["claim"]], source, edge["target"]) for source, edges in outgoing.items() for edge in edges]
    for length in range(2, max_path_length + 1):
        next_frontier = []
        cross_count = 0
        for path, _source, current in frontier:
            visited_states = {endpoints[item["id"]][0] for item in path}
            visited_states.add(current)
            for edge in outgoing.get(current, []):
                if edge["target"] in visited_states:
                    continue
                extended = path + [edge["claim"]]
                next_frontier.append((extended, endpoints[path[0]["id"]][0], edge["target"]))
                paper_ids = {item["paper_id"] for item in extended}
                if len(paper_ids) > 1:
                    cross_count += 1
                    if len(examples[str(length)]) < 3:
                        examples[str(length)].append(
                            {
                                "claim_ids": [item["id"] for item in extended],
                                "paper_ids": sorted(paper_ids),
                                "states": [endpoints[extended[0]["id"]][0]]
                                + [endpoints[item["id"]][1] for item in extended],
                            }
                        )
        frontier = next_frontier
        path_counts[str(length)] = len(frontier)
        cross_paper_counts[str(length)] = cross_count

    shared = sorted(
        (
            {
                "state_id": state_id,
                "paper_count": len(papers_by_state[state_id]),
                "endpoint_occurrences": occurrences[state_id],
            }
            for state_id in occurrences
            if len(papers_by_state[state_id]) > 1
        ),
        key=lambda item: (-item["paper_count"], -item["endpoint_occurrences"], item["state_id"]),
    )
    return {
        "paper_count": len(papers),
        "claim_count": len(claims),
        "unique_state_count": len(occurrences),
        "weak_component_count": len(components),
        "largest_weak_components": sorted((len(item) for item in components), reverse=True)[:15],
        "states_with_reused_endpoints": sum(count >= 2 for count in occurrences.values()),
        "states_shared_across_papers": len(shared),
        "top_shared_states": shared[:15],
        "directed_simple_path_counts": path_counts,
        "cross_paper_path_counts": cross_paper_counts,
        "cross_paper_path_examples": dict(examples),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(load_papers(args.root))
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
