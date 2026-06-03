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


NOTABLE_AUTHORS = [
    "Yoshua Bengio",
    "Yann LeCun",
    "Geoffrey Hinton",
    "Ilya Sutskever",
    "Fei-Fei Li",
    "Percy Liang",
    "Dawn Song",
    "Pieter Abbeel",
    "Chelsea Finn",
    "Christopher Manning",
    "Danqi Chen",
    "Diyi Yang",
    "Tatsunori Hashimoto",
    "Jacob Steinhardt",
    "Sergey Levine",
    "Pieter Abbeel",
]

NOTABLE_LABS = [
    "OpenAI",
    "DeepMind",
    "Google Research",
    "Google DeepMind",
    "Anthropic",
    "Meta AI",
    "Microsoft Research",
    "NVIDIA",
    "Apple",
    "Stanford",
    "MIT",
    "Berkeley",
    "CMU",
    "Princeton",
    "Tsinghua",
    "Peking University",
    "Shanghai AI Lab",
]

FRESH_ARXIV_QUERIES = [
    'cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.CV',
    'all:"large language model" OR all:"LLM" OR all:"foundation model"',
    'all:"agent" OR all:"tool use" OR all:"reasoning"',
    'all:"multimodal" OR all:"vision-language"',
    'all:"small language model" OR all:"distillation" OR all:"quantization"',
]

TRENDING_QUERIES = [
    "large language models reasoning",
    "language model agents tool use",
    "multimodal foundation models",
    "small language models efficient inference",
    "retrieval augmented generation evaluation",
    "AI alignment safety evaluation",
    "AI for science foundation models",
    "robotics vision language action model",
]

SERIES = [
    {
        "name": "GNN",
        "queries": ["graph neural networks", "graph representation learning", "graph foundation models"],
    },
    {
        "name": "RL",
        "queries": ["reinforcement learning", "offline reinforcement learning", "reinforcement learning from human feedback"],
    },
    {
        "name": "LLM",
        "queries": ["large language models", "transformer language models", "instruction tuning language models"],
    },
    {
        "name": "RAG",
        "queries": ["retrieval augmented generation", "dense retrieval language models", "retrieval language model"],
    },
    {
        "name": "Agents",
        "queries": ["language model agents", "tool use language models", "AI agents planning"],
    },
    {
        "name": "Multimodal",
        "queries": ["vision language models", "multimodal large language models", "video language models"],
    },
    {
        "name": "Efficient Models",
        "queries": ["model compression distillation quantization", "small language models", "efficient inference language models"],
    },
    {
        "name": "Alignment and Evaluation",
        "queries": ["AI alignment evaluation", "language model safety evaluation", "red teaming language models"],
    },
]

HOT_TERMS = [
    "reasoning",
    "agent",
    "tool use",
    "multimodal",
    "vision-language",
    "small language model",
    "distillation",
    "quantization",
    "alignment",
    "evaluation",
    "retrieval",
    "rag",
    "long context",
    "post-training",
    "reinforcement learning",
    "diffusion",
    "robotics",
    "ai for science",
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


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def is_future_date(value: str) -> bool:
    return bool(value and value[:10] > today_utc())


def fetch_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "daily-ai-paper-briefing/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "daily-ai-paper-briefing/2.0"})
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
    institutions = " ".join(
        clean_text(inst.get("display_name", ""))
        for author in item.get("authorships", [])[:10]
        for inst in author.get("institutions", [])[:2]
    )
    primary_location = item.get("primary_location") or {}
    source_obj = primary_location.get("source") or {}
    venue = clean_text(source_obj.get("display_name", ""))
    abstract = inverted_index_to_text(item.get("abstract_inverted_index") or {})
    if institutions:
        abstract = f"{abstract} Institutions: {institutions}"
    doi = clean_text(item.get("doi", ""))
    return Paper(
        title=title,
        authors=authors or "Unknown authors",
        date=date,
        source="OpenAlex",
        url=doi or item.get("id") or "",
        abstract=abstract,
        venue=venue,
        doi=doi,
        cited_by_count=int(item.get("cited_by_count") or 0),
        module_hint=module_hint,
    )


def search_openalex(
    query: str,
    from_date: str,
    sort: str = "publication_date:desc",
    per_page: int = 10,
    module_hint: str = "",
) -> list[Paper]:
    params = {
        "search": query,
        "filter": f"from_publication_date:{from_date}",
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


def search_arxiv() -> list[Paper]:
    papers: list[Paper] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for query in FRESH_ARXIV_QUERIES:
        params = {
            "search_query": query,
            "start": "0",
            "max_results": "25",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
        try:
            text = fetch_text(url)
        except Exception as exc:
            print(f"arXiv query failed for {query!r}: {exc}", file=sys.stderr)
            continue
        root = ET.fromstring(text)
        for entry in root.findall("atom:entry", ns):
            title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
            date = clean_text(entry.findtext("atom:published", default="", namespaces=ns))[:10]
            if not title or is_future_date(date):
                continue
            abstract = clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
            authors = ", ".join(
                clean_text(author.findtext("atom:name", default="", namespaces=ns))
                for author in entry.findall("atom:author", ns)[:6]
            )
            url = clean_text(entry.findtext("atom:id", default="", namespaces=ns))
            papers.append(Paper(title, authors or "Unknown authors", date, "arXiv", url, abstract, "arXiv", module_hint="Fresh arXiv"))
    return dedupe(papers)


def search_trending() -> list[Paper]:
    papers: list[Paper] = []
    for query in TRENDING_QUERIES:
        papers.extend(search_openalex(query, cutoff(180), sort="cited_by_count:desc", per_page=10, module_hint="Trending"))
    return [paper for paper in dedupe(papers) if paper.cited_by_count > 0]


def search_notable_authors_labs() -> list[Paper]:
    papers: list[Paper] = []
    for author in NOTABLE_AUTHORS:
        papers.extend(search_openalex(f"{author} artificial intelligence", cutoff(365), per_page=5, module_hint="Notable author/lab"))
    for lab in NOTABLE_LABS:
        papers.extend(search_openalex(f"{lab} artificial intelligence", cutoff(365), per_page=5, module_hint="Notable author/lab"))
    return dedupe(papers)


def daily_series() -> dict[str, object]:
    index = datetime.now(timezone(timedelta(hours=8))).toordinal() % len(SERIES)
    return SERIES[index]


def search_series_reading(series: dict[str, object]) -> list[Paper]:
    papers: list[Paper] = []
    for query in series["queries"]:
        papers.extend(search_openalex(query, "2012-01-01", sort="cited_by_count:desc", per_page=12, module_hint=f"{series['name']} series"))
        papers.extend(search_openalex(query, "2022-01-01", sort="cited_by_count:desc", per_page=8, module_hint=f"{series['name']} frontier"))
    return [paper for paper in dedupe(papers) if paper.cited_by_count >= 50]


def text_of(paper: Paper) -> str:
    return f"{paper.title} {paper.abstract} {paper.venue} {paper.authors}".lower()


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)


def quality_signal(paper: Paper, fresh: bool = False) -> str:
    text = text_of(paper)
    reasons = []
    if contains_any(text, NOTABLE_AUTHORS):
        reasons.append("notable author")
    if contains_any(text, NOTABLE_LABS):
        reasons.append("major lab/company")
    if not fresh and paper.cited_by_count:
        reasons.append(f"{paper.cited_by_count} citations")
    if contains_any(text, HOT_TERMS):
        reasons.append("hot topic")
    return ", ".join(reasons[:3]) or "metadata-level relevance; verify full paper"


def keywords(paper: Paper) -> list[str]:
    text = text_of(paper)
    candidates = {
        "LLM": ["large language model", "llm", "language model"],
        "Small model": ["small language model", "distillation", "quantization", "compression"],
        "Agent": ["agent", "tool use", "planning"],
        "Reasoning": ["reasoning", "test-time", "test time"],
        "Multimodal": ["multimodal", "vision-language", "video", "image"],
        "RAG": ["retrieval", "rag", "memory"],
        "Safety/eval": ["safety", "alignment", "evaluation", "benchmark", "red teaming"],
        "RL": ["reinforcement learning", "rlhf", "policy"],
        "GNN": ["graph neural", "graph representation", "gnn"],
        "AI4Science": ["science", "scientific", "biology", "chemistry"],
        "Robotics": ["robot", "robotics"],
    }
    tags = [label for label, terms in candidates.items() if contains_any(text, terms)]
    return tags[:6] or ["AI"]


def abstract_short(paper: Paper, limit: int = 650) -> str:
    abstract = clean_text(re.sub(r"<[^>]+>", " ", paper.abstract))
    if not abstract:
        return "No abstract in metadata."
    if len(abstract) <= limit:
        return abstract
    return abstract[:limit].rsplit(" ", 1)[0] + "..."


def method_summary(paper: Paper) -> str:
    text = text_of(paper)
    if "small language model" in text or "distillation" in text or "quantization" in text:
        return "Develops or evaluates efficient-model methods such as distillation, quantization, compression, or small-model deployment."
    if "agent" in text or "tool use" in text:
        return "Builds or evaluates agentic workflows involving planning, tool use, multi-step reasoning, autonomy, or reliability mechanisms."
    if "multimodal" in text or "vision-language" in text:
        return "Uses multimodal modeling, usually combining vision/language/video inputs, to improve understanding, generation, or reasoning."
    if "retrieval" in text or "rag" in text:
        return "Uses retrieval, memory, or external knowledge mechanisms to ground model outputs or improve factual/task performance."
    if "alignment" in text or "safety" in text or "evaluation" in text:
        return "Designs evaluation, alignment, reward-modeling, red-teaming, or safety methods for measuring and improving model behavior."
    if "reinforcement learning" in text or "rlhf" in text:
        return "Uses reinforcement learning or preference-optimization methods to improve policies, agents, or model behavior."
    if "benchmark" in text or "dataset" in text:
        return "Introduces or uses a benchmark/dataset to evaluate model capability, robustness, or task performance."
    if "graph" in text:
        return "Uses graph representation learning, message passing, or graph-based modeling to capture relational structure."
    if "large language model" in text or "foundation model" in text:
        return "Trains, adapts, evaluates, or analyzes foundation models/LLMs for a specific capability or task setting."
    return "Studies an AI method, benchmark, or system using the approach described in the title and abstract metadata."


def score_fresh(paper: Paper) -> int:
    text = text_of(paper)
    return (
        25 * contains_any(text, NOTABLE_LABS)
        + 20 * contains_any(text, NOTABLE_AUTHORS)
        + 8 * sum(term.lower() in text for term in HOT_TERMS)
        + 10 * (paper.date >= cutoff(3))
    )


def score_cited(paper: Paper) -> int:
    text = text_of(paper)
    return min(paper.cited_by_count // 10, 40) + 12 * contains_any(text, NOTABLE_LABS) + 8 * sum(term.lower() in text for term in HOT_TERMS)


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


def paper_block(paper: Paper, fresh: bool = False, include_citations: bool = True) -> list[str]:
    lines = [
        f"### {paper.title}",
        f"- Authors: {paper.authors}",
        f"- Date: {paper.date or 'Unknown'}",
        f"- Link: {paper.url or 'No link available'}",
    ]
    if include_citations:
        lines.append(f"- Citation signal: {paper.cited_by_count} OpenAlex citations")
    lines.extend(
        [
            f"- Abstract: {abstract_short(paper)}",
            f"- Keywords: {', '.join(keywords(paper))}",
            f"- Method: {method_summary(paper)}",
            f"- Quality signal: {quality_signal(paper, fresh=fresh)}",
            "",
        ]
    )
    return lines


def topic_summary(sections: dict[str, list[Paper]], series_name: str) -> list[str]:
    all_papers = [paper for papers in sections.values() for paper in papers]
    text = " ".join(text_of(paper) for paper in all_papers)
    lines = []
    if "agent" in text:
        lines.append("- Agents remain a strong topic source: look for reliability, monitoring, evaluation, and human oversight gaps.")
    if "small language model" in text or "distillation" in text:
        lines.append("- Small-model work is useful for deployable topics: cost, privacy, edge constraints, and specialized organizational tasks.")
    if "multimodal" in text or "vision-language" in text:
        lines.append("- Multimodal work suggests richer artifact/interface topics, but evaluation quality matters more than demo quality.")
    if "retrieval" in text or "rag" in text:
        lines.append("- RAG/memory papers can become topics around provenance, trust calibration, and organizational knowledge decay.")
    lines.append(f"- Today's series is {series_name}; use it to build background depth rather than only chasing new arXiv papers.")
    return lines[:5]


def build_markdown() -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    fresh = sorted(search_arxiv(), key=score_fresh, reverse=True)[:10]
    trending = sorted(search_trending(), key=score_cited, reverse=True)[:8]
    notable = sorted(search_notable_authors_labs(), key=score_cited, reverse=True)[:8]
    series = daily_series()
    series_papers = sorted(search_series_reading(series), key=score_cited, reverse=True)[:10]

    sections = {
        "Fresh arXiv": fresh,
        "Trending": trending,
        "Notable author/lab": notable,
        f"{series['name']} series": series_papers,
    }

    lines = [
        "# Daily AI Paper Briefing",
        f"Generated: {now:%Y-%m-%d %H:%M} Asia/Shanghai",
        "",
        "## 1. Fresh arXiv",
        "",
    ]
    for paper in fresh:
        lines.extend(paper_block(paper, fresh=True, include_citations=False))

    lines.extend(["## 2. Trending Recent Papers / Topics", ""])
    for paper in trending:
        lines.extend(paper_block(paper))

    lines.extend(["## 3. Notable Author / Lab Papers", ""])
    for paper in notable:
        lines.extend(paper_block(paper))

    lines.extend([f"## 4. Daily Series: {series['name']} Must-Reads", ""])
    if series_papers:
        for paper in series_papers:
            lines.extend(paper_block(paper))
    else:
        lines.extend(["No sufficiently cited series papers found today.", ""])

    lines.extend(["## Highlight Summary", ""])
    lines.extend(topic_summary(sections, str(series["name"])))
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
