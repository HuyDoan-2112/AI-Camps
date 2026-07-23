"""Build reviewed prose projections for the Bedrock Knowledge Base.

The structured store remains authoritative for exact calculations. The KB also
needs readable projections of that data so a KB-only agentic retrieval request
can find both parts of a transfer answer:

* major preparation from the selected ASSIST articulation agreement;
* Cal-GETC general-education areas and AVC-certified course options.

This script builds catalog descriptions, one Cal-GETC record per area, and one
combined transfer-pathway record per configured major. It does not publish
offering history as prose because term placement is calculated by the
deterministic validator.

Strips two things that would be wrong to embed as general catalog facts:
  - The Prerequisite/Corequisite/Advisory clause lines (already structured
    separately in prereq_graph_reviewed.json -- duplicating them here as prose
    risks the KB's semantic retrieval contradicting the exact structured data).
  - "Section information text:" and anything after it -- this is specific to
    whichever single CRN we happened to sample, not a fact about the course in
    general (e.g. MATH150's sampled section had a corequisite-lab note that
    doesn't apply to every MATH150 section).

Usage:
    python3 scripts/build_kb_content.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = Path(__file__).resolve().parent.parent
DRAFT_PATH = ROOT / "data" / "processed" / "banner" / "prereq_graph_draft.json"
COURSES_PATH = ROOT / "data" / "processed" / "structured_store" / "courses.json"
GE_PATH = ROOT / "data" / "processed" / "structured_store" / "ge_certification.json"
ARTICULATION_PATH = ROOT / "data" / "processed" / "structured_store" / "articulation.json"
MAJORS_PATH = ROOT / "config" / "majors.csv"
INSTITUTIONS_PATH = ROOT / "config" / "institutions.csv"
GE_POLICIES_PATH = ROOT / "config" / "transfer_ge_policies.csv"
OUT_DIR = ROOT / "data" / "processed" / "kb"
CSV_PATH = OUT_DIR / "avc_catalog.csv"
METADATA_PATH = OUT_DIR / "avc_catalog.csv.metadata.json"
GE_CSV_PATH = OUT_DIR / "avc_cal_getc.csv"
GE_METADATA_PATH = OUT_DIR / "avc_cal_getc.csv.metadata.json"
PATHWAYS_CSV_PATH = OUT_DIR / "avc_transfer_pathways.csv"
PATHWAYS_METADATA_PATH = OUT_DIR / "avc_transfer_pathways.csv.metadata.json"

_SECTION_INFO_MARKER = "section information text"


def _extract_description(raw_description: str, num_clause_lines: int) -> str:
    lines = raw_description.split("\n")
    remaining = lines[num_clause_lines:]
    description_lines = []
    for line in remaining:
        if line.strip().lower().startswith(_SECTION_INFO_MARKER):
            break
        description_lines.append(line)
    return " ".join(line.strip() for line in description_lines if line.strip())


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def _write_metadata(path: Path, content_field: str, metadata_fields: list[str]) -> None:
    metadata = {
        "documentStructureConfiguration": {
            "type": "RECORD_BASED_STRUCTURE_METADATA",
            "recordBasedStructureMetadata": {
                "contentFields": [{"fieldName": content_field}],
                "metadataFieldsSpecification": {
                    "fieldsToInclude": [{"fieldName": name} for name in metadata_fields]
                },
            },
        },
    }
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Wrote sidecar metadata to {path}")


def _build_catalog_rows(
    draft: list[dict[str, object]], courses: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in draft:
        course_key = record["course_key"]
        course = courses.get(course_key)
        if not course:
            print(f"WARNING: {course_key} not in structured_store/courses.json, skipping")
            continue

        description = _extract_description(record["raw_description"], len(record["clauses"]))
        rows.append(
            {
                "course_key": course_key,
                "title": course["title"],
                "description": description,
                "source": "catalog",
                "institution": "avc",
                "academic_year": course["catalog_year"],
            }
        )
    return rows


def _format_ge_course(course: dict[str, object]) -> str:
    min_units = float(course["min_units"])
    max_units = float(course["max_units"])
    units = f"{min_units:g}" if min_units == max_units else f"{min_units:g}-{max_units:g}"
    return f"{course['course_key']} ({course['title']}, {units} units)"


def _group_ge_courses(
    ge_courses: list[dict[str, object]],
) -> dict[tuple[str, str], list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for course in ge_courses:
        for area in course["areas"]:
            key = (area["code"], area["description"])
            grouped.setdefault(key, []).append(course)
    return grouped


def _build_ge_rows(ge_courses: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = _group_ge_courses(ge_courses)
    area_summary = "; ".join(
        f"Area {code} {description}" for code, description in sorted(grouped)
    )
    rows: list[dict[str, object]] = [
        {
            "record_key": "cal_getc_overview",
            "area_code": "ALL",
            "area_description": "Cal-GETC overview",
            "content": (
                "Antelope Valley College general-education planning for Fall 2025 and later "
                "uses Cal-GETC, the unified California General Education Transfer Curriculum. "
                f"The published certification data contains these areas: {area_summary}. "
                "A transfer plan must consider Cal-GETC in addition to ASSIST major preparation. "
                "The area records contain the AVC-certified options. Do not assume that one "
                "course can satisfy multiple areas, or that completing one course in every listed "
                "code is by itself a certification; verify the official completion, double-counting, "
                "campus, and local graduation rules with an AVC counselor."
            ),
            "source": "cal_getc_certification",
            "institution": "avc",
            "academic_year": "2025-26",
        }
    ]

    for (code, description), courses in sorted(grouped.items()):
        options = "; ".join(_format_ge_course(course) for course in courses)
        rows.append(
            {
                "record_key": f"cal_getc_{code.lower()}",
                "area_code": code,
                "area_description": description,
                "content": (
                    f"Cal-GETC Area {code}: {description}. AVC-certified course options for "
                    f"2025-26 are: {options}. These are alternatives certified for this area, "
                    "not a direction to take every listed course. Confirm selection and all "
                    "Cal-GETC completion rules with an AVC counselor."
                ),
                "source": "cal_getc_certification",
                "institution": "avc",
                "academic_year": "2025-26",
            }
        )
    return rows


def _format_articulation(record: dict[str, object]) -> str:
    destination = str(record["receiving_course_key"] or record["receiving_title"])
    if record["status"] != "articulated":
        return (
            f"{destination} = no direct AVC articulation "
            f"({record.get('reason') or 'reason not provided'})."
        )

    choices = [
        " + ".join(str(course_key) for course_key in option)
        for option in record["sending_options"]
    ]
    return f"{destination} = AVC {' OR '.join(choices)}."


def _build_pathway_rows(
    majors: list[dict[str, str]],
    institutions: dict[str, str],
    ge_policies: dict[str, dict[str, str]],
    articulation: list[dict[str, object]],
    ge_courses: list[dict[str, object]],
) -> list[dict[str, object]]:
    articulation_by_major: dict[str, list[dict[str, object]]] = {}
    for record in articulation:
        articulation_by_major.setdefault(str(record["major_key"]), []).append(record)

    grouped_ge = _group_ge_courses(ge_courses)
    ge_summary = "; ".join(
        f"Area {code} {description}: "
        + ", ".join(str(course["course_key"]) for course in courses[:5])
        for (code, description), courses in sorted(grouped_ge.items())
    )

    rows: list[dict[str, object]] = []
    for major in majors:
        major_key = major["major_key"]
        destination_id = major["institution_id"]
        requirements = articulation_by_major.get(major_key, [])
        requirement_text = " ".join(_format_articulation(record) for record in requirements)

        articulated_avc_courses = {
            str(course_key)
            for record in requirements
            for option in record["sending_options"]
            for course_key in option
        }
        overlaps: list[str] = []
        for (code, _description), courses in sorted(grouped_ge.items()):
            matches = sorted(
                str(course["course_key"])
                for course in courses
                if course["course_key"] in articulated_avc_courses
            )
            if matches:
                overlaps.append(f"Area {code}: {', '.join(matches)}")
        overlap_text = "; ".join(overlaps) if overlaps else "No overlap identified in the published data."

        destination_name = institutions[destination_id]
        policy = ge_policies[destination_id]
        common = {
            "major_key": major_key,
            "major_name": major["display_name"],
            "sending_institution": "Antelope Valley College",
            "receiving_institution": destination_name,
            "institution": destination_id,
            "academic_year": major["academic_year"],
        }
        rows.extend(
            [
                {
                    **common,
                    "record_key": f"{major_key}_major_preparation",
                    "record_type": "major_preparation",
                    "content": (
                        f"Complete AVC to {destination_name} {major['display_name']} "
                        f"lower-division major-preparation mapping, "
                        f"{major['academic_year']}. Every reviewed ASSIST requirement is "
                        f"included: {requirement_text} Verify with ASSIST.org and an AVC "
                        "counselor."
                    ),
                    "source": "assist_articulation",
                },
                {
                    **common,
                    "record_key": f"{major_key}_destination_ge_policy",
                    "record_type": "destination_ge_policy",
                    "content": (
                        f"Destination general-education policy for an AVC student transferring "
                        f"to {destination_name} for {major['display_name']}, academic year "
                        f"{major['academic_year']}: {policy['policy_summary']} This GE policy "
                        "must be considered together with the separate complete major-preparation "
                        "record. Do not replace major preparation with Cal-GETC. Policy source: "
                        f"{policy['source_url']} (reviewed {policy['verified_on']})."
                    ),
                    "source": "destination_ge_policy",
                },
                {
                    **common,
                    "record_key": f"{major_key}_ge_options_and_overlaps",
                    "record_type": "ge_options_and_overlaps",
                    "content": (
                        f"General-education options and potential major-preparation overlap for "
                        f"an AVC student transferring to {destination_name} for "
                        f"{major['display_name']}. Representative AVC Cal-GETC options by area "
                        f"are {ge_summary}. Potential major-preparation and Cal-GETC overlaps "
                        f"are {overlap_text}. These are representative certified alternatives, "
                        "not required courses and not a term schedule. Verify Cal-GETC "
                        "certification, double counting, admission requirements, and the final "
                        "education plan with an AVC counselor."
                    ),
                    "source": "assist_and_cal_getc",
                },
            ]
        )
    return rows


def main() -> int:
    draft = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    courses = {c["course_key"]: c for c in json.loads(COURSES_PATH.read_text(encoding="utf-8"))}
    ge_courses = json.loads(GE_PATH.read_text(encoding="utf-8"))
    articulation = json.loads(ARTICULATION_PATH.read_text(encoding="utf-8"))
    majors = _read_csv(MAJORS_PATH)
    institutions = {row["institution_id"]: row["name"] for row in _read_csv(INSTITUTIONS_PATH)}
    ge_policies = {row["institution_id"]: row for row in _read_csv(GE_POLICIES_PATH)}

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _write_csv(
        CSV_PATH,
        ["course_key", "title", "description", "source", "institution", "academic_year"],
        _build_catalog_rows(draft, courses),
    )
    _write_metadata(
        METADATA_PATH,
        "description",
        ["course_key", "title", "source", "institution", "academic_year"],
    )

    _write_csv(
        GE_CSV_PATH,
        [
            "record_key",
            "area_code",
            "area_description",
            "content",
            "source",
            "institution",
            "academic_year",
        ],
        _build_ge_rows(ge_courses),
    )
    _write_metadata(
        GE_METADATA_PATH,
        "content",
        [
            "record_key",
            "area_code",
            "area_description",
            "source",
            "institution",
            "academic_year",
        ],
    )

    _write_csv(
        PATHWAYS_CSV_PATH,
        [
            "record_key",
            "record_type",
            "major_key",
            "major_name",
            "sending_institution",
            "receiving_institution",
            "content",
            "source",
            "institution",
            "academic_year",
        ],
        _build_pathway_rows(majors, institutions, ge_policies, articulation, ge_courses),
    )
    _write_metadata(
        PATHWAYS_METADATA_PATH,
        "content",
        [
            "record_key",
            "record_type",
            "major_key",
            "major_name",
            "sending_institution",
            "receiving_institution",
            "source",
            "institution",
            "academic_year",
        ],
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
