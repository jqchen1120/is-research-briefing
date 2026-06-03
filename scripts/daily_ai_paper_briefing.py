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


TOPIC_QUERIES = {
    "Large Models / Foundation Models": [
        "large language models reasoning",
        "foundation models training post-training",
        "mixture of experts large language model",
        "long context large language models",
    ],
    "Small Models / Efficient AI": [
        "small language models efficient reasoning",
        "model compression distillation quantization",
        "parameter efficient fine tuning language models",
        "on device language model efficient inference",
    ],
    "Agents / Tool Use / Reasoning": [
        "language model agents tool use planning",
        "LLM agents reasoning evaluation",
        "agentic workflows large language models",
        "test time compute reasoning language models",
    ],
    "Multimodal / Vision-Language": [
        "multimodal large language models",
        "vision language model reasoning",
        "video language model understanding",
        "image generation diffusion transformer",
    ],
    "RAG / Memory / Knowledge": [
        "retrieval augmented generation evaluation",
        "long term memory language model agents",
        "knowledge editing large language models",
        "semantic retrieval language models",
    ],
    "Alignment / Safety / Evaluation": [
        "large language model alignment safety evaluation",
        "red teaming large language models",
        "AI evaluation benchmark reasoning",
        "reward models preference optimization",
    ],
    "AI for Science / Code / Robotics": [
        "AI for science foundation models",
        "code generation large language models",
        "robotics foundation models vision language action",
        "scientific discovery language models",
    ],
}

AUTHOR_QUERIES = [
    "Yoshua Bengio AI",
    "Yann LeCun AI",
    "Geoffrey Hinton AI",
    "Ilya Sutskever AI",
    "Fei-Fei Li AI",
    "Pieter Abbeel AI",
    "Percy Liang language models",
    "Dawn Song AI security",
    "Chelsea Finn robotics learning",
    "Andrej Karpathy language models",
    "Christopher Manning language models",
    "Diyi Yang language models",
    "Danqi Chen retrieval language models",
    "Tatsunori Hashimoto language models",
    "Jacob Steinhardt AI alignment",
]

ORG_TERMS = [
    "OpenAI",
    "DeepMind",
    "Google Research",
    "Anthropic",
    "Meta AI",
    "Microsoft Research",
    "NVIDIA",
    "Apple",
    "Stanford",
    "MIT",
    "Berkeley",
    "CMU",
    "Tsinghua",
    "Peking University",
    "Shanghai AI Lab",
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
    "RAG",
    "retrieval",
    "long context",
    "post-training",
    "reinforcement learning",
    "diffusion",
    "robotics",
    "AI for science",
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


def fetch_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "daily-ai-paper-briefing/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "daily-ai-paper-briefing/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def is_future_date(value: str) -> bool:
    return bool(value and value[:10] > datetime.now(timezone.utc).date().isoformat())


def inverted_index_to_text(index: dict[str, list[int]]) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            words.append((pos, word))
    return clean_text(" ".join(word for _, word in sorted(words)))


def search_openalex_topic(module: str, query: str, days: int = 21, per_page: int = 8) -> list[Paper]:
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    params = {
        "search": query,
        "filter": f"from_publication_date:{cutoff(days)}",
        "sort": "publication_date:desc",
        "per-page": str(per_page),
    }
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    try:
        data = fetch_json(url)
    except Exception as exc:
        print(f"OpenAlex query failed for {query!r}: {exc}", file=sys.stderr)
        return []
    return [
        paper_from_openalex(item, module)
        for item in data.get("results", [])
        if item.get("title") and not is_future_date(clean_text(item.get("publication_date", "")))
    ]


def search_openalex_hot(days: int = 180) -> list[Paper]:
    papers: list[Paper] = []
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    for query in ["artificial intelligence", "large language models", "machine learning"]:
        params = {
            "search": query,
            "filter": f"from_publication_date:{cutoff(days)}",
            "sort": "cited_by_count:desc",
            "per-page": "12",
        }
        if mailto:
            params["mailto"] = mailto
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"OpenAlex hot query failed for {query!r}: {exc}", file=sys.stderr)
            continue
        papers.extend(
            paper_from_openalex(item, "Trending / Highly Cited Recent")
            for item in data.get("results", [])
            if item.get("title") and not is_future_date(clean_text(item.get("publication_date", "")))
        )
    return papers


def search_openalex_authors(days: int = 365) -> list[Paper]:
    papers: list[Paper] = []
    for query in AUTHOR_QUERIES:
        papers.extend(search_openalex_topic("Notable Authors / Labs", query, days=days, per_page=4))
    return papers


def paper_from_openalex(item: dict, module: str) -> Paper:
    publication_date = clean_text(item.get("publication_date", ""))
    authors = ", ".join(
        clean_text(a.get("author", {}).get("display_name", ""))
        for a in item.get("authorships", [])[:6]
        if a.get("author")
    )
    institutions = " ".join(
        clean_text(i.get("display_name", ""))
        for a in item.get("authorships", [])[:8]
        for i in a.get("institutions", [])[:2]
    )
    primary_location = item.get("primary_location") or {}
    source_obj = primary_location.get("source") or {}
    source = clean_text(source_obj.get("display_name", ""))
    abstract = inverted_index_to_text(item.get("abstract_inverted_index") or {})
    if institutions:
        abstract = f"{abstract} Institutions: {institutions}"
    doi = clean_text(item.get("doi", ""))
    return Paper(
        title=clean_text(item.get("title", "")),
        authors=authors or "Unknown authors",
        date=publication_date,
        source="OpenAlex",
        url=item.get("doi") or item.get("id") or "",
        abstract=abstract,
        venue=source,
        doi=doi,
        cited_by_count=int(item.get("cited_by_count") or 0),
        module_hint=module,
    )


def search_arxiv() -> list[Paper]:
    queries = [
        'cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.CV',
        'all:"large language model" OR all:"language model agents" OR all:"multimodal"',
        'all:"small language model" OR all:"model compression" OR all:"quantization"',
    ]
    papers: list[Paper] = []
    for query in queries:
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
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(text)
        for entry in root.findall("atom:entry", ns):
            title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
            abstract = clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
            authors = ", ".join(
                clean_text(a.findtext("atom:name", default="", namespaces=ns))
                for a in entry.findall("atom:author", ns)[:6]
            )
            published = clean_text(entry.findtext("atom:published", default="", namespaces=ns))[:10]
            if is_future_date(published):
                continue
            link = clean_text(entry.findtext("atom:id", default="", namespaces=ns))
            if title:
                papers.append(Paper(title, authors or "Unknown authors", published, "arXiv", link, abstract, "arXiv", module_hint="Fresh arXiv"))
    return papers


def search_crossref() -> list[Paper]:
    papers: list[Paper] = []
    for query in ["large language models", "artificial intelligence agents", "multimodal AI", "efficient language models"]:
        params = {
            "query.bibliographic": query,
            "filter": f"from-pub-date:{cutoff(45)}",
            "sort": "published",
            "order": "desc",
            "rows": "8",
        }
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"Crossref query failed for {query!r}: {exc}", file=sys.stderr)
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
                item.get("published-print", {}).get("date-parts")
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
                    module_hint="Published / Proceedings",
                )
            )
    return papers


def classify(paper: Paper) -> str:
    text = f"{paper.title} {paper.abstract} {paper.venue} {paper.module_hint}".lower()
    if paper.module_hint in {"Trending / Highly Cited Recent", "Notable Authors / Labs", "Fresh arXiv"}:
        return paper.module_hint
    if any(term in text for term in ["small language model", "distillation", "quantization", "compression", "efficient inference", "on device"]):
        return "Small Models / Efficient AI"
    if any(term in text for term in ["agent", "tool use", "planning", "reasoning", "test time"]):
        return "Agents / Tool Use / Reasoning"
    if any(term in text for term in ["multimodal", "vision-language", "video", "image generation", "diffusion"]):
        return "Multimodal / Vision-Language"
    if any(term in text for term in ["retrieval", "rag", "memory", "knowledge editing"]):
        return "RAG / Memory / Knowledge"
    if any(term in text for term in ["safety", "alignment", "red teaming", "reward model", "evaluation", "benchmark"]):
        return "Alignment / Safety / Evaluation"
    if any(term in text for term in ["robot", "code generation", "ai for science", "scientific discovery"]):
        return "AI for Science / Code / Robotics"
    return "Large Models / Foundation Models"


def score(paper: Paper) -> int:
    text = f"{paper.title} {paper.abstract} {paper.venue}".lower()
    value = 0
    value += 8 * sum(term.lower() in text for term in HOT_TERMS)
    value += 12 if any(org.lower() in text for org in ORG_TERMS) else 0
    value += min(paper.cited_by_count // 10, 25)
    value += 10 if paper.source == "arXiv" and paper.date >= cutoff(7) else 0
    value += 5 if paper.date >= cutoff(21) else 0
    value += 6 if paper.module_hint == "Notable Authors / Labs" else 0
    return value


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


def summarize(abstract: str, limit: int = 380) -> str:
    abstract = clean_text(re.sub(r"<[^>]+>", " ", abstract))
    if not abstract:
        return "No abstract available from the source metadata."
    if len(abstract) <= limit:
        return abstract
    return abstract[:limit].rsplit(" ", 1)[0] + "..."


def build_markdown(papers: list[Paper]) -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    groups: dict[str, list[Paper]] = {
        "Fresh arXiv": [],
        "Trending / Highly Cited Recent": [],
        "Notable Authors / Labs": [],
        "Large Models / Foundation Models": [],
        "Small Models / Efficient AI": [],
        "Agents / Tool Use / Reasoning": [],
        "Multimodal / Vision-Language": [],
        "RAG / Memory / Knowledge": [],
        "Alignment / Safety / Evaluation": [],
        "AI for Science / Code / Robotics": [],
        "Published / Proceedings": [],
    }
    for paper in sorted(papers, key=score, reverse=True):
        groups.setdefault(classify(paper), []).append(paper)

    limits = {
        "Fresh arXiv": 6,
        "Trending / Highly Cited Recent": 5,
        "Notable Authors / Labs": 5,
        "Large Models / Foundation Models": 3,
        "Small Models / Efficient AI": 3,
        "Agents / Tool Use / Reasoning": 3,
        "Multimodal / Vision-Language": 3,
        "RAG / Memory / Knowledge": 3,
        "Alignment / Safety / Evaluation": 3,
        "AI for Science / Code / Robotics": 3,
        "Published / Proceedings": 3,
    }

    lines = [
        "# Daily AI Paper Inspiration Briefing",
        "",
        f"Generated: {now:%Y-%m-%d %H:%M} Asia/Shanghai",
        "",
        "Goal: expose you to diverse frontier AI papers for research-topic inspiration, mixing latest arXiv work, hot recent papers, notable-author/lab work, small models, large models, agents, multimodal, RAG, safety, and AI-for-science/code/robotics.",
        "",
    ]

    shown: set[str] = set()
    for group, items in groups.items():
        selected = []
        for paper in items:
            key = re.sub(r"[^a-z0-9]+", "", paper.title.lower())[:140]
            if key in shown:
                continue
            selected.append(paper)
            shown.add(key)
            if len(selected) >= limits[group]:
                break
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
                    f"- Citation signal: {paper.cited_by_count} OpenAlex citations",
                    f"- Why it may spark ideas: {idea_angle(paper)}",
                    f"- Method / artifact clue: {method_clue(paper)}",
                    f"- Summary: {summarize(paper.abstract)}",
                    f"- Tags: {', '.join(tags_for(paper))}",
                    "",
                ]
            )

    lines.extend(["## Topic Sparks", ""])
    lines.extend(topic_sparks(papers))
    lines.extend(["", "## Read First", ""])
    top = sorted(papers, key=score, reverse=True)[:1]
    lines.append(f"Start with: **{top[0].title}**" if top else "No papers were retrieved today.")
    lines.append("")
    return "\n".join(lines)


def tags_for(paper: Paper) -> list[str]:
    text = f"{paper.title} {paper.abstract}".lower()
    candidates = {
        "LLM": ["large language model", "llm", "language model"],
        "Small Model": ["small language model", "distillation", "quantization", "compression"],
        "Agent": ["agent", "tool use", "planning"],
        "Reasoning": ["reasoning", "test time"],
        "Multimodal": ["multimodal", "vision-language", "video", "image"],
        "RAG": ["retrieval", "rag", "memory"],
        "Safety/Eval": ["safety", "alignment", "evaluation", "benchmark", "red teaming"],
        "AI4Science": ["science", "scientific", "biology", "chemistry"],
        "Robotics": ["robot", "robotics"],
        "Code": ["code generation", "programming"],
    }
    tags = [label for label, terms in candidates.items() if any(term in text for term in terms)]
    return tags[:6] or ["AI"]


def idea_angle(paper: Paper) -> str:
    text = f"{paper.title} {paper.abstract}".lower()
    if "small language model" in text or "distillation" in text or "quantization" in text:
        return "Small/efficient models can inspire deployable, low-cost, privacy-preserving, or edge AI research topics."
    if "agent" in text or "tool use" in text:
        return "Agent workflows suggest topics around task decomposition, tool orchestration, reliability, monitoring, and human supervision."
    if "multimodal" in text or "vision-language" in text:
        return "Multimodal systems open questions around richer interaction, embodied workflows, evaluation, and domain-specific interfaces."
    if "alignment" in text or "safety" in text or "evaluation" in text:
        return "Safety/evaluation work can become research on governance artifacts, benchmarks, failure modes, and trustworthy AI deployment."
    if "retrieval" in text or "rag" in text:
        return "RAG/memory work suggests topics around knowledge quality, provenance, personalization, and organizational knowledge systems."
    return "It may reveal a new capability, benchmark, system pattern, or application domain worth translating into a research question."


def method_clue(paper: Paper) -> str:
    text = f"{paper.title} {paper.abstract}".lower()
    if "benchmark" in text or "evaluation" in text:
        return "Benchmark/evaluation paper."
    if "dataset" in text:
        return "Dataset or data-centric contribution."
    if "framework" in text or "system" in text or "agent" in text:
        return "System/framework/artifact-style contribution."
    if "theory" in text or "analysis" in text:
        return "Analytical or conceptual contribution."
    if "training" in text or "fine-tuning" in text or "post-training" in text:
        return "Training or post-training method paper."
    return "Check full text for method, benchmark, dataset, or system contribution."


def topic_sparks(papers: list[Paper]) -> list[str]:
    text = " ".join(p.title + " " + p.abstract for p in papers[:60]).lower()
    sparks = []
    if "small language model" in text or "distillation" in text:
        sparks.append("- Small-model topic: compare when smaller specialized models outperform general large models in real organizational workflows.")
    if "agent" in text or "tool use" in text:
        sparks.append("- Agent topic: design oversight and recovery mechanisms for multi-step AI agents in high-stakes knowledge work.")
    if "multimodal" in text or "vision-language" in text:
        sparks.append("- Multimodal topic: build evaluation tasks that measure whether multimodal models improve decisions, not just perception accuracy.")
    if "retrieval" in text or "rag" in text:
        sparks.append("- RAG topic: study provenance, trust calibration, and knowledge decay in retrieval-augmented organizational assistants.")
    if "alignment" in text or "safety" in text:
        sparks.append("- Safety topic: turn red-team findings into deployable governance artifacts and continuous evaluation dashboards.")
    while len(sparks) < 5:
        sparks.append("- Cross-field topic: translate a frontier AI capability into a concrete artifact, benchmark, or field evaluation setting.")
    return sparks[:5]


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
    message["Subject"] = f"Daily AI Paper Inspiration Briefing - {today}"
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
    papers: list[Paper] = []
    for module, queries in TOPIC_QUERIES.items():
        for query in queries:
            papers.extend(search_openalex_topic(module, query))
    papers.extend(search_openalex_hot())
    papers.extend(search_openalex_authors())
    papers.extend(search_arxiv())
    papers.extend(search_crossref())
    markdown = build_markdown(dedupe(papers))
    print(markdown)
    send_email(markdown)


if __name__ == "__main__":
    main()
