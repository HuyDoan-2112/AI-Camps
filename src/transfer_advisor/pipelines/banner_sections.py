"""AVC Banner (Ellucian) class-search API client.

Fetches term codes and course-section rows from AVC's public, unauthenticated
Banner 9 Self-Service class search (ssb.avc.edu) -- the same endpoint the public
"Browse Classes" page uses. No API key or login needed. Session flow (none of
this is documented anywhere; found by inspecting the site's own network traffic):

  1. GET  classSearch/classSearch      -- establishes a JSESSIONID cookie
  2. GET  classSearch/getTerms          -- enumerate available term codes
  3. POST term/search?mode=search       -- registers a term against the session
  4. GET  classSearch/resetDataForm     -- resets search state
  5. GET  searchResults/searchResults   -- paginated section rows for a subject

Term codes are "<calendar year><term type>": 70=Fall, 50=Summer, 30=Spring,
10=Intersession/Winter -- e.g. "202630" = Spring 2026.

Important, found the hard way: the subject filter is server-side session state,
not a stateless query parameter. Without calling resetDataForm again before
*every* subject search (not just once per term), a second search_sections()
call for a different subject silently returns the previous subject's rows
instead of erroring -- confirmed live: registering "MATH" then searching "PHYS"
without an intervening reset returned MATH sections labeled as a PHYS search.
search_sections() below calls reset before each search for exactly this reason.

Be polite: this hits a real college's production registration system. Keep
    page_delay_seconds as-is when paginating. Do not fan out aggressive parallel
    requests against the college's production registration service.
"""

from __future__ import annotations

import time
from typing import Any

import requests

BASE_URL = "https://ssb.avc.edu/StudentRegistrationSsb/ssb"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DEFAULT_PAGE_SIZE = 500
DEFAULT_PAGE_DELAY_SECONDS = 0.4


class BannerSession:
    """A requests.Session bootstrapped against AVC's Banner class search."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})
        self._session.get(f"{BASE_URL}/classSearch/classSearch", timeout=15).raise_for_status()

    def register_term(self, term_code: str) -> None:
        """Must be called before search_sections() for a given term."""
        response = self._session.post(
            f"{BASE_URL}/term/search",
            params={"mode": "search"},
            data={
                "term": term_code,
                "studyPath": "",
                "studyPathText": "",
                "startDatepicker": "",
                "endDatepicker": "",
            },
            timeout=15,
        )
        response.raise_for_status()
        self.reset_search_form()

    def reset_search_form(self) -> None:
        """Clears server-side search-filter state. Must be called before every
        subject search, not just once per term -- see the module docstring."""
        self._session.get(f"{BASE_URL}/classSearch/resetDataForm", timeout=15).raise_for_status()

    def get_json(self, path: str, params: dict[str, Any]) -> Any:
        response = self._session.get(f"{BASE_URL}{path}", params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def get_text(self, path: str, params: dict[str, Any]) -> str:
        response = self._session.get(f"{BASE_URL}{path}", params=params, timeout=15)
        response.raise_for_status()
        return response.text


def get_terms(session: BannerSession, max_terms: int = 100) -> list[dict[str, str]]:
    """Enumerate available term codes, most recent first.

    Do this before crawling anything -- see docs/architecture.md Phase 1a. Returns
    entries shaped {"code": "202630", "description": "Spring 2026 (View Only)"}.
    """
    return session.get_json("/classSearch/getTerms", {"offset": 1, "max": max_terms, "searchTerm": ""})


def search_sections(
    session: BannerSession,
    subject: str,
    term_code: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    page_delay_seconds: float = DEFAULT_PAGE_DELAY_SECONDS,
) -> list[dict[str, Any]]:
    """All section rows for one (subject, term), paginating on pageOffset until
    totalCount is reached. Caller must call session.register_term(term_code) first.

    Raises:
        ValueError: if Banner reports the search as unsuccessful.
    """
    session.reset_search_form()

    rows: list[dict[str, Any]] = []
    offset = 0
    total_count: int | None = None

    while total_count is None or offset < total_count:
        data = session.get_json(
            "/searchResults/searchResults",
            {
                "txt_subject": subject,
                "txt_term": term_code,
                "startDatepicker": "",
                "endDatepicker": "",
                "pageOffset": offset,
                "pageMaxSize": page_size,
                "sortColumn": "subjectDescription",
                "sortDirection": "asc",
            },
        )
        if not data.get("success", False):
            raise ValueError(f"Banner reported failure for subject={subject!r} term={term_code!r}: {data}")

        total_count = data["totalCount"]
        batch = data.get("data") or []
        rows.extend(batch)
        offset += len(batch)

        if not batch:
            break  # guard against an infinite loop if totalCount and returned rows disagree

        if offset < total_count:
            time.sleep(page_delay_seconds)

    return rows


def get_course_description(session: BannerSession, term_code: str, course_reference_number: str) -> str:
    """Raw catalog-description HTML for one section (an undocumented endpoint, found
    the same way as the rest of this module): includes Prerequisite/Advisory/
    Corequisite text when present, followed by the course description prose.

    Not verified whether this is identical across every section of the same course
    in the same term, or whether it can drift term to term -- callers doing bulk
    extraction should note which (term, CRN) they fetched from.
    """
    return session.get_text(
        "/searchResults/getCourseDescription",
        {"term": term_code, "courseReferenceNumber": course_reference_number},
    )
