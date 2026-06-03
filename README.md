# Daily IS Design Science Research Briefing

This GitHub Actions workflow sends a daily Information Systems research briefing at 10:00 Asia/Shanghai.

The IS briefing is intentionally concise. Each paper includes authors, date, link, a concise abstract-style summary, and keywords.

The IS briefing separates papers into:

- Latest IS papers from IS journals and conferences, with field labels such as modeling, design, behavioral, platform, or AI/ML.
- Recent high-value DSR + AI/ML papers from the last three years, prioritizing ISR, MISQ, and Management Science, then POM, JMIS, JOC, JAIS, DSS, I&M, EJIS, and ISJ.
- Recent IS conference DSR + AI/ML papers from the last three months for broader ideation.
- Highlight summary after all search modules.

The `Field` label is a single coarse type such as `Design Science`, `Modeling`, `Behavioral`, `Empirical`, or `General IS`. Keywords are split into method/background signals.

## Setup

1. Create a GitHub repository and push this folder to it.
2. In the repository, open `Settings -> Secrets and variables -> Actions -> New repository secret`.
3. Add these secrets:

| Secret | Example | Notes |
|---|---|---|
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | Use `587` for STARTTLS or `465` for SSL |
| `SMTP_USERNAME` | `your_email@gmail.com` | SMTP login |
| `SMTP_PASSWORD` | Gmail app password | Do not use your normal account password |
| `MAIL_FROM` | `your_email@gmail.com` | Sender address |
| `MAIL_TO` | `target@example.com` | One or more recipients, comma-separated |
| `OPENALEX_MAILTO` | `target@example.com` | Optional but recommended for polite OpenAlex API use |

For Gmail, enable 2-step verification and create an app password.

## Schedule

The workflow runs at `02:00 UTC`, which is `10:00 Asia/Shanghai`.

You can also run it manually from `Actions -> Daily IS Design Science Briefing -> Run workflow`.

## Files

- `.github/workflows/daily-is-briefing.yml`: GitHub Actions schedule and runtime.
- `scripts/daily_is_briefing.py`: Search, classify, format, and email logic.
- `.github/workflows/daily-ai-paper-briefing.yml`: GitHub Actions schedule for the AI paper inspiration briefing.
- `scripts/daily_ai_paper_briefing.py`: Searches frontier AI papers across arXiv, OpenAlex, and Crossref, then sends a diverse idea-sparking email.

## AI Paper Inspiration Briefing

The second workflow sends a broader AI paper briefing at 10:30 Asia/Shanghai. Each paper includes authors, date, link, a concise abstract-style summary, keywords, and a quality signal. It mixes:

- Fresh arXiv papers, selected by topic relevance plus notable author/lab/company signals.
- Trending recent AI papers and topics, using citation signal where available.
- Notable author/lab papers.
- A rotating daily series such as GNN, RL, LLM, RAG, Agents, Multimodal, Efficient Models, or Alignment/Evaluation. This section requires citation signal and mixes classic and frontier must-reads.

## Notes

The script uses public metadata APIs and standard-library Python only:

- OpenAlex
- arXiv
- Crossref

The result quality depends on source metadata freshness. For a production-grade version, add Semantic Scholar, SSRN, stateful deduplication, and an LLM-based ranking step.
