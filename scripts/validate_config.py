"""Structural validation for config/*.csv.

This checks contract shape only: required columns present, enum fields valid,
foreign keys resolve. It does NOT require assist_id / assist_major_guid /
Banner term codes to be filled in yet — those are real external identifiers
fetched in later phases (see config/README.md and docs/architecture.md, Phase 0
"AWS foundations and config completion"). That stricter gate belongs there,
not here.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

INSTITUTIONS_COLUMNS = [
    "institution_id",
    "name",
    "system",
    "role",
    "assist_id",
    "catalog_url",
    "banner_base_url",
    "active",
]
INSTITUTIONS_SYSTEMS = {"UC", "CSU", "CCC", "private", "out_of_state"}
INSTITUTIONS_ROLES = {"sending", "receiving", "both"}

MAJORS_COLUMNS = [
    "major_key",
    "display_name",
    "institution_id",
    "assist_major_guid",
    "academic_year",
]

GE_POLICIES_COLUMNS = [
    "institution_id",
    "program_scope",
    "academic_year",
    "policy_summary",
    "source_url",
    "verified_on",
]

BOOL_VALUES = {"true", "false"}


class ValidationError(Exception):
    pass


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def require_columns(path: Path, rows: list[dict[str, str]], expected: list[str]) -> None:
    if not rows:
        # An empty (header-only) file still has DictReader.fieldnames from the header.
        with path.open(newline="", encoding="utf-8") as f:
            fieldnames = csv.DictReader(f).fieldnames or []
    else:
        fieldnames = list(rows[0].keys())
    missing = [c for c in expected if c not in fieldnames]
    if missing:
        raise ValidationError(f"{path.name}: missing columns {missing}")


def require_nonempty(path: Path, row: dict[str, str], columns: list[str], row_num: int) -> None:
    for col in columns:
        if not row.get(col, "").strip():
            raise ValidationError(f"{path.name} row {row_num}: '{col}' must not be empty")


def validate_institutions() -> list[str]:
    path = CONFIG_DIR / "institutions.csv"
    rows = read_rows(path)
    require_columns(path, rows, INSTITUTIONS_COLUMNS)

    seen_ids: set[str] = set()
    for i, row in enumerate(rows, start=2):
        require_nonempty(path, row, ["institution_id", "name", "system", "role", "active"], i)

        institution_id = row["institution_id"].strip()
        if institution_id in seen_ids:
            raise ValidationError(f"{path.name} row {i}: duplicate institution_id '{institution_id}'")
        seen_ids.add(institution_id)

        system = row["system"].strip()
        if system not in INSTITUTIONS_SYSTEMS:
            raise ValidationError(
                f"{path.name} row {i}: system '{system}' not in {sorted(INSTITUTIONS_SYSTEMS)}"
            )

        role = row["role"].strip()
        if role not in INSTITUTIONS_ROLES:
            raise ValidationError(
                f"{path.name} row {i}: role '{role}' not in {sorted(INSTITUTIONS_ROLES)}"
            )

        active = row["active"].strip().lower()
        if active not in BOOL_VALUES:
            raise ValidationError(f"{path.name} row {i}: active '{row['active']}' must be true/false")

    return sorted(seen_ids)


def validate_majors(known_institution_ids: list[str]) -> None:
    path = CONFIG_DIR / "majors.csv"
    rows = read_rows(path)
    require_columns(path, rows, MAJORS_COLUMNS)

    seen_keys: set[str] = set()
    for i, row in enumerate(rows, start=2):
        require_nonempty(path, row, ["major_key", "display_name", "institution_id"], i)

        major_key = row["major_key"].strip()
        if major_key in seen_keys:
            raise ValidationError(f"{path.name} row {i}: duplicate major_key '{major_key}'")
        seen_keys.add(major_key)

        institution_id = row["institution_id"].strip()
        if institution_id not in known_institution_ids:
            raise ValidationError(
                f"{path.name} row {i}: institution_id '{institution_id}' "
                f"not found in institutions.csv"
            )


def validate_ge_policies(known_institution_ids: list[str]) -> None:
    path = CONFIG_DIR / "transfer_ge_policies.csv"
    rows = read_rows(path)
    require_columns(path, rows, GE_POLICIES_COLUMNS)

    seen_ids: set[str] = set()
    for i, row in enumerate(rows, start=2):
        require_nonempty(path, row, GE_POLICIES_COLUMNS, i)
        institution_id = row["institution_id"].strip()
        if institution_id not in known_institution_ids:
            raise ValidationError(
                f"{path.name} row {i}: institution_id '{institution_id}' "
                "not found in institutions.csv"
            )
        if institution_id in seen_ids:
            raise ValidationError(
                f"{path.name} row {i}: duplicate institution_id '{institution_id}'"
            )
        seen_ids.add(institution_id)
        if not row["source_url"].strip().startswith("https://"):
            raise ValidationError(f"{path.name} row {i}: source_url must use https://")


def main() -> int:
    try:
        institution_ids = validate_institutions()
        validate_majors(institution_ids)
        validate_ge_policies(institution_ids)
    except ValidationError as exc:
        print(f"config validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"config validation passed ({len(institution_ids)} institutions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
