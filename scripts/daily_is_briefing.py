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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Iterable


FIRST_TIER_JOURNALS = [
    "MIS Quarterly",
    "Information Systems Research",
    "Management Science",
]

SECOND_TIER_JOURNALS = [
    "Production and Operations Management",
    "Journal of Management Information Systems",
    "Journal of Operations Management",
    "Journal of the Association for Information Systems",
    "Decision Support Systems",
    "Information & Management",
    "European Journal of Information Systems",
    "Information Systems Journal",
]

IS_CONFERENCES = [
    "International Conference on Information Systems",
    "European Conference on Information Systems",
    "Pacific Asia Conference on Information Systems",
    "Hawaii International Conference on System Sciences",
    "Americas Conference on Information Systems",
    "Conference on Information Systems and Technology",
    "Workshop on Information Systems and Economics",
]

DAILY_IS_QUERIES = [
    *FIRST_TIER_JOURNALS,
    *SECOND_TIER_JOURNALS,
    *IS_CONFERENCES,
    "information systems digital transformation",
    "information systems artificial intelligence",
    "information systems platform",
    "information systems decision support",
]

DSR_AI_QUERIES = [
    "design science artificial intelligence information systems",
    "machine learning decision support information systems",
    "deep learning decision support system information systems",
    "AI artifact design science information systems",
    "human AI collaboration design science information systems",
    "generative AI artifact information systems",
    "data analytics artifact design science information systems",
    "algorithmic decision support design science information systems",
    "health information technology AI design science",
    "cybersecurity privacy AI tool design science information systems",
]

DSR_AI_CONFERENCE_QUERIES = [
    f"{conference} artificial intelligence design science"
    for conference in IS_CONFERENCES
] + [
    f"{conference} machine learning decision support"
    for conference in IS_CONFERENCES
]

AI_ML_TERMS = [
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "large language model",
    "generative ai",
    "algorithm",
    "analytics",
    "neural",
    "prediction",
    "classification",
    "recommendation",
    "decision support",
]

DSR_TERMS = [
    "design science",
    "artifact",
    "artefact",
    "prototype",
    "design principle",
    "design theory",
    "design evaluation",
    "action design research",
    "build and evaluate",
    "instantiation",
    "tool",
    "system",
    "framework",
]

BEHAVIORAL_TERMS = [
    "behavior",
    "behaviour",
    "adoption",
    "trust",
    "acceptance",
    "user",
    "intention",
    "survey",
    "experiment",
]

MODELING_TERMS = [
    "model",
    "optimization",
    "simulation",
    "econometric",
    "causal",
    "regression",
    "panel data",
    "structural",
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
    module_hint: str = ""


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def years_ago(years: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=365 * years)).date().isoformat()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def is_future_date(value: str) -> bool:
    return bool(value and value[:10] > today_utc())


def fetch_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "is-research-briefing/2.0"})
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


def paper_from_openalex(item: dict, module_hint: str) -> Paper | None:
    title = clean_text(item.get("title", ""))
    date = clean_text(item.get("publication_date", ""))
    if not title or is_future_date(date):
        return None

    authors = ", ".join(
        clean_text(author.get("author", {}).get("display_name", ""))
        for author in item.get("authorships", [])[:6]
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
        url=doi or item.get("id") or "",
        abstract=inverted_index_to_text(item.get("abstract_inverted_index") or {}),
        venue=venue,
        doi=doi,
        cited_by_count=int(item.get("cited_by_count") or 0),
        module_hint=module_hint,
    )


def search_openalex(
    query: str,
    from_date: str,
    to_date: str | None = None,
    sort: str = "publication_date:desc",
    per_page: int = 10,
    module_hint: str = "",
) -> list[Paper]:
    filters = [f"from_publication_date:{from_date}"]
    if to_date:
        filters.append(f"to_publication_date:{to_date}")
    params = {
        "search": query,
        "filter": ",".join(filters),
        "sort": sort,
        "per-page": str(per_page),
    }
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    try:
        data = fetch_json(url)
    except Exception as exc:
        print(f"OpenAlex query failed for {query!r}: {exc}", file=sys.stderr)
        return []
    papers = [paper_from_openalex(item, module_hint) for item in data.get("results", [])]
    return [paper for paper in papers if paper]


def search_daily_is() -> list[Paper]:
    papers: list[Paper] = []
    for query in DAILY_IS_QUERIES:
        papers.extend(search_openalex(query, cutoff(21), per_page=6, module_hint="Latest IS papers"))
    return filter_relevant_is(dedupe(papers))


def search_recent_high_value_dsr_ai() -> list[Paper]:
    papers: list[Paper] = []
    for query in DSR_AI_QUERIES:
        papers.extend(
            search_openalex(
                query,
                years_ago(3),
                sort="cited_by_count:desc",
                per_page=12,
                module_hint="Recent high-value DSR + AI/ML",
            )
        )
    return [
        paper
        for paper in dedupe(papers)
        if is_ai_dsr(paper) and venue_priority(paper.venue) > 0
    ]


def search_recent_conference_dsr_ai() -> list[Paper]:
    papers: list[Paper] = []
    for query in DSR_AI_CONFERENCE_QUERIES:
        papers.extend(
            search_openalex(
                query,
                cutoff(90),
                sort="publication_date:desc",
                per_page=8,
                module_hint="Recent IS conference DSR + AI/ML",
            )
        )
    return [
        paper
        for paper in dedupe(papers)
        if is_ai_dsr(paper) and is_conference_like(paper)
    ]


def filter_relevant_is(papers: list[Paper]) -> list[Paper]:
    filtered = []
    for paper in papers:
        text = paper_text(paper)
        if venue_priority(paper.venue) > 0 or is_conference_like(paper) or "information systems" in text:
            filtered.append(paper)
    return filtered


def paper_text(paper: Paper) -> str:
    return f"{paper.title} {paper.abstract} {paper.venue}".lower()


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)


def is_ai_dsr(paper: Paper) -> bool:
    text = paper_text(paper)
    return contains_any(text, AI_ML_TERMS) and (
        contains_any(text, DSR_TERMS)
        or "decision support" in text
        or "practical" in text
        or "application" in text
    )


def venue_priority(venue: str) -> int:
    lowered = venue.lower()
    if any(name.lower() in lowered for name in FIRST_TIER_JOURNALS):
        return 4
    if any(name.lower() in lowered for name in SECOND_TIER_JOURNALS):
        return 3
    if any(name.lower() in lowered for name in IS_CONFERENCES):
        return 2
    return 0


def is_conference_like(paper: Paper) -> bool:
    text = f"{paper.venue} {paper.title}".lower()
    return any(name.lower() in text for name in IS_CONFERENCES) or "conference" in text or "proceedings" in text


def classify_domain(paper: Paper) -> str:
    text = paper_text(paper)
    labels = []
    if contains_any(text, DSR_TERMS):
        labels.append("design")
    if contains_any(text, AI_ML_TERMS):
        labels.append("ai/ml")
    if contains_any(text, MODELING_TERMS):
        labels.append("modeling")
    if contains_any(text, BEHAVIORAL_TERMS):
        labels.append("behavioral")
    if "platform" in text:
        labels.append("platform")
    if "health" in text or "clinical" in text:
        labels.append("health it")
    if "security" in text or "privacy" in text or "cyber" in text:
        labels.append("security/privacy")
    return ", ".join(dict.fromkeys(labels)) or "general IS"


def keywords(paper: Paper) -> list[str]:
    text = paper_text(paper)
    candidates = {
        "DSR": DSR_TERMS,
        "AI/ML": AI_ML_TERMS,
        "Modeling": MODELING_TERMS,
        "Behavioral": BEHAVIORAL_TERMS,
        "Decision support": ["decision support", "decision aid"],
        "Platform": ["platform", "ecosystem"],
        "Health IT": ["health", "clinical", "medical"],
        "Security/privacy": ["security", "privacy", "cybersecurity"],
    }
    tags = [label for label, terms in candidates.items() if contains_any(text, terms)]
    return tags[:6] or ["Information Systems"]


def abstract_short(paper: Paper, limit: int = 320) -> str:
    abstract = clean_text(re.sub(r"<[^>]+>", " ", paper.abstract))
    if not abstract:
        return "No abstract in metadata."
    if len(abstract) <= limit:
        return abstract
    return abstract[:limit].rsplit(" ", 1)[0] + "..."


def novelty(paper: Paper) -> str:
    text = paper_text(paper)
    if "action design research" in text:
        return "Action-design study linking artifact building with real organizational use."
    if "generative ai" in text or "large language model" in text:
        return "Applies GenAI/LLM capability to an IS artifact, workflow, or decision setting."
    if "machine learning" in text or "deep learning" in text:
        return "Uses ML/DL to solve an applied organizational or decision problem."
    if "design principle" in text or "design theory" in text:
        return "Attempts to extract reusable design knowledge rather than only report effects."
    if "platform" in text:
        return "Connects digital platform design/governance to IS outcomes."
    return "Potentially useful IS contribution; verify novelty from full text."


def limitation(paper: Paper) -> str:
    text = paper_text(paper)
    if "survey" in text or "interview" in text:
        return "Likely context- and sample-dependent; check external validity."
    if "case study" in text or "action design" in text:
        return "Likely strong context fit but limited generalizability; check evaluation depth."
    if "model" in text or "algorithm" in text or "machine learning" in text:
        return "Check data scope, baseline choice, deployment realism, and robustness."
    if not paper.abstract:
        return "Metadata is thin; full text needed before judging contribution."
    return "Full-text reading needed for causal claims, evaluation strength, and boundary conditions."


def score_daily(paper: Paper) -> int:
    return venue_priority(paper.venue) * 20 + min(paper.cited_by_count // 10, 15) + len(set(keywords(paper))) * 2


def score_dsr_ai(paper: Paper) -> int:
    text = paper_text(paper)
    return (
        venue_priority(paper.venue) * 30
        + min(paper.cited_by_count // 20, 25)
        + 15 * contains_any(text, AI_ML_TERMS)
        + 12 * contains_any(text, DSR_TERMS)
        + 8 * ("decision support" in text or "application" in text)
    )


def dedupe(papers: Iterable[Paper]) -> list[Paper]:
    seen: set[str] = set()
    result: list[Paper] = []
    for paper in papers:
        key = re.sub(r"[^a-z0-9]+", "", paper.title.lower())[:140]
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(paper)
    return result


def paper_block(paper: Paper, include_domain: bool = False, include_citations: bool = False) -> list[str]:
    lines = [
        f"### {paper.title}",
        f"- Authors: {paper.authors}",
        f"- Date: {paper.date or 'Unknown'}",
        f"- Venue/source: {paper.venue or paper.source}",
        f"- Link: {paper.url or 'No link available'}",
    ]
    if include_domain:
        lines.append(f"- Field: {classify_domain(paper)}")
    if include_citations:
        lines.append(f"- Citation signal: {paper.cited_by_count} OpenAlex citations")
    lines.extend(
        [
            f"- Abstract: {abstract_short(paper)}",
            f"- Keywords: {', '.join(keywords(paper))}",
            f"- Novelty / highlight: {novelty(paper)}",
            f"- Limitation: {limitation(paper)}",
            "",
        ]
    )
    return lines


def highlight_summary(sections: dict[str, list[Paper]]) -> list[str]:
    all_papers = [paper for papers in sections.values() for paper in papers]
    text = " ".join(paper_text(paper) for paper in all_papers)
    lines = []
    if "generative ai" in text or "large language model" in text:
        lines.append("- GenAI/LLM is the strongest current bridge into DSR: artifact design, workflow redesign, and human oversight are recurring angles.")
    if "decision support" in text or "machine learning" in text or "deep learning" in text:
        lines.append("- Applied ML/DL decision support remains the most relevant lane for your preference: look for papers with real deployment or field evaluation.")
    if "platform" in text:
        lines.append("- Platform papers can generate design-principle topics around governance, complementors, and AI-enabled coordination.")
    if "health" in text or "security" in text or "privacy" in text:
        lines.append("- Health/security/privacy settings offer concrete problem contexts where DSR evaluation can be stronger than generic tool-building.")
    while len(lines) < 3:
        lines.append("- Best topic candidates are papers that combine artifact building, AI/ML capability, and credible field or organizational evaluation.")
    return lines[:4]


def build_markdown() -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    latest = sorted(search_daily_is(), key=score_daily, reverse=True)[:10]
    high_value = sorted(search_recent_high_value_dsr_ai(), key=score_dsr_ai, reverse=True)[:8]
    conferences = sorted(search_recent_conference_dsr_ai(), key=score_dsr_ai, reverse=True)[:10]

    sections = {
        "Latest IS papers": latest,
        "Recent high-value DSR + AI/ML papers": high_value,
        "Recent IS conference DSR + AI/ML papers": conferences,
    }

    lines = [
        "# Daily IS Paper Briefing",
        f"Generated: {now:%Y-%m-%d %H:%M} Asia/Shanghai",
        "",
    ]

    if latest:
        lines.extend(["## 1. Latest IS Papers", ""])
        for paper in latest:
            lines.extend(paper_block(paper, include_domain=True))

    lines.extend(["## 2. Recent High-Value DSR + AI/ML Papers", ""])
    if high_value:
        for paper in high_value:
            lines.extend(paper_block(paper, include_citations=True))
    else:
        lines.extend(["No strong matches found today.", ""])

    lines.extend(["## 3. Recent IS Conference DSR + AI/ML Papers", ""])
    if conferences:
        for paper in conferences:
            lines.extend(paper_block(paper, include_citations=True))
    else:
        lines.extend(["No strong conference matches found in the last three months.", ""])

    lines.extend(["## Highlight Summary", ""])
    lines.extend(highlight_summary(sections))
    lines.append("")
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
    message["Subject"] = f"Daily IS Paper Briefing - {today}"
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
