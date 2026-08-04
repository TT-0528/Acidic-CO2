#!/usr/bin/env python3
"""Monitor OpenAlex for newly indexed acidic CO2 electroreduction literature.

The script is designed for GitHub Actions. It searches recent works, applies a
second local relevance filter, deduplicates results, and creates one GitHub Issue
for an unseen paper on each scheduled run.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

OPENALEX_URL = "https://api.openalex.org/works"
GITHUB_ISSUES_URL = "https://api.github.com/repos/{repository}/issues"
STATE_PATH = Path(os.getenv("STATE_PATH", "state/seen.json"))

# Two complementary searches: one for explicitly acidic media and one for
# proton-conducting membrane terminology. OpenAlex supports Boolean search.
SEARCH_QUERIES = (
    '(("carbon dioxide" OR CO2 OR CO₂) AND '
    '(electroreduction OR "electrochemical reduction" OR electrolysis OR CO2RR)) '
    'AND (acidic OR "acid media" OR "acid electrolyte" OR hydronium OR "low pH")',
    '(("carbon dioxide" OR CO2 OR CO₂) AND '
    '(electroreduction OR "electrochemical reduction" OR electrolysis OR CO2RR)) '
    'AND ("proton exchange membrane" OR "cation exchange membrane" OR '
    '"solid polymer electrolyte" OR Nafion)',
)

CO2_TERMS = (
    "carbon dioxide",
    "co2",
    "co2rr",
)

ELECTROREDUCTION_TERMS = (
    "electroreduction",
    "electro-reduction",
    "electrochemical reduction",
    "electrocatalytic reduction",
    "co2 reduction",
    "carbon dioxide reduction",
    "co2 electrolysis",
    "carbon dioxide electrolysis",
    "co2rr",
    "co2 electrolyzer",
    "co2 electrolyser",
)

ACID_TERMS = (
    "acidic",
    "acid media",
    "acidic media",
    "acid electrolyte",
    "acidic electrolyte",
    "acidic condition",
    "acidic environment",
    "acidic solution",
    "low ph",
    "low-ph",
    "hydronium",
    "proton-rich",
    "proton rich",
    "proton activity",
    "proton concentration",
    "proton exchange membrane",
    "proton-exchange membrane",
    "cation exchange membrane",
    "cation-exchange membrane",
    "solid polymer electrolyte",
    "proton conducting membrane",
    "proton-conducting membrane",
    "nafion-h",
    "nafion h",
    "sulfonic acid membrane",
)

CONTEXT_TERMS = (
    "membrane electrode assembly",
    "zero-gap",
    "zero gap",
    "solid-polymer-electrolyte",
    "solid polymer electrolyte",
    "local ph",
    "interfacial ph",
)

ALLOWED_TYPES = {
    "article",
    "review",
    "preprint",
    "proceedings-article",
    "book-chapter",
}


@dataclass(frozen=True)
class Paper:
    key: str
    title: str
    authors: str
    publication_date: str
    venue: str
    doi: str
    url: str
    abstract: str
    matched_terms: tuple[str, ...]
    work_type: str


def normalize_text(value: str | None) -> str:
    """Normalize scientific Unicode variants for robust term matching."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = text.replace("₂", "2").replace("₃", "3").replace("₄", "4")
    text = text.lower()
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """Convert OpenAlex's inverted abstract index into ordinary text."""
    if not inverted_index:
        return ""
    positioned_words: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for position in positions:
            positioned_words.append((position, word))
    positioned_words.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positioned_words)


def phrase_present(text: str, term: str) -> bool:
    if term == "co2":
        return bool(re.search(r"\bco\s*2\b", text))
    return term in text


def collect_hits(text: str, terms: Iterable[str]) -> list[str]:
    return [term for term in terms if phrase_present(text, term)]


def relevance(work: dict[str, Any]) -> tuple[bool, tuple[str, ...]]:
    """Require evidence for all three concepts: CO2, electroreduction, acidity."""
    work_type = work.get("type") or ""
    if work_type and work_type not in ALLOWED_TYPES:
        return False, ()

    title = work.get("display_name") or work.get("title") or ""
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    keyword_text = " ".join(
        item.get("display_name", "") for item in (work.get("keywords") or [])
    )
    topic_text = " ".join(
        item.get("display_name", "") for item in (work.get("topics") or [])
    )
    text = normalize_text(" ".join((title, abstract, keyword_text, topic_text)))

    co2_hits = collect_hits(text, CO2_TERMS)
    electro_hits = collect_hits(text, ELECTROREDUCTION_TERMS)
    acid_hits = collect_hits(text, ACID_TERMS)
    context_hits = collect_hits(text, CONTEXT_TERMS)

    accepted = bool(co2_hits and electro_hits and acid_hits)
    matched = tuple(dict.fromkeys((co2_hits + electro_hits + acid_hits + context_hits)))
    return accepted, matched[:8]


def paper_key(work: dict[str, Any]) -> str:
    doi = (work.get("doi") or "").strip().lower()
    if doi:
        return doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    return (work.get("id") or "").strip().lower()


def extract_authors(work: dict[str, Any], limit: int = 6) -> str:
    names: list[str] = []
    for authorship in work.get("authorships") or []:
        name = ((authorship.get("author") or {}).get("display_name") or "").strip()
        if name:
            names.append(name)
    if not names:
        return "Unknown authors"
    if len(names) > limit:
        return ", ".join(names[:limit]) + ", et al."
    return ", ".join(names)


def extract_venue(work: dict[str, Any]) -> str:
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    return (source.get("display_name") or "Unknown venue").strip()


def extract_url(work: dict[str, Any]) -> str:
    doi = (work.get("doi") or "").strip()
    if doi:
        return doi
    for location_key in ("best_oa_location", "primary_location"):
        location = work.get(location_key) or {}
        for field in ("landing_page_url", "pdf_url"):
            value = location.get(field)
            if value:
                return value
    return work.get("id") or ""


def to_paper(work: dict[str, Any], matched_terms: tuple[str, ...]) -> Paper:
    title = (work.get("display_name") or work.get("title") or "Untitled").strip()
    doi = (work.get("doi") or "").strip()
    return Paper(
        key=paper_key(work),
        title=title,
        authors=extract_authors(work),
        publication_date=work.get("publication_date") or "Unknown date",
        venue=extract_venue(work),
        doi=doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/"),
        url=extract_url(work),
        abstract=reconstruct_abstract(work.get("abstract_inverted_index")),
        matched_terms=matched_terms,
        work_type=work.get("type") or "unknown",
    )


def fetch_recent_works(
    api_key: str,
    lookback_days: int,
    per_query: int,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Fetch and merge recent results from all configured search queries."""
    client = session or requests.Session()
    from_date = (date.today() - timedelta(days=lookback_days)).isoformat()
    selected_fields = ",".join(
        (
            "id",
            "doi",
            "display_name",
            "publication_date",
            "type",
            "authorships",
            "primary_location",
            "best_oa_location",
            "abstract_inverted_index",
            "keywords",
            "topics",
        )
    )

    merged: dict[str, dict[str, Any]] = {}
    for query in SEARCH_QUERIES:
        params = {
            "api_key": api_key,
            "search": query,
            "filter": f"from_publication_date:{from_date}",
            "sort": "publication_date:desc",
            "per_page": min(max(per_query, 1), 100),
            "select": selected_fields,
        }
        response = client.get(OPENALEX_URL, params=params, timeout=45)
        response.raise_for_status()
        payload = response.json()
        for work in payload.get("results", []):
            key = paper_key(work)
            if key:
                merged[key] = work
        time.sleep(0.25)

    return sorted(
        merged.values(),
        key=lambda work: work.get("publication_date") or "",
        reverse=True,
    )


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"seen": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Cannot read state file {path}: {exc}") from exc
    if not isinstance(state.get("seen"), dict):
        state["seen"] = {}
    return state


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def trim_state(state: dict[str, Any], max_entries: int = 5000) -> None:
    seen = state.get("seen", {})
    if len(seen) <= max_entries:
        return
    newest = sorted(
        seen.items(),
        key=lambda item: item[1].get("first_seen", ""),
        reverse=True,
    )[:max_entries]
    state["seen"] = dict(newest)


def shorten(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def format_github_issue(paper: Paper) -> tuple[str, str]:
    """Build a concise GitHub Issue title and Markdown body."""
    title = shorten(f"[Acidic CO₂RR] {paper.title}", 240)
    matched = ", ".join(paper.matched_terms) or "—"
    abstract = shorten(paper.abstract, 1200) or "Abstract unavailable in OpenAlex."
    doi_line = f"- **DOI:** `{paper.doi}`\n" if paper.doi else ""
    link_line = f"- **Paper:** {paper.url}\n" if paper.url else ""

    body = (
        f"## {paper.title}\n\n"
        f"- **Publication date:** {paper.publication_date}\n"
        f"- **Type:** {paper.work_type}\n"
        f"- **Journal/source:** {paper.venue}\n"
        f"- **Authors:** {paper.authors}\n"
        f"{doi_line}"
        f"- **Matched terms:** {matched}\n"
        f"{link_line}\n"
        f"### Abstract\n\n{abstract}\n\n"
        "---\n"
        "Automatically selected from OpenAlex by the acidic CO₂ electroreduction filter."
    )
    return title, body


def create_github_issue(token: str, repository: str, paper: Paper) -> None:
    title, body = format_github_issue(paper)
    response = requests.post(
        GITHUB_ISSUES_URL.format(repository=repository),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": title, "body": body},
        timeout=30,
    )
    response.raise_for_status()


def notify_papers(token: str, repository: str, papers: list[Paper]) -> list[str]:
    delivered: list[str] = []
    for paper in papers:
        create_github_issue(token, repository, paper)
        delivered.append(paper.key)
        time.sleep(0.25)
    return delivered


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matching unseen papers without creating GitHub Issues or changing state.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=int(os.getenv("LOOKBACK_DAYS", "365")),
        help="How far back to search on every run (default: 365).",
    )
    parser.add_argument(
        "--per-query",
        type=int,
        default=int(os.getenv("RESULTS_PER_QUERY", "100")),
        help="Maximum OpenAlex results fetched per query (default: 100).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    api_key = os.getenv("OPENALEX_API_KEY", "").strip()
    if not api_key:
        logging.error("OPENALEX_API_KEY is required.")
        return 2

    token = os.getenv("GITHUB_TOKEN", "").strip()
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not args.dry_run and (not token or not repository):
        logging.error("GITHUB_TOKEN and GITHUB_REPOSITORY are required.")
        return 2

    state = load_state()
    seen: dict[str, Any] = state["seen"]
    first_run = not seen

    logging.info("Searching OpenAlex for the last %s days...", args.lookback_days)
    works = fetch_recent_works(api_key, args.lookback_days, args.per_query)

    relevant: list[Paper] = []
    for work in works:
        accepted, matched_terms = relevance(work)
        if not accepted:
            continue
        paper = to_paper(work, matched_terms)
        if paper.key and paper.key not in seen:
            relevant.append(paper)

    logging.info("Found %s relevant unseen papers.", len(relevant))
    if not relevant:
        return 0

    first_run_limit = max(0, int(os.getenv("FIRST_RUN_SEND_LIMIT", "8")))
    max_alerts = max(1, int(os.getenv("MAX_ALERTS_PER_RUN", "20")))

    if args.dry_run:
        for paper in relevant[:max_alerts]:
            print("=" * 80)
            issue_title, issue_body = format_github_issue(paper)
            print(issue_title)
            print(issue_body)
        return 0

    now = datetime.now(timezone.utc).isoformat()
    send_limit = first_run_limit if first_run else max_alerts
    papers_to_send = relevant[:send_limit]
    delivered = notify_papers(token, repository, papers_to_send) if papers_to_send else []
    delivered_set = set(delivered)
    for paper in papers_to_send:
        if paper.key in delivered_set:
            seen[paper.key] = {
                "first_seen": now,
                "title": paper.title,
                "notified": True,
            }

    trim_state(state)
    save_state(state)
    logging.info("Delivered %s alert(s) and updated %s.", len(delivered), STATE_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
