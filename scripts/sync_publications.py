#!/usr/bin/env python3
"""Synchronize Marcus Vukojevic's publications from OpenAlex and arXiv.

OpenAlex's official Works API is the primary source because it can include
journal and conference records that are not on arXiv. The official arXiv Atom
API supplies authoritative preprint metadata and acts as a fallback. Only
Python's standard library is used.

Output is deterministic: records and fields have a fixed order, formatting
whitespace is normalized, and retrieval/citation counters are not stored. A
degraded or empty response is never allowed to replace different last-good data.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable


AUTHOR = "Marcus Vukojevic"
OPENALEX_AUTHOR_ID = "A5119861930"
OPENALEX_AUTHOR_URL = f"https://openalex.org/{OPENALEX_AUTHOR_ID}"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"
ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
EXPECTED_ARXIV_IDS = {"2505.23875", "2605.05953", "2606.02559"}
EXCLUDED_TYPES = {"dataset", "paratext"}
EXCLUDED_TITLE_FRAGMENTS = {"hub trentino innovazione"}

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "_data" / "publications.yml"

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
VERSION_SUFFIX = re.compile(r"v\d+$")
ARXIV_DOI_PATTERN = re.compile(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})", re.IGNORECASE)
ARXIV_URL_PATTERN = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)


def normalize(value: object | None) -> str:
    """Collapse formatting whitespace into a stable single-line value."""

    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_title(value: object | None) -> str:
    ascii_value = unicodedata.normalize("NFKD", normalize(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def normalize_doi(value: object | None) -> str:
    doi = normalize(value).casefold()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi)
    return doi.rstrip("/")


def trusted_https_url(value: object | None, allowed_host: str | None = None) -> str:
    """Return a normalized HTTPS URL, optionally restricted to one hostname."""

    url = normalize(value)
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        return ""
    if allowed_host and parsed.hostname.casefold() != allowed_host.casefold():
        return ""
    return url


def child_text(element: ET.Element, name: str, namespace: str = ATOM) -> str:
    return normalize(element.findtext(f"{namespace}{name}"))


def canonical_arxiv_id(entry_id: str) -> str:
    marker = "/abs/"
    if marker not in entry_id:
        raise ValueError(f"Unexpected arXiv entry id: {entry_id!r}")
    return VERSION_SUFFIX.sub("", entry_id.split(marker, 1)[1])


def arxiv_id_from_openalex(work: dict[str, object]) -> str:
    candidates = [work.get("doi")]
    for location_name in ("primary_location", "best_oa_location"):
        location = work.get(location_name) or {}
        if isinstance(location, dict):
            candidates.extend([location.get("landing_page_url"), location.get("pdf_url")])
    for location in work.get("locations") or []:
        if isinstance(location, dict):
            candidates.extend([location.get("landing_page_url"), location.get("pdf_url")])

    for candidate in candidates:
        value = normalize(candidate)
        for pattern in (ARXIV_DOI_PATTERN, ARXIV_URL_PATTERN):
            match = pattern.search(value)
            if match:
                return match.group(1)
    return ""


def reconstruct_abstract(inverted_index: object) -> str:
    if not isinstance(inverted_index, dict):
        return ""
    positioned_words: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned_words.append((position, str(word)))
    return normalize(" ".join(word for _, word in sorted(positioned_words)))


def parse_openalex(payload: bytes) -> list[dict[str, object]]:
    document = json.loads(payload)
    if not isinstance(document, dict) or not isinstance(document.get("results"), list):
        raise ValueError("OpenAlex response does not contain a results list")

    records: list[dict[str, object]] = []
    for work in document["results"]:
        if not isinstance(work, dict):
            continue

        work_type = normalize(work.get("type")).casefold()
        title = normalize(work.get("display_name") or work.get("title"))
        folded_title = title.casefold()
        if work_type in EXCLUDED_TYPES or work.get("is_paratext"):
            continue
        if any(fragment in folded_title for fragment in EXCLUDED_TITLE_FRAGMENTS):
            continue

        authorships = work.get("authorships") or []
        if not any(
            isinstance(authorship, dict)
            and isinstance(authorship.get("author"), dict)
            and authorship["author"].get("id") == OPENALEX_AUTHOR_URL
            for authorship in authorships
        ):
            continue

        authors = [
            normalize(authorship.get("author", {}).get("display_name"))
            for authorship in authorships
            if isinstance(authorship, dict) and isinstance(authorship.get("author"), dict)
        ]
        authors = [author for author in authors if author]
        published = normalize(work.get("publication_date"))
        if not (title and authors and re.fullmatch(r"\d{4}-\d{2}-\d{2}", published)):
            continue

        primary_location = work.get("primary_location") or {}
        best_location = work.get("best_oa_location") or {}
        if not isinstance(primary_location, dict):
            primary_location = {}
        if not isinstance(best_location, dict):
            best_location = {}

        source = primary_location.get("source") or {}
        source_name = normalize(source.get("display_name")) if isinstance(source, dict) else ""
        is_arxiv_source = "arxiv" in source_name.casefold()
        journal_ref = source_name if source_name and not is_arxiv_source and work_type != "preprint" else ""

        arxiv_id = arxiv_id_from_openalex(work)
        doi = normalize_doi(work.get("doi"))
        external_doi = doi and not doi.startswith("10.48550/arxiv.")
        openalex_url = trusted_https_url(work.get("id"), "openalex.org")
        landing_url = trusted_https_url(primary_location.get("landing_page_url"))
        pdf_url = ""
        if arxiv_id:
            arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        else:
            arxiv_url = ""

        primary_topic = work.get("primary_topic") or {}
        primary_category = normalize(primary_topic.get("display_name")) if isinstance(primary_topic, dict) else ""

        records.append(
            {
                "_source": "openalex",
                "_type": work_type,
                "_doi": doi,
                "openalex_url": openalex_url,
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": authors,
                "published": published,
                "updated": published,
                "year": int(published[:4]),
                "primary_category": primary_category,
                "categories": [primary_category] if primary_category else [],
                "journal_ref": journal_ref,
                "doi_url": f"https://doi.org/{doi}" if external_doi else "",
                "arxiv_url": arxiv_url,
                "pdf_url": pdf_url,
                "url": arxiv_url or (f"https://doi.org/{doi}" if doi else landing_url or openalex_url),
                "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
            }
        )

    return records


def parse_arxiv(payload: bytes) -> list[dict[str, object]]:
    root = ET.fromstring(payload)
    records: list[dict[str, object]] = []

    for entry in root.findall(f"{ATOM}entry"):
        authors = [child_text(author, "name") for author in entry.findall(f"{ATOM}author")]
        authors = [author for author in authors if author]

        # arXiv's author search can be fuzzy; retain exact-author matches only.
        if AUTHOR.casefold() not in {author.casefold() for author in authors}:
            continue

        arxiv_id = canonical_arxiv_id(child_text(entry, "id"))
        published = child_text(entry, "published")
        updated = child_text(entry, "updated")
        title = child_text(entry, "title")
        if not (arxiv_id and published and updated and title and authors):
            raise ValueError(f"arXiv entry {arxiv_id or '<unknown>'} is missing required metadata")

        primary_category_element = entry.find(f"{ARXIV}primary_category")
        primary_category = ""
        if primary_category_element is not None:
            primary_category = normalize(primary_category_element.get("term"))

        categories = sorted(
            {
                normalize(category.get("term"))
                for category in entry.findall(f"{ATOM}category")
                if normalize(category.get("term"))
            }
        )
        if primary_category and primary_category in categories:
            categories.remove(primary_category)
            categories.insert(0, primary_category)

        doi = normalize_doi(child_text(entry, "doi", ARXIV))
        records.append(
            {
                "_source": "arxiv",
                "_type": "preprint",
                "_doi": doi,
                "openalex_url": "",
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": authors,
                "published": published[:10],
                "updated": updated[:10],
                "year": int(published[:4]),
                "primary_category": primary_category,
                "categories": categories,
                "journal_ref": child_text(entry, "journal_ref", ARXIV),
                "doi_url": f"https://doi.org/{doi}" if doi else "",
                "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                "url": "",
                "abstract": child_text(entry, "summary"),
            }
        )

    return records


def same_work(first: dict[str, object], second: dict[str, object]) -> bool:
    first_title = normalize_title(first.get("title"))
    second_title = normalize_title(second.get("title"))
    first_doi = normalize_doi(first.get("_doi"))
    second_doi = normalize_doi(second.get("_doi"))
    first_arxiv = normalize(first.get("arxiv_id"))
    second_arxiv = normalize(second.get("arxiv_id"))
    return bool(
        (first_title and first_title == second_title)
        or (first_doi and first_doi == second_doi)
        or (first_arxiv and first_arxiv == second_arxiv)
    )


def record_quality(record: dict[str, object]) -> tuple[int, str]:
    type_scores = {
        "article": 6,
        "book-chapter": 5,
        "proceedings-article": 5,
        "review": 4,
        "preprint": 2,
    }
    score = type_scores.get(normalize(record.get("_type")).casefold(), 3)
    doi = normalize_doi(record.get("_doi"))
    if doi and not doi.startswith("10.48550/arxiv."):
        score += 4
    if record.get("journal_ref"):
        score += 3
    if record.get("abstract"):
        score += 1
    return score, normalize(record.get("openalex_url") or record.get("arxiv_id"))


def merge_group(group: list[dict[str, object]]) -> dict[str, object]:
    best = max(group, key=record_quality)
    merged = dict(best)

    for candidate in sorted(group, key=record_quality, reverse=True):
        for field in (
            "openalex_url",
            "arxiv_id",
            "journal_ref",
            "doi_url",
            "arxiv_url",
            "pdf_url",
            "url",
            "abstract",
        ):
            if not merged.get(field) and candidate.get(field):
                merged[field] = candidate[field]

    arxiv_records = [record for record in group if record.get("_source") == "arxiv"]
    if arxiv_records:
        arxiv = max(arxiv_records, key=record_quality)
        for field in ("arxiv_id", "updated", "primary_category", "categories", "arxiv_url", "pdf_url"):
            if arxiv.get(field):
                merged[field] = arxiv[field]
        if arxiv.get("abstract"):
            merged["abstract"] = arxiv["abstract"]
        if not merged.get("journal_ref") and arxiv.get("journal_ref"):
            merged["journal_ref"] = arxiv["journal_ref"]
        if normalize(merged.get("_type")).casefold() == "preprint":
            for field in ("title", "authors", "published", "year"):
                merged[field] = arxiv[field]

    return merged


def deduplicate(records: list[dict[str, object]]) -> list[dict[str, object]]:
    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    for first in range(len(records)):
        for second in range(first + 1, len(records)):
            if same_work(records[first], records[second]):
                union(first, second)

    groups: dict[int, list[dict[str, object]]] = {}
    for index, record in enumerate(records):
        groups.setdefault(find(index), []).append(record)

    merged = [merge_group(group) for group in groups.values()]
    return sorted(
        merged,
        key=lambda record: (str(record["published"]), normalize_title(record["title"])),
        reverse=True,
    )


def validate(publications: list[dict[str, object]]) -> None:
    if not publications:
        raise ValueError("publication sources returned no usable records")
    found_arxiv_ids = {normalize(publication.get("arxiv_id")) for publication in publications}
    missing = EXPECTED_ARXIV_IDS.difference(found_arxiv_ids)
    if missing:
        raise ValueError(f"publication sources omitted known work(s): {', '.join(sorted(missing))}")


def yaml_string(value: object) -> str:
    """Return a JSON-quoted scalar, which is also a valid YAML scalar."""

    return json.dumps(str(value), ensure_ascii=False)


def render_yaml(publications: list[dict[str, object]]) -> str:
    lines = [
        "# Generated from the official OpenAlex Works and arXiv Atom APIs.",
        "# Do not edit manually; update scripts/sync_publications.py if the schema changes.",
    ]

    for publication in publications:
        arxiv_id = normalize(publication.get("arxiv_id"))
        openalex_url = normalize(publication.get("openalex_url"))
        if arxiv_id:
            lines.append(f"- arxiv_id: {yaml_string(arxiv_id)}")
        else:
            lines.append(f"- openalex_url: {yaml_string(openalex_url)}")
        lines.extend(
            [
                f"  title: {yaml_string(publication['title'])}",
                "  authors:",
            ]
        )
        lines.extend(f"    - {yaml_string(author)}" for author in publication["authors"])
        lines.extend(
            [
                f"  published: {yaml_string(publication['published'])}",
                f"  updated: {yaml_string(publication['updated'])}",
                f"  year: {publication['year']}",
                f"  primary_category: {yaml_string(publication['primary_category'])}",
            ]
        )
        if publication["categories"]:
            lines.append("  categories:")
            lines.extend(f"    - {yaml_string(category)}" for category in publication["categories"])
        else:
            lines.append("  categories: []")

        for field in ("journal_ref", "doi_url", "arxiv_url", "pdf_url"):
            if publication.get(field):
                lines.append(f"  {field}: {yaml_string(publication[field])}")
        if publication.get("url") and publication.get("url") != publication.get("arxiv_url"):
            lines.append(f"  url: {yaml_string(publication['url'])}")
        if not arxiv_id and openalex_url:
            # openalex_url is already the list item's first field; do not repeat it.
            pass
        elif openalex_url and not publication.get("arxiv_url"):
            lines.append(f"  openalex_url: {yaml_string(openalex_url)}")

        lines.append("  abstract: >-")
        abstract_lines = textwrap.wrap(
            str(publication.get("abstract") or ""),
            width=100,
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]
        lines.extend(f"    {line}" for line in abstract_lines)

    return "\n".join(lines) + "\n"


def openalex_query_url() -> str:
    parameters = urllib.parse.urlencode(
        {
            "filter": f"author.id:{OPENALEX_AUTHOR_ID}",
            "per-page": 200,
            "sort": "publication_date:desc",
        }
    )
    return f"{OPENALEX_ENDPOINT}?{parameters}"


def arxiv_query_url() -> str:
    parameters = urllib.parse.urlencode(
        {
            "search_query": f'au:"{AUTHOR}"',
            "start": 0,
            "max_results": 100,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    return f"{ARXIV_ENDPOINT}?{parameters}"


def fetch(url: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "MarcusVukojevic-publications/2.0 (https://marcusvukojevic.github.io)",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def read_source(path: str | None, fetcher: Callable[[], bytes]) -> bytes:
    if path is None:
        return fetcher()
    if path == "-":
        return sys.stdin.buffer.read()
    return Path(path).read_bytes()


def write_output(path: str, content: str) -> bool:
    """Write only when content changes; return whether a file was changed."""

    if path == "-":
        sys.stdout.write(content)
        return False
    output = Path(path)
    existing = output.read_text(encoding="utf-8") if output.exists() else None
    if existing == content:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return True


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openalex-input", help="read OpenAlex JSON from a file instead of the API")
    parser.add_argument("--arxiv-input", help="read arXiv Atom XML from a file instead of the API")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="destination YAML, or '-' for stdout")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    source_errors: list[str] = []

    try:
        openalex_records = parse_openalex(
            read_source(
                arguments.openalex_input,
                lambda: fetch(openalex_query_url(), "application/json"),
            )
        )
        if not openalex_records:
            raise ValueError("OpenAlex returned no usable works")
    except (json.JSONDecodeError, OSError, ValueError) as error:
        source_errors.append(f"OpenAlex: {error}")
        openalex_records = []

    try:
        arxiv_records = parse_arxiv(
            read_source(
                arguments.arxiv_input,
                lambda: fetch(arxiv_query_url(), "application/atom+xml"),
            )
        )
        if not arxiv_records:
            raise ValueError("arXiv returned no exact-author works")
    except (ET.ParseError, OSError, ValueError) as error:
        source_errors.append(f"arXiv: {error}")
        arxiv_records = []

    publications = deduplicate(openalex_records + arxiv_records)
    validate(publications)
    content = render_yaml(publications)

    if source_errors and arguments.output != "-":
        output = Path(arguments.output)
        existing = output.read_text(encoding="utf-8") if output.exists() else None
        if existing is not None and existing != content:
            details = "; ".join(source_errors)
            raise RuntimeError(f"degraded sync refused; last-good data preserved ({details})")

    changed = write_output(arguments.output, content)
    if arguments.output != "-":
        state = "updated" if changed else "already up to date"
        warning = f"; fallback used: {'; '.join(source_errors)}" if source_errors else ""
        print(f"{arguments.output}: {state} ({len(publications)} publications){warning}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ET.ParseError, OSError, RuntimeError, ValueError) as error:
        print(f"Publication sync failed: {error}", file=sys.stderr)
        raise SystemExit(1)
