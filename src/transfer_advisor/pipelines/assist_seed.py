"""ASSIST public frontend API client -- Phase 1b (docs/architecture.md).

Fetches institution IDs, major agreement GUIDs, and full articulation agreements from
the public, unauthenticated ASSIST frontend API (assist.org/api/...). No API key
needed -- but every /api/ call requires echoing the site's ASP.NET antiforgery cookie
back as an X-XSRF-TOKEN header, or the WAF returns 400 Bad Request. This isn't
documented anywhere; found by inspecting assist.org's own network traffic.

Output of get_articulation_agreement() is the RAW agreement as ASSIST returns it,
with its JSON-encoded-string fields decoded (see _parse_agreement) -- it is NOT a
reviewed seed file. Per docs/architecture.md's build-time HITL gate, a human must
verify at least one full agreement row-by-row against assist.org before anything
derived from this is trusted as the seed. Never publish raw output from here
directly as the reviewed seed.
"""

from __future__ import annotations

import json
from typing import Any

import requests

BASE_URL = "https://assist.org"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_JSON_ENCODED_FIELDS = (
    "articulations",
    "receivingInstitution",
    "sendingInstitution",
    "catalogYear",
    "academicYear",
    "templateAssets",
)


class AssistSession:
    """A requests.Session pre-armed with the XSRF handshake ASSIST's API requires."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})
        self._session.get(BASE_URL, timeout=15).raise_for_status()
        token = self._session.cookies.get("X-XSRF-TOKEN")
        if not token:
            raise RuntimeError(
                "assist.org did not set an X-XSRF-TOKEN cookie -- site behavior may have changed"
            )
        self._session.headers.update({"X-XSRF-TOKEN": token})

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self._session.get(f"{BASE_URL}{path}", params=params, timeout=15)
        response.raise_for_status()
        return response.json()


def get_institutions(session: AssistSession) -> list[dict[str, Any]]:
    return session.get_json("/api/institutions")


def get_academic_years(session: AssistSession) -> list[dict[str, Any]]:
    return session.get_json("/api/AcademicYears")


def get_agreements(
    session: AssistSession,
    sending_institution_id: int,
    receiving_institution_id: int,
    academic_year_id: int,
    category_code: str = "major",
) -> list[dict[str, Any]]:
    """Returns report entries shaped {label, key, ownerInstitutionId}.

    `key` is what get_articulation_agreement() expects, shaped
    "{academicYearId}/{sendingId}/to/{receivingId}/Major/{guid}".
    """
    data = session.get_json(
        "/api/agreements",
        params={
            "receivingInstitutionId": receiving_institution_id,
            "sendingInstitutionId": sending_institution_id,
            "academicYearId": academic_year_id,
            "categoryCode": category_code,
        },
    )
    return data.get("reports", [])


def get_articulation_agreement(session: AssistSession, key: str) -> dict[str, Any]:
    """Fetch one full agreement by its `key` (from get_agreements).

    Raises:
        ValueError: if ASSIST reports the fetch as unsuccessful (e.g. a bad key).
    """
    envelope = session.get_json(f"/api/articulation/Agreements?Key={key}")
    if not envelope.get("isSuccessful", False):
        raise ValueError(f"ASSIST reported failure fetching key={key!r}: {envelope.get('validationFailure')}")
    return _parse_agreement(envelope["result"])


def get_ge_certification_courses(
    session: AssistSession,
    institution_id: int,
    academic_year_id: int,
    list_type: str = "CalGETC",
) -> dict[str, Any]:
    """Raw GE-certified course list for one sending institution. Real endpoint
    (/api/transferability/courses), found by inspecting assist.org's own
    network traffic while it rendered a GE results page -- not documented
    anywhere, and not the same endpoint as get_agreements()/
    get_articulation_agreement() (those are major-to-major only; GE
    certification isn't tied to a receiving institution at all).

    `list_type` is ASSIST's own pattern name -- "CalGETC", "IGETC", "CSUGE".
    Cal-GETC replaced both IGETC and CSU GE-Breadth starting Fall 2025 (see
    pipelines/ge_certification.py); this project's academic_year="2025-26"
    convention means CalGETC is the only pattern actually targeted, though
    the older ones still return data (ASSIST keeps them queryable for
    students with pre-Fall-2025 catalog rights).

    Each returned course row's `transferAreas` lists areas from EVERY
    pattern (Cal-GETC, IGETC, CSUGE, CSUAI...) regardless of `list_type` --
    filtering down to the requested pattern happens in
    pipelines/ge_certification.py, not here.
    """
    return session.get_json(
        "/api/transferability/courses",
        params={"institutionId": institution_id, "academicYearId": academic_year_id, "listType": list_type},
    )


def _parse_agreement(result: dict[str, Any]) -> dict[str, Any]:
    """Decode ASSIST's double-JSON-encoded fields into real structures.

    The `result` object (nested under the top-level response envelope) carries
    `receivingInstitution`, `sendingInstitution`, `academicYear`, `catalogYear`,
    `templateAssets`, and `articulations` as JSON-encoded strings, not nested
    objects or arrays -- json.loads() them a second time. See the module docstring;
    this was found by inspecting real responses, not from any published schema.
    """
    parsed = dict(result)
    for field in _JSON_ENCODED_FIELDS:
        value = parsed.get(field)
        if isinstance(value, str):
            try:
                parsed[field] = json.loads(value)
            except json.JSONDecodeError:
                pass  # leave as-is; a human reviewing raw output will notice
    return parsed
