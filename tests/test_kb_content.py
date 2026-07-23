"""Contracts for the reviewed Knowledge Base publication artifacts."""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

from transfer_advisor._project_root import project_root


class KnowledgeBaseContentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kb_dir = project_root() / "data" / "processed" / "kb"

    def _rows(self, name: str) -> list[dict[str, str]]:
        with (self.kb_dir / name).open(newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file))

    def test_cal_getc_has_overview_and_every_published_area(self) -> None:
        rows = self._rows("avc_cal_getc.csv")
        self.assertEqual(len(rows), 12)
        self.assertEqual(
            {row["area_code"] for row in rows},
            {"ALL", "1A", "1B", "1C", "2", "3A", "3B", "4", "5A", "5B", "5C", "6"},
        )
        self.assertTrue(all("AVC" in row["content"] or "Antelope Valley College" in row["content"] for row in rows))

    def test_every_configured_major_has_focused_pathway_records(self) -> None:
        with (project_root() / "config" / "majors.csv").open(
            newline="", encoding="utf-8"
        ) as file:
            expected = {row["major_key"] for row in csv.DictReader(file)}
        pathways = self._rows("avc_transfer_pathways.csv")
        self.assertEqual({row["major_key"] for row in pathways}, expected)
        self.assertEqual(len(pathways), len(expected) * 3)
        for major_key in expected:
            records = {row["record_type"] for row in pathways if row["major_key"] == major_key}
            self.assertEqual(
                records,
                {
                    "major_preparation",
                    "destination_ge_policy",
                    "ge_options_and_overlaps",
                },
            )

    def test_ucla_me_pathway_contains_major_prep_ge_and_policy(self) -> None:
        rows = [
            row
            for row in self._rows("avc_transfer_pathways.csv")
            if row["major_key"] == "me_ucla"
        ]
        by_type = {row["record_type"]: row["content"] for row in rows}
        major_prep = by_type["major_preparation"]
        for course_key in (
            "MATH150",
            "MATH160",
            "MATH250",
            "MATH220",
            "ENGR140",
            "ENGLC1000",
            "ENGR230",
            "ENGR130",
            "ENGR125",
            "CHEM110",
            "CHEM120",
            "PHYS110",
            "PHYS120",
            "PHYS211",
        ):
            self.assertIn(course_key, major_prep)
        self.assertIn("no direct AVC articulation", major_prep)

        ge_options = by_type["ge_options_and_overlaps"]
        self.assertIn("Area 1A", ge_options)
        self.assertIn("Area 6", ge_options)

        policy = by_type["destination_ge_policy"]
        self.assertIn("full Cal-GETC is optional", policy)
        self.assertIn("partial Cal-GETC is not accepted", policy)

    def test_every_generated_csv_has_matching_record_metadata(self) -> None:
        for csv_path in sorted(self.kb_dir.glob("*.csv")):
            metadata_path = Path(f"{csv_path}.metadata.json")
            self.assertTrue(metadata_path.exists(), metadata_path.name)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            structure = metadata["documentStructureConfiguration"]
            self.assertEqual(structure["type"], "RECORD_BASED_STRUCTURE_METADATA")


if __name__ == "__main__":
    unittest.main()
