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

OTHER_IS_JOURNALS = [
    "Journal of Strategic Information Systems",
    "Information Systems Frontiers",
    "International Journal of Information Management",
    "Information Systems",
    "Data Base for Advances in Information Systems",
    "Electronic Markets",
    "Internet Research",
    "Government Information Quarterly",
]

DAILY_IS_QUERIES = [
    "MIS Quarterly",
    "Information Systems Research",
    "Journal of Management Information Systems",
]

IS_JOURNAL_ISSNS = [
    ("MIS Quarterly", "0276-7783"),
    ("Information Systems Research", "1047-7047"),
    ("Management Science", "0025-1909"),
    ("Production and Operations Management", "1059-1478"),
    ("Journal of Management Information Systems", "0742-1222"),
    ("Journal of Operations Management", "0272-6963"),
    ("Journal of the Association for Information Systems", "1536-9323"),
    ("Decision Support Systems", "0167-9236"),
    ("Information & Management", "0378-7206"),
    ("European Journal of Information Systems", "0960-085X"),
    ("Information Systems Journal", "1350-1917"),
    ("Journal of Strategic Information Systems", "0963-8687"),
    ("Information Systems Frontiers", "1387-3326"),
    ("International Journal of Information Management", "0268-4012"),
    ("Information Systems", "0306-4379"),
    ("Data Base for Advances in Information Systems", "0095-0033"),
    ("Electronic Markets", "1019-6781"),
    ("Internet Research", "1066-2243"),
    ("Government Information Quarterly", "0740-624X"),
]

DSR_AI_QUERIES = [
    "deep learning decision support information systems",
    "machine learning artifact design information systems",
    "AI-enabled decision support design science information systems",
    "predictive model decision support information systems",
    "recommender system design science information systems",
]

SSRN_DSR_AI_QUERIES = [
    "deep learning decision support information systems",
    "machine learning decision support information systems",
    "LLM decision support information systems",
    "AI-enabled decision support enterprise systems",
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

AI_METHOD_TERMS = [
    "machine learning",
    "deep learning",
    "large language model",
    "generative ai",
    "neural network",
    "natural language processing",
    "reinforcement learning",
    "computer vision",
    "graph neural",
    "prediction model",
    "predictive model",
    "classifier",
    "classification",
    "recommendation",
    "recommender",
    "algorithmic",
    "optimization",
]

DL_METHOD_TERMS = [
    "machine learning",
    "deep learning",
    "neural network",
    "large language model",
    "generative ai",
    "natural language processing",
    "reinforcement learning",
    "computer vision",
    "graph neural",
    "transformer",
    "embedding",
    "representation learning",
    "classification",
    "prediction",
    "predictive model",
    "recommender",
    "recommendation",
    "algorithm",
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

STRICT_DSR_TERMS = [
    "design science",
    "action design research",
    "artifact",
    "artefact",
    "prototype",
    "design principle",
    "design theory",
    "design evaluation",
    "build and evaluate",
    "instantiation",
]

AI_DESIGN_TERMS = [
    "artifact",
    "artefact",
    "prototype",
    "decision support",
    "decision aid",
    "design science",
    "design principle",
    "design theory",
    "build and evaluate",
    "instantiation",
    "system",
    "tool",
    "framework",
    "model",
    "method",
    "workflow",
    "intervention",
    "implementation",
    "deployment",
]

AI_DESIGN_STRONG_TERMS = [
    "artifact",
    "artefact",
    "prototype",
    "decision support",
    "decision aid",
    "recommender system",
    "recommendation system",
    "predictive model",
    "prediction model",
    "classification model",
    "algorithm design",
    "model design",
    "system design",
    "tool",
    "build and evaluate",
    "deployment",
    "implementation",
    "intervention",
    "design science",
    "design principle",
]

IS_CONTEXT_TERMS = [
    "information systems",
    "management information systems",
    "decision support systems",
    "enterprise systems",
    "digital platform",
    "digital platforms",
    "business process",
    "organizational",
    "organisation",
    "enterprise",
    "operations",
    "supply chain",
    "e-commerce",
    "health it",
    "fintech",
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
    source_keywords: tuple[str, ...] = ()


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


def fetch_json(url: str, timeout: int = 4) -> dict:
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


def unique_keywords(values: Iterable[str], limit: int = 6) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    blocked = {
        "information systems",
        "information system",
        "computer science",
        "business",
        "management science",
        "social sciences",
        "article",
        "research",
    }
    for value in values:
        label = clean_text(value).strip(" .;:,")
        if not label:
            continue
        key = label.lower()
        if key in seen or key in blocked or len(key) < 3:
            continue
        seen.add(key)
        result.append(label)
        if len(result) >= limit:
            break
    return result


def openalex_keywords(item: dict) -> tuple[str, ...]:
    labels: list[str] = []
    for keyword in item.get("keywords") or []:
        labels.append(clean_text(keyword.get("display_name", "")))
    primary_topic = item.get("primary_topic") or {}
    labels.append(clean_text(primary_topic.get("display_name", "")))
    for topic in item.get("topics") or []:
        labels.append(clean_text(topic.get("display_name", "")))
    for concept in item.get("concepts") or []:
        if int(concept.get("level") or 99) <= 2:
            labels.append(clean_text(concept.get("display_name", "")))
    return tuple(unique_keywords(labels))


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
        source_keywords=openalex_keywords(item),
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
    filters.append(f"to_publication_date:{to_date or today_utc()}")
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


def crossref_date(item: dict) -> str:
    for key in ["published-print", "published-online", "published", "posted", "created", "deposited"]:
        parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
        if parts:
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 1
            day = int(parts[2]) if len(parts) > 2 else 1
            return f"{year:04d}-{month:02d}-{day:02d}"
    return ""


def paper_from_crossref_ssrn(item: dict, module_hint: str) -> Paper | None:
    title = clean_text(" ".join(item.get("title") or []))
    date = crossref_date(item)
    if not title or is_future_date(date):
        return None
    authors = ", ".join(
        clean_text(" ".join(part for part in [author.get("given", ""), author.get("family", "")] if part))
        for author in item.get("author", [])[:6]
    )
    doi = clean_text(item.get("DOI", ""))
    abstract = clean_text(re.sub(r"<[^>]+>", " ", item.get("abstract", "")))
    subjects = [clean_text(subject) for subject in item.get("subject", [])]
    return Paper(
        title=title,
        authors=authors or "Unknown authors",
        date=date,
        source="SSRN",
        url=f"https://doi.org/{doi}" if doi else clean_text(item.get("URL", "")),
        abstract=abstract,
        venue="SSRN",
        doi=doi,
        cited_by_count=int(item.get("is-referenced-by-count") or 0),
        module_hint=module_hint,
        source_keywords=tuple(unique_keywords(subjects)),
    )


def search_ssrn_crossref(query: str, from_date: str, per_page: int = 8) -> list[Paper]:
    filters = [f"from-pub-date:{from_date}", f"until-pub-date:{today_utc()}", "prefix:10.2139"]
    params = {
        "query.bibliographic": query,
        "filter": ",".join(filters),
        "sort": "published",
        "order": "desc",
        "rows": str(per_page),
    }
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    try:
        data = fetch_json(url, timeout=8)
    except Exception as exc:
        print(f"Crossref SSRN query failed for {query!r}: {exc}", file=sys.stderr)
        return []
    items = (data.get("message") or {}).get("items", [])
    papers = [paper_from_crossref_ssrn(item, "Recent high-value DSR + AI/ML") for item in items]
    return [paper for paper in papers if paper]


def search_openalex_issn(venue_name: str, issn: str, from_date: str, per_page: int = 5) -> list[Paper]:
    filters = [
        f"primary_location.source.issn:{issn}",
        f"from_publication_date:{from_date}",
        f"to_publication_date:{today_utc()}",
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
        print(f"OpenAlex ISSN query failed for {venue_name!r}: {exc}", file=sys.stderr)
        return []
    papers = [paper_from_openalex(item, "Latest IS papers") for item in data.get("results", [])]
    return [paper for paper in papers if paper and not is_editorial(paper)]


def search_openalex_issns(journals: list[tuple[str, str]], from_date: str, per_page: int) -> list[Paper]:
    papers: list[Paper] = []
    if not journals:
        return papers
    max_workers = min(6, len(journals))
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        futures = [
            executor.submit(search_openalex_issn, venue_name, issn, from_date, per_page)
            for venue_name, issn in journals
        ]
        try:
            for future in as_completed(futures, timeout=35):
                papers.extend(future.result())
        except TimeoutError:
            print("OpenAlex ISSN batch timed out; continuing with completed journal results.", file=sys.stderr)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return papers


def search_daily_is() -> list[Paper]:
    papers = search_openalex_issns(IS_JOURNAL_ISSNS, cutoff(730), per_page=4)
    candidates = dedupe(papers)
    filtered = filter_relevant_is(candidates)
    if filtered:
        return filtered
    if candidates:
        return candidates
    return search_openalex("information systems", cutoff(730), per_page=15, module_hint="Latest IS papers")


def is_editorial(paper: Paper) -> bool:
    title = paper.title.lower()
    return any(marker in title for marker in ["editor's comments", "editor’s comments", "editorial", "call for papers", "erratum", "corrigendum"])


def search_recent_high_value_dsr_ai() -> list[Paper]:
    papers = search_openalex_issns(IS_JOURNAL_ISSNS, years_ago(3), per_page=5)
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
    for query in SSRN_DSR_AI_QUERIES:
        papers.extend(search_ssrn_crossref(query, years_ago(3), per_page=6))
    return [
        paper
        for paper in dedupe(papers)
        if is_dsr_ai_source_candidate(paper) and is_dsr_ai_method_paper(paper)
    ]


def filter_relevant_is(papers: list[Paper]) -> list[Paper]:
    filtered = []
    for paper in papers:
        text = paper_text(paper)
        if venue_priority(paper.venue) > 0 or "information systems" in text:
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


def is_ai_or_dsr_related(paper: Paper) -> bool:
    text = paper_text(paper)
    return contains_any(text, AI_ML_TERMS) or contains_any(text, STRICT_DSR_TERMS) or "decision support" in text


def is_dsr_ai_method_paper(paper: Paper) -> bool:
    text = paper_text(paper)
    has_ai_method = contains_any(text, DL_METHOD_TERMS)
    has_design_context = contains_any(text, AI_DESIGN_STRONG_TERMS)
    behavioral_only = (
        contains_any(text, ["adoption", "acceptance", "intention", "perception", "attitude", "trust", "continuance"])
        and not contains_any(text, ["decision support", "artifact", "prototype", "recommender", "predictive model", "classification model"])
    )
    return has_ai_method and has_design_context and not behavioral_only


def is_dsr_ai_source_candidate(paper: Paper) -> bool:
    if venue_priority(paper.venue) > 0:
        return True
    text = paper_text(paper)
    return paper.source == "SSRN" and contains_any(text, IS_CONTEXT_TERMS)


def is_is_related(paper: Paper) -> bool:
    text = paper_text(paper)
    return (
        "information systems" in text
        or "mis quarterly" in paper.venue.lower()
        or "information systems research" in paper.venue.lower()
        or "journal of management information systems" in paper.venue.lower()
    )


def venue_priority(venue: str) -> int:
    lowered = venue.lower()
    if any(name.lower() in lowered for name in FIRST_TIER_JOURNALS):
        return 4
    if any(name.lower() in lowered for name in SECOND_TIER_JOURNALS):
        return 3
    if any(name.lower() in lowered for name in OTHER_IS_JOURNALS):
        return 2
    return 0


def keywords(paper: Paper) -> list[str]:
    if paper.source_keywords:
        return unique_keywords(paper.source_keywords, limit=6)
    text = paper_text(paper)
    explicit_phrases = extract_candidate_phrases(text)
    candidates = [
        "artificial intelligence",
        "deep learning",
        "machine learning",
        "large language model",
        "generative AI",
        "decision support",
        "AI adoption",
        "user trust",
        "design science",
        "artifact design",
        "predictive model",
        "recommender system",
        "digital platform",
        "health IT",
        "privacy",
        "cybersecurity",
        "social media",
        "digital transformation",
        "human-AI collaboration",
    ]
    tags = [label for label in candidates if label.lower() in text]
    title_terms = [
        phrase
        for phrase in re.findall(r"\b[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){1,2}\b", paper.title)
        if not phrase.lower().endswith(" in")
    ]
    return unique_keywords([*tags, *explicit_phrases, *title_terms], limit=6) or ["IS research"]


def extract_candidate_phrases(text: str) -> list[str]:
    stop = {
        "this paper",
        "the paper",
        "we propose",
        "we develop",
        "we design",
        "we examine",
        "we study",
        "our study",
        "our results",
        "the results",
        "information systems",
        "research paper",
    }
    phrases = re.findall(r"\b[a-z][a-z-]{3,}(?:\s+[a-z][a-z-]{3,}){1,2}\b", text)
    scored: list[tuple[int, str]] = []
    for phrase in phrases:
        phrase = phrase.strip()
        if phrase in stop:
            continue
        score = 0
        if contains_any(phrase, DL_METHOD_TERMS):
            score += 4
        if contains_any(phrase, AI_DESIGN_STRONG_TERMS):
            score += 3
        if contains_any(phrase, IS_CONTEXT_TERMS):
            score += 2
        if score:
            scored.append((score, phrase))
    return [phrase for _, phrase in sorted(scored, reverse=True)]


def abstract_short(paper: Paper, limit: int = 850) -> str:
    abstract = clean_text(re.sub(r"<[^>]+>", " ", paper.abstract))
    if not abstract:
        return f"This paper studies {paper.title}. {method_summary(paper)}"
    sentences = split_sentences(abstract)
    background = pick_sentence(
        sentences,
        ["problem", "challenge", "need", "important", "however", "despite", "lack", "gap", "because", "question"],
        default_index=0,
    )
    method = pick_sentence(
        sentences,
        [
            "we develop",
            "we design",
            "we build",
            "we propose",
            "we use",
            "machine learning",
            "deep learning",
            "model",
            "algorithm",
            "framework",
            "artifact",
            "decision support",
        ],
        default_index=1,
        exclude={background},
    )
    contribution = pick_sentence(
        sentences,
        ["contribute", "show", "find", "demonstrate", "evaluate", "results", "evidence", "implication"],
        default_index=2,
        exclude={background, method},
    )
    summary = " ".join(unique_sentences([background, method, contribution]))
    if not summary:
        summary = first_sentences(abstract, max_sentences=3)
    return trim_text(summary, limit)


def first_sentences(text: str, max_sentences: int = 2) -> str:
    selected = split_sentences(text)[:max_sentences]
    return " ".join(selected)


def split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]


def pick_sentence(sentences: list[str], markers: list[str], default_index: int, exclude: set[str] | None = None) -> str:
    exclude = exclude or set()
    for sentence in sentences:
        if sentence in exclude:
            continue
        lowered = sentence.lower()
        if any(marker in lowered for marker in markers):
            return sentence
    if default_index < len(sentences) and sentences[default_index] not in exclude:
        return sentences[default_index]
    for sentence in sentences:
        if sentence not in exclude:
            return sentence
    return ""


def unique_sentences(sentences: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for sentence in sentences:
        normalized = re.sub(r"\W+", "", sentence.lower())
        if not sentence or normalized in seen:
            continue
        seen.add(normalized)
        result.append(sentence)
    return result


def trim_text(text: str, limit: int) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].rstrip(".,;:")
    return clipped + "."


def method_summary(paper: Paper) -> str:
    text = paper_text(paper)
    if "action design research" in text:
        return "Uses action design research: builds an artifact in an organizational setting, iterates with stakeholders, and evaluates the artifact through use."
    if "generative ai" in text or "large language model" in text:
        return "Designs or evaluates a GenAI/LLM-enabled artifact, workflow, or decision-support process in an IS context."
    if "machine learning" in text or "deep learning" in text:
        return "Uses ML/DL methods to model, predict, classify, recommend, or support decisions for an applied organizational problem."
    if "design principle" in text or "design theory" in text:
        return "Derives design principles or design-theory components from artifact development, evaluation evidence, or prior theory."
    if "survey" in text:
        return "Uses survey evidence to model perceptions, adoption, behavior, or organizational outcomes related to IS use."
    if "interview" in text or "case study" in text:
        return "Uses qualitative field evidence such as interviews or case analysis to explain how the IS phenomenon unfolds in context."
    if "experiment" in text:
        return "Uses experimental or quasi-experimental evidence to estimate effects of a digital intervention, artifact, or information treatment."
    if "regression" in text or "panel data" in text or "econometric" in text:
        return "Uses empirical modeling, likely regression or panel-data analysis, to estimate relationships or effects in an IS setting."
    if "platform" in text:
        return "Analyzes or designs platform mechanisms such as governance, matching, participation, or ecosystem coordination."
    return "Studies an IS phenomenon using the article's reported empirical, analytical, or design approach; the abstract metadata gives the main setup."


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


def paper_block(paper: Paper, include_citations: bool = False) -> list[str]:
    lines = [
        f"### {paper.title}",
        f"- Authors: {paper.authors}",
        f"- Date: {paper.date or 'Unknown'}",
        f"- Venue/source: {paper.venue or paper.source}",
        f"- Link: {paper.url or 'No link available'}",
    ]
    if include_citations:
        lines.append(f"- Citation signal: {paper.cited_by_count} OpenAlex citations")
    lines.extend(
        [
            f"- Abstract: {abstract_short(paper)}",
            f"- Keywords: {', '.join(keywords(paper))}",
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

    sections = {
        "Latest IS papers": latest,
        "Recent high-value DSR + AI/ML papers": high_value,
    }

    lines = [
        "# Daily IS Paper Briefing",
        f"Generated: {now:%Y-%m-%d %H:%M} Asia/Shanghai",
        "",
    ]

    if latest:
        lines.extend(["## 1. Latest IS Papers", ""])
        for paper in latest:
            lines.extend(paper_block(paper))

    lines.extend(["## 2. Recent High-Value DSR + AI/ML Papers", ""])
    if high_value:
        for paper in high_value:
            lines.extend(paper_block(paper, include_citations=True))
    else:
        lines.extend(["No strong matches found today.", ""])

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
