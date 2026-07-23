# Config layer

These tables are first-class, version-controlled, human-reviewed artifacts.
Adding a school or major should mean editing a row here, not touching application
code. The deterministic validator reads configured major keys at runtime.

## No fabricated external IDs

`assist_id`, `assist_major_guid`, and Banner term codes are real identifiers that
only come from calling the real ASSIST/Banner APIs (Phase 1b/1a of
[`../docs/architecture.md`](../docs/architecture.md)). Rows in this repo use the literal
string `TBD` for any such column until that fetch happens. Never invent a
plausible-looking ID as a placeholder — a bad ID is worse than a missing one
because it looks trustworthy.

`institutions.csv`'s `assist_id` and `majors.csv`'s `assist_major_guid`/
`academic_year` were resolved via a live fetch against the ASSIST frontend API on
2026-07-21 (`src/transfer_advisor/pipelines/assist_seed.py`) — real IDs, not
guesses, and spot-checkable directly on assist.org. That is a different bar than
the build-time HITL gate in `docs/architecture.md`, which still requires a human to
verify at least one full agreement **row-by-row** before its course-level content
(not just the ID) is trusted as a seed. `scripts/fetch_assist_seed.py` stages raw
agreements at `data/raw/assist/` (gitignored) for exactly that review.

## `institutions.csv`

| Column | Notes |
|---|---|
| `institution_id` | Stable slug, used as a foreign key from `majors.csv` |
| `name` | Display name |
| `system` | `UC`, `CSU`, `CCC`, `private`, or `out_of_state` — drives the GE pattern lookup in v2 and the "no ASSIST data exists" guard today |
| `role` | `sending`, `receiving`, or `both` |
| `assist_id` | ASSIST institution ID — `TBD` until fetched |
| `catalog_url` | Public course catalog |
| `banner_base_url` | Only meaningful for sending institutions with a Banner instance |
| `active` | `true`/`false` — toggles a school on/off without deleting its data |

## `majors.csv`

| Column | Notes |
|---|---|
| `major_key` | Stable slug, e.g. `me_ucla` |
| `display_name` | e.g. `Mechanical Engineering` |
| `institution_id` | The **receiving** institution this agreement is with — ASSIST major agreements are per receiving institution |
| `assist_major_guid` | Per-agreement GUID — `TBD` until fetched |
| `academic_year` | ASSIST pins articulation to an academic year — `TBD` until fetched |

## `transfer_ge_policies.csv`

Reviewed destination-specific general-education guidance used when building the
KB's combined pathway documents. Cal-GETC certification identifies which AVC
courses qualify for each area; it does not by itself determine whether a
particular engineering program requires, encourages, or accepts partial
Cal-GETC.

| Column | Notes |
|---|---|
| `institution_id` | Receiving institution; foreign key to `institutions.csv` |
| `program_scope` | School or program family covered, currently `engineering` |
| `academic_year` | Policy/catalog year reviewed |
| `policy_summary` | Human-reviewed advising guidance |
| `source_url` | Official destination-institution source |
| `verified_on` | Date the official source was reviewed |
