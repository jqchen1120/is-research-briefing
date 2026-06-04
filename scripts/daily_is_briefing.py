from __future__ import annotations

import html
import json
import os
import re
import smtplib
import ssl
import sys
import textwrap
import urllib.parse
import urllib.request
from concurrent.futures import TimeoutError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Iterable


PREMIER_IS_JOURNALS = [
    ("MIS Quarterly", "0276-7783"),
    ("Information Systems Research", "1047-7047"),
    ("Management Science", "0025-1909"),
]

OTHER_TOP_IS_JOURNALS = [
    ("Journal of Management Information Systems", "0742-1222"),
    ("Decision Support Systems", "0167-9236"),
    ("Journal of the Association for Information Systems", "1536-9323"),
    ("Information & Management", "0378-7206"),
    ("European Journal of Information Systems", "0960-085X"),
    ("Information Systems Journal", "1350-1917"),
    ("Journal of Strategic Information Systems", "0963-8687"),
    ("Information Systems Frontiers", "1387-3326"),
    ("International Journal of Information Management", "0268-4012"),
    ("Information Systems", "0306-4379"),
    ("Electronic Markets", "1019-6781"),
    ("Internet Research", "1066-2243"),
    ("Government Information Quarterly", "0740-624X"),
    ("Journal of Organizational Computing and Electronic Commerce", "1091-9392"),
]


@dataclass
class Paper:
    title: str
    authors: str
    date: str
    journal: str
    url: str
    abstract: str
    keywords: tuple[str, ...]
    cited_by_count: int


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def is_future_date(value: str) -> bool:
    return bool(value and value[:10] > today_utc())


def fetch_json(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "is-research-briefing/3.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def inverted_index_to_text(index: dict[str, list[int]]) -> str:
    if not index:
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            pairs.append((position, word))
    return clean_text(" ".join(word for _, word in sorted(pairs)))


def raw_keywords(item: dict) -> tuple[str, ...]:
    values: list[str] = []
    for keyword in item.get("keywords") or []:
        label = clean_text(keyword.get("display_name", ""))
        if label:
            values.append(label)
    return tuple(dedupe_strings(values)[:8])


def dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def paper_from_openalex(item: dict) -> Paper | None:
    title = clean_text(item.get("title", ""))
    date = clean_text(item.get("publication_date", ""))
    if not title or is_future_date(date):
        return None

    primary_location = item.get("primary_location") or {}
    source_obj = primary_location.get("source") or {}
    journal = clean_text(source_obj.get("display_name", ""))
    authors = ", ".join(
        clean_text(author.get("author", {}).get("display_name", ""))
        for author in item.get("authorships", [])[:6]
        if author.get("author")
    )
    doi = clean_text(item.get("doi", ""))
    return Paper(
        title=title,
        authors=authors or "Unknown authors",
        date=date,
        journal=journal or "Unknown journal",
        url=doi or item.get("id") or "",
        abstract=inverted_index_to_text(item.get("abstract_inverted_index") or {}),
        keywords=raw_keywords(item),
        cited_by_count=int(item.get("cited_by_count") or 0),
    )


def search_openalex_issn(journal_name: str, issn: str, from_date: str, per_page: int = 10) -> list[Paper]:
    filters = [
        f"primary_location.source.issn:{issn}",
        f"from_publication_date:{from_date}",
        f"to_publication_date:{today_utc()}",
        "type:article",
    ]
    params = {
        "filter": ",".join(filters),
        "sort": "publication_date:desc",
        "per-page": str(per_page),
    }
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    try:
        data = fetch_json(url)
    except Exception as exc:
        print(f"OpenAlex ISSN query failed for {journal_name!r}: {exc}", file=sys.stderr)
        return []
    papers = [paper_from_openalex(item) for item in data.get("results", [])]
    return [paper for paper in papers if paper and not is_editorial(paper)]


def search_journal_group(journals: list[tuple[str, str]], from_date: str, per_page: int = 10) -> list[Paper]:
    papers: list[Paper] = []
    max_workers = min(6, len(journals))
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        futures = [
            executor.submit(search_openalex_issn, journal_name, issn, from_date, per_page)
            for journal_name, issn in journals
        ]
        try:
            for future in as_completed(futures, timeout=45):
                papers.extend(future.result())
        except TimeoutError:
            print("OpenAlex journal batch timed out; using completed journal results.", file=sys.stderr)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return sorted(dedupe_papers(papers), key=paper_sort_key, reverse=True)[:10]


def is_editorial(paper: Paper) -> bool:
    title = paper.title.lower()
    markers = [
        "editor's comments",
        "editorial",
        "call for papers",
        "erratum",
        "corrigendum",
        "correction to",
        "retraction",
    ]
    return any(marker in title for marker in markers)


def dedupe_papers(papers: Iterable[Paper]) -> list[Paper]:
    seen: set[str] = set()
    result: list[Paper] = []
    for paper in papers:
        key = re.sub(r"[^a-z0-9]+", "", paper.title.lower())[:140]
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(paper)
    return result


def paper_sort_key(paper: Paper) -> tuple[str, int]:
    return (paper.date or "", paper.cited_by_count)


def paper_block(paper: Paper) -> list[str]:
    return [
        f"### {paper.title}",
        f"- Journal: {paper.journal}",
        f"- Date: {paper.date or 'Unknown'}",
        f"- Citations: {paper.cited_by_count} OpenAlex citations",
        f"- Authors: {paper.authors}",
        f"- Link: {paper.url or 'No link available'}",
        f"- Keywords: {', '.join(paper.keywords) if paper.keywords else 'No source keywords available'}",
        f"- Abstract: {paper.abstract or 'No source abstract available'}",
        "",
    ]


def build_markdown() -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    from_date = days_ago(30)
    premier = search_journal_group(PREMIER_IS_JOURNALS, from_date, per_page=10)
    other_top = search_journal_group(OTHER_TOP_IS_JOURNALS, from_date, per_page=10)

    lines = [
        "# Daily IS Journal Paper Briefing",
        f"Generated: {now:%Y-%m-%d %H:%M} Asia/Shanghai",
        f"Window: {from_date} to {today_utc()} UTC",
        "",
        "## 1. ISR / MISQ / Management Science",
        "",
    ]
    if premier:
        for paper in premier:
            lines.extend(paper_block(paper))
    else:
        lines.extend(["No source-matched papers found in the last 30 days.", ""])

    lines.extend(["## 2. Other Strong IS Journals", ""])
    if other_top:
        for paper in other_top:
            lines.extend(paper_block(paper))
    else:
        lines.extend(["No source-matched papers found in the last 30 days.", ""])

    return "\n".join(lines)


def send_email(markdown: str) -> None:
    required = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    mail_from = os.environ["MAIL_FROM"]
    recipients = [addr.strip() for addr in os.environ["MAIL_TO"].split(",") if addr.strip()]

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    message = EmailMessage()
    message["Subject"] = f"Daily IS Journal Paper Briefing - {today}"
    message["From"] = mail_from
    message["To"] = ", ".join(recipients)
    message.set_content(markdown)
    message.add_alternative(markdown_to_html(markdown), subtype="html")

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls(context=context)
            smtp.login(username, password)
            smtp.send_message(message)


def markdown_to_html(markdown: str) -> str:
    escaped = html.escape(markdown)
    escaped = re.sub(r"^# (.+)$", r"<h1>\1</h1>", escaped, flags=re.MULTILINE)
    escaped = re.sub(r"^## (.+)$", r"<h2>\1</h2>", escaped, flags=re.MULTILINE)
    escaped = re.sub(r"^### (.+)$", r"<h3>\1</h3>", escaped, flags=re.MULTILINE)
    escaped = re.sub(r"^- (.+)$", r"<li>\1</li>", escaped, flags=re.MULTILINE)
    escaped = escaped.replace("\n\n", "<br><br>")
    return textwrap.dedent(
        f"""
        <!doctype html>
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.5; color: #222;">
        {escaped}
        </body>
        </html>
        """
    ).strip()


def main() -> None:
    markdown = build_markdown()
    print(markdown)
    send_email(markdown)


if __name__ == "__main__":
    main()
