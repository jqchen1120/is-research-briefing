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
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Iterable


TOPICS = [
    "information systems design science",
    "design science research information systems",
    "digital artifact design information systems",
    "human AI collaboration artifact",
    "generative AI information systems design",
    "decision support systems design science",
    "digital platform design information systems",
    "enterprise systems design science",
    "health information technology design science",
    "privacy cybersecurity tool design information systems",
]

VENUES = [
    "MIS Quarterly",
    "Information Systems Research",
    "Journal of Management Information Systems",
    "Journal of the Association for Information Systems",
    "Information & Management",
    "Decision Support Systems",
    "International Conference on Information Systems",
    "European Conference on Information Systems",
    "Pacific Asia Conference on Information Systems",
    "Hawaii International Conference on System Sciences",
]

DSR_TERMS = [
    "design science",
    "artifact",
    "artefact",
    "prototype",
    "design principle",
    "design theory",
    "design knowledge",
    "design evaluation",
    "instantiate",
    "instantiation",
    "build and evaluate",
    "decision aid",
    "decision support",
    "system design",
    "framework",
    "method",
    "tool",
]

EMPIRICAL_TERMS = [
    "empirical",
    "survey",
    "field experiment",
    "experiment",
    "quasi-experiment",
    "econometric",
    "archival",
    "panel data",
    "difference-in-differences",
    "regression",
    "case study",
    "interview",
    "mixed method",
]

BEHAVIORAL_TERMS = [
    "behavior",
    "behaviour",
    "adoption",
    "user",
    "individual",
    "team",
    "organization",
    "organisation",
    "trust",
    "acceptance",
    "intention",
    "human-ai",
    "human ai",
]

HIGH_VALUE_READING_QUERIES = [
    "design science research information systems artifact evaluation",
    "design principles information systems artificial intelligence",
    "design science generative AI information systems",
    "human AI collaboration design science information systems",
    "digital platform design principles information systems",
    "decision support systems design science artificial intelligence",
    "health information technology design science artifact",
    "cybersecurity privacy tool design science information systems",
]


@dataclass
class Paper:
    title: str
    authors: str
    date: str
    source: str
    url: str
    abstract: str
    venue: str = ""
    doi: str = ""
    cited_by_count: int = 0


def fetch_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "is-research-briefing/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "is-research-briefing/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def recent_cutoff(days: int = 14) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def is_future_date(value: str) -> bool:
    return bool(value and value[:10] > datetime.now(timezone.utc).date().isoformat())


def search_openalex() -> list[Paper]:
    papers: list[Paper] = []
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    for topic in TOPICS:
        params = {
            "search": topic,
            "filter": f"from_publication_date:{recent_cutoff(21)}",
            "sort": "publication_date:desc",
            "per-page": "8",
        }
        if mailto:
            params["mailto"] = mailto
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"OpenAlex query failed for {topic!r}: {exc}", file=sys.stderr)
            continue
        for item in data.get("results", []):
            title = clean_text(item.get("title", ""))
            if not title:
                continue
            publication_date = clean_text(item.get("publication_date", ""))
            if is_future_date(publication_date):
                continue
            authors = ", ".join(
                clean_text(a.get("author", {}).get("display_name", ""))
                for a in item.get("authorships", [])[:6]
                if a.get("author")
            )
            abstract = inverted_index_to_text(item.get("abstract_inverted_index") or {})
            primary_location = item.get("primary_location") or {}
            source_obj = primary_location.get("source") or {}
            source = clean_text(source_obj.get("display_name", ""))
            doi = clean_text(item.get("doi", ""))
            papers.append(
                Paper(
                    title=title,
                    authors=authors or "Unknown authors",
                    date=publication_date,
                    source="OpenAlex",
                    url=item.get("doi") or item.get("id") or "",
                    abstract=abstract,
                    venue=source,
                    doi=doi,
                    cited_by_count=int(item.get("cited_by_count") or 0),
                )
            )
    return papers


def search_high_value_readings() -> list[Paper]:
    papers: list[Paper] = []
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    max_date = (datetime.now(timezone.utc) - timedelta(days=60)).date().isoformat()
    for query in HIGH_VALUE_READING_QUERIES:
        params = {
            "search": query,
            "filter": f"from_publication_date:2018-01-01,to_publication_date:{max_date}",
            "sort": "cited_by_count:desc",
            "per-page": "8",
        }
        if mailto:
            params["mailto"] = mailto
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"OpenAlex reading query failed for {query!r}: {exc}", file=sys.stderr)
            continue
        for item in data.get("results", []):
            title = clean_text(item.get("title", ""))
            if not title:
                continue
            publication_date = clean_text(item.get("publication_date", ""))
            if is_future_date(publication_date):
                continue
            authors = ", ".join(
                clean_text(a.get("author", {}).get("display_name", ""))
                for a in item.get("authorships", [])[:6]
                if a.get("author")
            )
            abstract = inverted_index_to_text(item.get("abstract_inverted_index") or {})
            primary_location = item.get("primary_location") or {}
            source_obj = primary_location.get("source") or {}
            source = clean_text(source_obj.get("display_name", ""))
            doi = clean_text(item.get("doi", ""))
            paper = Paper(
                title=title,
                authors=authors or "Unknown authors",
                date=publication_date,
                source="OpenAlex",
                url=item.get("doi") or item.get("id") or "",
                abstract=abstract,
                venue=source,
                doi=doi,
                cited_by_count=int(item.get("cited_by_count") or 0),
            )
            if classify(paper) == "Design Science Research" or score(paper) >= 30:
                papers.append(paper)
    return dedupe(papers)


def inverted_index_to_text(index: dict[str, list[int]]) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            words.append((pos, word))
    return clean_text(" ".join(word for _, word in sorted(words)))


def search_arxiv() -> list[Paper]:
    query = " OR ".join(f'all:"{topic}"' for topic in TOPICS[:6])
    params = {
        "search_query": query,
        "start": "0",
        "max_results": "20",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    try:
        text = fetch_text(url)
    except Exception as exc:
        print(f"arXiv query failed: {exc}", file=sys.stderr)
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(text)
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", ns):
        title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        abstract = clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
        authors = ", ".join(
            clean_text(a.findtext("atom:name", default="", namespaces=ns))
            for a in entry.findall("atom:author", ns)[:6]
        )
        published = clean_text(entry.findtext("atom:published", default="", namespaces=ns))[:10]
        link = clean_text(entry.findtext("atom:id", default="", namespaces=ns))
        if title:
            papers.append(Paper(title, authors or "Unknown authors", published, "arXiv", link, abstract, "arXiv"))
    return papers


def search_crossref() -> list[Paper]:
    papers: list[Paper] = []
    for topic in TOPICS[:7]:
        params = {
            "query.bibliographic": topic,
            "filter": f"from-pub-date:{recent_cutoff(30)}",
            "sort": "published",
            "order": "desc",
            "rows": "6",
        }
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"Crossref query failed for {topic!r}: {exc}", file=sys.stderr)
            continue
        for item in data.get("message", {}).get("items", []):
            title = clean_text(" ".join(item.get("title", [])[:1]))
            if not title:
                continue
            authors = ", ".join(
                clean_text(" ".join(filter(None, [a.get("given", ""), a.get("family", "")])))
                for a in item.get("author", [])[:6]
            )
            date_parts = (
                item.get("published-print", {})
                .get("date-parts")
                or item.get("published-online", {}).get("date-parts")
                or item.get("created", {}).get("date-parts")
                or [[]]
            )
            date = "-".join(str(x) for x in date_parts[0]) if date_parts and date_parts[0] else ""
            if is_future_date(date):
                continue
            venue = clean_text(" ".join(item.get("container-title", [])[:1]))
            doi = clean_text(item.get("DOI", ""))
            papers.append(
                Paper(
                    title=title,
                    authors=authors or "Unknown authors",
                    date=date,
                    source="Crossref",
                    url=f"https://doi.org/{doi}" if doi else clean_text(item.get("URL", "")),
                    abstract=clean_text(item.get("abstract", "")),
                    venue=venue,
                    doi=doi,
                )
            )
    return papers


def classify(paper: Paper) -> str:
    text = f"{paper.title} {paper.abstract} {paper.venue}".lower()
    if any(term in text for term in DSR_TERMS):
        return "Design Science Research"
    if any(term in text for term in BEHAVIORAL_TERMS):
        return "Behavioral / Organizational IS"
    if any(term in text for term in EMPIRICAL_TERMS):
        return "Adjacent Empirical IS"
    return "Other Relevant IS"


def score(paper: Paper) -> int:
    text = f"{paper.title} {paper.abstract} {paper.venue}".lower()
    value = 0
    value += 12 * sum(term in text for term in DSR_TERMS)
    value += 3 * sum(term in text for term in EMPIRICAL_TERMS)
    value += 3 * sum(term in text for term in BEHAVIORAL_TERMS)
    value += 10 * any(venue.lower() in text for venue in VENUES)
    value += 5 if paper.source == "OpenAlex" else 0
    return value


def dedupe(papers: Iterable[Paper]) -> list[Paper]:
    seen: set[str] = set()
    result: list[Paper] = []
    for paper in papers:
        key = re.sub(r"[^a-z0-9]+", "", paper.title.lower())[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(paper)
    return result


def summarize(abstract: str, limit: int = 420) -> str:
    abstract = clean_text(re.sub(r"<[^>]+>", " ", abstract))
    if not abstract:
        return "No abstract available from the source metadata."
    if len(abstract) <= limit:
        return abstract
    return abstract[:limit].rsplit(" ", 1)[0] + "..."


def build_markdown(papers: list[Paper], high_value_readings: list[Paper]) -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    groups = {
        "Design Science Research": [],
        "Adjacent Empirical IS": [],
        "Behavioral / Organizational IS": [],
        "Other Relevant IS": [],
    }
    for paper in sorted(papers, key=score, reverse=True):
        groups[classify(paper)].append(paper)

    limits = {
        "Design Science Research": 6,
        "Adjacent Empirical IS": 3,
        "Behavioral / Organizational IS": 3,
        "Other Relevant IS": 3,
    }
    lines = [
        f"# Daily IS Design Science Research Briefing",
        "",
        f"Generated: {now:%Y-%m-%d %H:%M} Asia/Shanghai",
        "",
    ]
    if not groups["Design Science Research"]:
        lines.extend(
            [
                "> No strong Design Science Research matches were found in today's metadata scan. "
                "The briefing is filled with adjacent IS papers with possible design implications.",
                "",
            ]
        )

    for group, items in groups.items():
        selected = items[: limits[group]]
        if not selected:
            continue
        lines.extend([f"## {group}", ""])
        for idx, paper in enumerate(selected, 1):
            lines.extend(
                [
                    f"### {idx}. {paper.title}",
                    "",
                    f"- Authors: {paper.authors}",
                    f"- Date: {paper.date or 'Unknown'}",
                    f"- Source: {paper.source}" + (f" / {paper.venue}" if paper.venue else ""),
                    f"- Link: {paper.url or 'No link available'}",
                    f"- DOI: {paper.doi or 'Not available'}",
                    f"- Method type: {classify(paper)}",
                    f"- Why it matters for DSR: {why_dsr(paper)}",
                    f"- Summary: {summarize(paper.abstract)}",
                    f"- Tags: {', '.join(tags_for(paper))}",
                    "",
                ]
            )

    lines.extend(["## Recent High-Value DSR Reading", ""])
    selected_readings = select_high_value_readings(groups, high_value_readings)
    if not selected_readings:
        lines.extend(
            [
                "No suitable recent high-value DSR readings were found in the metadata scan today.",
                "",
            ]
        )
    for idx, paper in enumerate(selected_readings, 1):
        lines.extend(
            [
                f"### {idx}. {paper.title}",
                "",
                f"- Authors: {paper.authors}",
                f"- Date: {paper.date or 'Unknown'}",
                f"- Source: {paper.source}" + (f" / {paper.venue}" if paper.venue else ""),
                f"- Link: {paper.url or 'No link available'}",
                f"- DOI: {paper.doi or 'Not available'}",
                f"- Citation signal: {paper.cited_by_count} OpenAlex citations",
                f"- Why it is worth reading now: {why_dsr(paper)}",
                f"- DSR lesson to extract: {reading_lesson(paper)}",
                f"- Connection to today's briefing: {reading_connection(paper, groups)}",
                f"- Summary: {summarize(paper.abstract)}",
                "",
            ]
        )

    lines.extend(["## Emerging Opportunities for DSR", ""])
    lines.extend(opportunities(groups))
    lines.extend(["", "## Recommended Reading Priority", ""])
    top = (groups["Design Science Research"] or sorted(papers, key=score, reverse=True))[:1]
    if top:
        lines.append(f"Read first: **{top[0].title}**")
    else:
        lines.append("No papers were retrieved today. Check source/API availability.")
    lines.append("")
    return "\n".join(lines)


def why_dsr(paper: Paper) -> str:
    text = f"{paper.title} {paper.abstract}".lower()
    if any(term in text for term in ["prototype", "artifact", "artefact", "tool", "system"]):
        return "It appears to involve an artifact, tool, prototype, or system that can inform build-and-evaluate DSR work."
    if any(term in text for term in ["design principle", "framework", "method", "design theory"]):
        return "It appears to contribute design knowledge, principles, frameworks, methods, or theory."
    if any(term in text for term in ["decision support", "human-ai", "generative ai", "platform"]):
        return "It points to a sociotechnical design setting where new IS artifacts or design principles may be developed."
    return "It is adjacent to IS design questions and may suggest artifact requirements, evaluation settings, or design implications."


def tags_for(paper: Paper) -> list[str]:
    text = f"{paper.title} {paper.abstract}".lower()
    candidates = {
        "DSR": DSR_TERMS,
        "AI": ["ai", "artificial intelligence", "generative ai", "machine learning", "algorithm"],
        "Human-AI": ["human-ai", "human ai", "collaboration", "trust"],
        "Platforms": ["platform", "ecosystem"],
        "Decision Support": ["decision support", "decision aid"],
        "Health IT": ["health", "clinical", "medical"],
        "Security/Privacy": ["privacy", "security", "cybersecurity"],
        "Empirical": EMPIRICAL_TERMS,
        "Behavioral": BEHAVIORAL_TERMS,
    }
    tags = [label for label, terms in candidates.items() if any(term in text for term in terms)]
    return tags[:6] or ["Information Systems"]


def opportunities(groups: dict[str, list[Paper]]) -> list[str]:
    all_text = " ".join(p.title + " " + p.abstract for papers in groups.values() for p in papers).lower()
    ideas = []
    if "generative ai" in all_text or "large language model" in all_text:
        ideas.append("- Design and evaluate organizational GenAI artifacts with explicit human oversight, task fit, and governance mechanisms.")
    if "privacy" in all_text or "security" in all_text:
        ideas.append("- Build privacy/security decision aids that translate technical risk signals into managerially actionable interventions.")
    if "platform" in all_text:
        ideas.append("- Develop design principles for platform governance artifacts that balance complementor autonomy, data access, and ecosystem control.")
    if "health" in all_text or "clinical" in all_text:
        ideas.append("- Instantiate health IT artifacts that integrate workflow fit, explainability, and longitudinal evaluation in real clinical settings.")
    while len(ideas) < 3:
        ideas.append("- Convert adjacent empirical findings into testable design requirements, then evaluate artifact utility in field or simulation settings.")
    return ideas[:3]


def select_high_value_readings(
    groups: dict[str, list[Paper]], readings: list[Paper], count: int = 3
) -> list[Paper]:
    briefing_text = " ".join(
        paper.title + " " + paper.abstract + " " + paper.venue
        for papers in groups.values()
        for paper in papers[:6]
    ).lower()
    scored: list[tuple[int, Paper]] = []
    for paper in readings:
        text = f"{paper.title} {paper.abstract} {paper.venue}".lower()
        overlap = sum(term in briefing_text and term in text for term in [*DSR_TERMS, *BEHAVIORAL_TERMS])
        citation_signal = min(paper.cited_by_count // 25, 12)
        recency_signal = 4 if paper.date >= "2021" else 2
        scored.append((score(paper) + overlap * 6 + citation_signal + recency_signal, paper))
    ranked = [paper for _, paper in sorted(scored, key=lambda item: item[0], reverse=True)]
    return ranked[:count]


def reading_connection(paper: Paper, groups: dict[str, list[Paper]]) -> str:
    tags = [tag.lower() for tag in tags_for(paper)]
    recent = [
        item
        for papers in groups.values()
        for item in papers[:4]
        if any(tag in f"{item.title} {item.abstract}".lower() for tag in tags)
    ]
    if recent:
        return f"Most relevant to: {recent[0].title}"
    return "Use it as a recent benchmark for framing artifact novelty, evaluation, and design knowledge in today's DSR opportunities."


def reading_lesson(paper: Paper) -> str:
    text = f"{paper.title} {paper.abstract}".lower()
    if "design principle" in text or "design theory" in text:
        return "Study how the paper converts problem context and evaluation evidence into reusable design principles or design theory."
    if "prototype" in text or "artifact" in text or "tool" in text:
        return "Study how the artifact is scoped, instantiated, evaluated, and connected back to IS knowledge contribution."
    if "human-ai" in text or "generative ai" in text or "artificial intelligence" in text:
        return "Study how AI capability is translated into a sociotechnical artifact rather than treated as a standalone model."
    if "platform" in text:
        return "Study how platform rules, complements, governance, and user behavior become design variables."
    return "Study the paper as a recent example of turning IS problems into design requirements, evaluation criteria, and reusable design knowledge."


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
    message["Subject"] = f"Daily IS Design Science Briefing - {today}"
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
    papers = dedupe([*search_openalex(), *search_arxiv(), *search_crossref()])
    high_value_readings = search_high_value_readings()
    markdown = build_markdown(papers, high_value_readings)
    print(markdown)
    send_email(markdown)


if __name__ == "__main__":
    main()
