"""Replace cited-literature gold cases with current-paper findings."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


REPLACEMENTS: dict[str, dict[str, Any]] = {
    "CKGQ0003": {
        "question": (
            "During the Amazonian break period, how does weakening the synoptic wind affect "
            "deforestation-induced mesoscale circulation, afternoon clouds, and local rainfall?"
        ),
        "paper_id": "P000019",
        "source_block_ids": ["P000019:S08:P0062", "P000019:S08:P0064"],
        "reference_answer": (
            "Weakening the synoptic wind strengthened the deforestation-induced mesoscale circulations "
            "and allowed them to reach above the approximately 840-hPa most-unstable level. The stronger "
            "circulations triggered enhanced afternoon low-level cumulus over deforested areas, but the "
            "clouds produced little precipitation and did not overlap the sparse rainfall cells."
        ),
        "required_qualifiers": [
            "Amazonian break period",
            "weakened synoptic wind",
            "enhanced low-level clouds",
            "little local rainfall",
        ],
        "unsupported_conclusions": [
            "Weaker synoptic wind caused enhanced clouds to produce substantial rainfall over the deforested patches."
        ],
    },
    "CKGQ0005": {
        "question": (
            "How does drought change the cooling of summer temperature extremes associated with "
            "irrigation growth compared with rainfed cropland intensification in the United States?"
        ),
        "paper_id": "P000007",
        "source_block_ids": ["P000007:S06:P0034"],
        "reference_answer": (
            "Regions with large irrigation growth retained a cooling trend in the 95th percentile of "
            "summer daily maximum temperature during both drought and non-drought conditions. Rainfed "
            "areas with strong cropland intensification cooled during non-drought conditions but not "
            "during drought, because insufficient soil moisture prevented additional evapotranspirative cooling."
        ),
        "required_qualifiers": [
            "95th-percentile summer daily maximum temperature",
            "irrigation cooling persists during drought",
            "rainfed cooling disappears during drought",
            "soil-moisture limitation",
        ],
        "unsupported_conclusions": [
            "Drought removes the cooling trend equally from irrigated and rainfed intensification areas."
        ],
    },
    "CKGQ0008": {
        "question": (
            "How do season, wind speed, and forest size affect where cloud enhancement occurs over "
            "the Sologne and Landes forests in western Europe?"
        ),
        "paper_id": "P000014",
        "source_block_ids": [
            "P000014:S02:P0021",
            "P000014:S02:P0023",
            "P000014:S02:P0026",
        ],
        "reference_answer": (
            "Over Sologne, a significant preference for clouds over forest occurred during June-August, "
            "while differences outside summer were not significant. Over the larger Landes forest, cloud "
            "frequency was highest at the downwind, and to a lesser extent cross-wind, forest edge; this "
            "edge effect was strongest when regional wind speed exceeded 1 m/s. The smaller Sologne forest "
            "showed no clear wind-related cloud pattern, making its edge effect difficult to detect."
        ),
        "required_qualifiers": [
            "June-August seasonal preference over Sologne",
            "Landes downwind edge",
            "wind speed greater than 1 m/s",
            "no clear wind relation for smaller Sologne forest",
        ],
        "unsupported_conclusions": [
            "Both forests show the same wind-dependent downwind cloud enhancement in every season."
        ],
    },
    "CKGQ0009": {
        "question": (
            "How does simulated irrigation affect annual maximum daytime temperature, annual minimum "
            "nighttime temperature, and heat-wave duration over irrigated land?"
        ),
        "paper_id": "P000004",
        "source_block_ids": ["P000004:S18:P0096"],
        "reference_answer": (
            "Irrigation reduced annual maximum daytime temperature by an average of 0.78 K over irrigated "
            "land and also shortened heat-wave duration. Its temperature response was asymmetric: annual "
            "minimum nighttime temperature generally increased, locally by more than 2 K, even as daytime "
            "extremes decreased."
        ),
        "required_qualifiers": [
            "0.78 K average daytime-maximum cooling over irrigated land",
            "nighttime-minimum warming",
            "shorter heat-wave duration",
        ],
        "unsupported_conclusions": [
            "Irrigation cools both daytime maxima and nighttime minima by the same amount."
        ],
    },
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--graph-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    cases = deepcopy(read_json(args.source)[:10])
    papers = {row["id"]: row for row in pq.read_table(args.graph_root / "papers.parquet").to_pylist()}
    blocks = {
        row["id"]: row
        for row in pq.read_table(
            args.graph_root / "source_blocks.parquet",
            columns=["id", "paper_id", "page", "section_path", "text"],
        ).to_pylist()
    }
    claims = pq.read_table(
        args.graph_root / "claims.parquet",
        columns=["id", "paper_id", "evidence_role", "evidence_block_ids"],
    ).to_pylist()
    own_result_blocks = {
        block_id
        for claim in claims
        if claim["evidence_role"] == "OWN_RESULT"
        for block_id in claim["evidence_block_ids"]
    }

    replaced = []
    for case in cases:
        replacement = REPLACEMENTS.get(case["id"])
        if replacement is None:
            case["verification"] = {
                "status": "model_checked",
                "verifier": "Codex source-provenance audit",
                "date": date.today().isoformat(),
                "notes": (
                    "Gold passage checked against the saved paper text as a finding reported by the "
                    "current paper. Human verification against the original PDF remains required."
                ),
            }
            continue
        paper_id = replacement["paper_id"]
        block_ids = replacement["source_block_ids"]
        missing = [block_id for block_id in block_ids if block_id not in blocks]
        if missing:
            raise ValueError(f"{case['id']} has missing SourceBlocks: {missing}")
        wrong_owner = [block_id for block_id in block_ids if blocks[block_id]["paper_id"] != paper_id]
        if wrong_owner:
            raise ValueError(f"{case['id']} has SourceBlocks owned by another paper: {wrong_owner}")
        unconfirmed = [block_id for block_id in block_ids if block_id not in own_result_blocks]
        if unconfirmed:
            raise ValueError(f"{case['id']} replacement lacks OWN_RESULT Claim provenance: {unconfirmed}")

        paper = papers[paper_id]
        case.update(
            {
                "question": replacement["question"],
                "source_papers": [
                    {"paper_id": paper_id, "title": paper["title"], "doi": paper.get("doi")}
                ],
                "gold_evidence": [
                    {
                        "paper_id": paper_id,
                        "source_block_id": block_id,
                        "page": blocks[block_id]["page"],
                        "role": "central",
                    }
                    for block_id in block_ids
                ],
                "reference_answer": replacement["reference_answer"],
                "required_qualifiers": replacement["required_qualifiers"],
                "unsupported_conclusions": replacement["unsupported_conclusions"],
                "verification": {
                    "status": "model_checked",
                    "verifier": "Codex source-provenance audit",
                    "date": date.today().isoformat(),
                    "notes": (
                        "Replacement gold passages are current-paper results and are linked to "
                        "OWN_RESULT Claims. Human verification against the PDF remains required."
                    ),
                },
            }
        )
        replaced.append(case["id"])

    write_json(args.output_dir / "cases.json", cases)
    write_json(
        args.output_dir / "manifest.json",
        {
            "dataset_version": 2,
            "case_schema_version": 1,
            "status": "model_checked_requires_human_verification",
            "case_count": len(cases),
            "source_dataset": str(args.source),
            "replaced_case_ids": replaced,
            "superseded_reason": "Gold evidence summarized cited literature rather than a current-paper finding.",
            "gold_evidence_policy": (
                "Every answerable case must be supported by a finding produced, observed, simulated, "
                "or analyzed by the indexed paper itself. Cited-literature summaries are excluded."
            ),
        },
    )


if __name__ == "__main__":
    main()
