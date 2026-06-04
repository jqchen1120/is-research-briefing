from __future__ import annotations

import html
import json
import os
import re
import smtplib
import ssl
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import TimeoutError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Iterable


FRESH_ARXIV_QUERY = " OR ".join(
    [
        "cat:cs.AI",
        "cat:cs.CL",
        "cat:cs.LG",
        "cat:cs.CV",
        "cat:cs.RO",
        "cat:stat.ML",
    ]
)

TRENDING_AI_QUERIES = [
    "large language models reasoning agents",
    "foundation models multimodal learning",
    "language model alignment safety evaluation",
    "retrieval augmented generation language models",
    "efficient language models distillation quantization",
    "diffusion models generative AI",
    "vision language models multimodal",
    "reinforcement learning language models agents",
    "AI for science foundation models",
    "robotics vision language action models",
]

AI_CORE_TERMS = [
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "neural",
    "foundation model",
    "large language model",
    "language model",
    "llm",
    "transformer",
    "multimodal",
    "vision-language",
    "diffusion",
    "reinforcement learning",
    "agent",
    "retrieval augmented generation",
    "rag",
    "alignment",
    "computer vision",
    "robotics",
]

LOW_SIGNAL_TERMS = [
    "survey",
    "position paper",
    "perspective",
    "editorial",
    "commentary",
    "call for papers",
    "erratum",
    "corrigendum",
    "correction",
    "retraction",
]


@dataclass
class Paper:
    title: str
    authors: str
    date: str
    source: str
    url: str
    abstract: str
    keywords: tuple[str, ...]
    cited_by_count: int | None = None
    venue: str = ""


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def is_future_date(value: str) -> bool:
    return bool(value and value[:10] > today_utc())


def fetch_json(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "daily-ai-paper-briefing/3.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "daily-ai-paper-briefing/3.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def inverted_index_to_text(index: dict[str, list[int]]) -> str:
    if not index:
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            pairs.append((position, word))
    return clean_text(" ".join(word for _, word in sorted(pairs)))


def dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        label = clean_text(value).strip(" .;:,")
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(label)
    return result


def openalex_keywords(item: dict) -> tuple[str, ...]:
    values: list[str] = []
    for keyword in item.get("keywords") or []:
        values.append(clean_text(keyword.get("display_name", "")))
    primary_topic = item.get("primary_topic") or {}
    values.append(clean_text(primary_topic.get("display_name", "")))
    for topic in item.get("topics") or []:
        values.append(clean_text(topic.get("display_name", "")))
    return tuple(dedupe_strings(values)[:8])


def arxiv_keywords(entry: ET.Element, ns: dict[str, str]) -> tuple[str, ...]:
    terms = [
        clean_text(category.attrib.get("term", ""))
        for category in entry.findall("atom:category", ns)
        if category.attrib.get("term")
    ]
    return tuple(dedupe_strings(terms)[:8])


def text_of(paper: Paper) -> str:
    return f"{paper.title} {paper.abstract} {paper.source} {paper.venue} {' '.join(paper.keywords)}".lower()


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)


def is_ai_paper(paper: Paper) -> bool:
    text = text_of(paper)
    if contains_any(text, LOW_SIGNAL_TERMS):
        return False
    return contains_any(text, AI_CORE_TERMS) or any(
        keyword in {"cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.RO", "stat.ML"}
        for keyword in paper.keywords
    )


def arxiv_date_score(date: str) -> int:
    if date >= days_ago(2):
        return 20
    if date >= days_ago(7):
        return 10
    return 0


def score_fresh_arxiv(paper: Paper) -> int:
    text = text_of(paper)
    return (
        arxiv_date_score(paper.date)
        + 4 * sum(term in text for term in ["large language model", "llm", "agent", "multimodal", "reasoning"])
        + 3 * sum(term in text for term in ["alignment", "safety", "rag", "diffusion", "robotics"])
        + len(paper.keywords)
    )


def search_fresh_arxiv() -> list[Paper]:
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    params = {
        "search_query": FRESH_ARXIV_QUERY,
        "start": "0",
        "max_results": "120",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    try:
        text = fetch_text(url)
    except Exception as exc:
        print(f"arXiv query failed: {exc}")
        return []

    root = ET.fromstring(text)
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", ns):
        title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        date = clean_text(entry.findtext("atom:published", default="", namespaces=ns))[:10]
        if not title or is_future_date(date) or date < days_ago(14):
            continue
        abstract = clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
        authors = ", ".join(
            clean_text(author.findtext("atom:name", default="", namespaces=ns))
            for author in entry.findall("atom:author", ns)[:8]
        )
        paper = Paper(
            title=title,
            authors=authors or "Unknown authors",
            date=date,
            source="arXiv",
            venue="arXiv",
            url=clean_text(entry.findtext("atom:id", default="", namespaces=ns)),
            abstract=abstract,
            keywords=arxiv_keywords(entry, ns),
            cited_by_count=None,
        )
        if is_ai_paper(paper):
            papers.append(paper)
    return sorted(dedupe_papers(papers), key=score_fresh_arxiv, reverse=True)[:10]


def paper_from_openalex(item: dict) -> Paper | None:
    title = clean_text(item.get("title", ""))
    date = clean_text(item.get("publication_date", ""))
    if not title or is_future_date(date):
        return None
    authors = ", ".join(
        clean_text(author.get("author", {}).get("display_name", ""))
        for author in item.get("authorships", [])[:8]
        if author.get("author")
    )
    primary_location = item.get("primary_location") or {}
    source_obj = primary_location.get("source") or {}
    venue = clean_text(source_obj.get("display_name", ""))
    doi = clean_text(item.get("doi", ""))
    return Paper(
        title=title,
        authors=authors or "Unknown authors",
        date=date,
        source="OpenAlex",
        venue=venue or "Unknown venue",
        url=doi or item.get("id") or "",
        abstract=inverted_index_to_text(item.get("abstract_inverted_index") or {}),
        keywords=openalex_keywords(item),
        cited_by_count=int(item.get("cited_by_count") or 0),
    )


def search_openalex(query: str, from_date: str, per_page: int = 20) -> list[Paper]:
    filters = [
        f"from_publication_date:{from_date}",
        f"to_publication_date:{today_utc()}",
    ]
    params = {
        "search": query,
        "filter": ",".join(filters),
        "sort": "cited_by_count:desc",
        "per-page": str(per_page),
    }
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    try:
        data = fetch_json(url)
    except Exception as exc:
        print(f"OpenAlex query failed for {query!r}: {exc}")
        return []
    papers = [paper_from_openalex(item) for item in data.get("results", [])]
    return [paper for paper in papers if paper and is_ai_paper(paper)]


def search_trending_ai() -> list[Paper]:
    papers: list[Paper] = []
    executor = ThreadPoolExecutor(max_workers=5)
    try:
        futures = [
            executor.submit(search_openalex, query, days_ago(30), 15)
            for query in TRENDING_AI_QUERIES
        ]
        try:
            for future in as_completed(futures, timeout=35):
                papers.extend(future.result())
        except TimeoutError:
            print("OpenAlex trending batch timed out; using completed query results.")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return sorted(dedupe_papers(papers), key=score_trending, reverse=True)[:10]


def score_trending(paper: Paper) -> tuple[int, str]:
    citations = paper.cited_by_count or 0
    text = text_of(paper)
    topic_bonus = sum(term in text for term in ["large language model", "agent", "multimodal", "alignment", "diffusion", "robotics"])
    return (citations * 10 + topic_bonus, paper.date or "")


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


def paper_block(paper: Paper) -> list[str]:
    citation_text = (
        f"{paper.cited_by_count} OpenAlex citations"
        if paper.cited_by_count is not None
        else "Not available for fresh arXiv metadata"
    )
    return [
        f"### {paper.title}",
        f"- Source: {paper.venue or paper.source}",
        f"- Date: {paper.date or 'Unknown'}",
        f"- Citations: {citation_text}",
        f"- Authors: {paper.authors}",
        f"- Link: {paper.url or 'No link available'}",
        f"- Keywords: {', '.join(paper.keywords) if paper.keywords else 'No source keywords available'}",
        f"- Abstract: {paper.abstract or 'No source abstract available'}",
        "",
    ]


def build_markdown() -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    fresh = search_fresh_arxiv()
    trending = search_trending_ai()

    lines = [
        "# Daily AI Paper Briefing",
        f"Generated: {now:%Y-%m-%d %H:%M} Asia/Shanghai",
        "",
        "## 1. Fresh arXiv AI Papers",
        "",
    ]
    if fresh:
        for paper in fresh:
            lines.extend(paper_block(paper))
    else:
        lines.extend(["No source-matched fresh arXiv AI papers found.", ""])

    lines.extend(["## 2. Trending AI Papers", ""])
    if trending:
        for paper in trending:
            lines.extend(paper_block(paper))
    else:
        lines.extend(["No source-matched trending AI papers found in the last 30 days.", ""])

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
    message["Subject"] = f"Daily AI Paper Briefing - {today}"
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
