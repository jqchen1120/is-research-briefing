# Daily IS Journal Paper Briefing

This GitHub Actions workflow sends a daily Information Systems research briefing at 10:07 Asia/Shanghai.

The IS briefing is intentionally simple. It uses OpenAlex metadata only and does not call an LLM.

The IS briefing separates papers into:

- ISR / MISQ / Management Science: up to 10 source-matched journal articles from the last 30 days.
- Other strong IS journals: up to 10 source-matched journal articles from the last 30 days, including JMIS, JAIS, DSS, I&M, EJIS, ISJ, JSIS, ISF, IJIM, Electronic Markets, Internet Research, Government Information Quarterly, Information Systems, and Journal of Organizational Computing and Electronic Commerce.

Each paper includes title, journal, date, OpenAlex citation count, authors, link, source keywords, and source abstract. If OpenAlex has no keywords or abstract for a paper, the email says so rather than generating replacements.

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

The workflow runs at `02:07 UTC`, which is `10:07 Asia/Shanghai`.

You can also run it manually from `Actions -> Daily IS Design Science Briefing -> Run workflow`.

## Files

- `.github/workflows/daily-is-briefing.yml`: GitHub Actions schedule and runtime.
- `scripts/daily_is_briefing.py`: OpenAlex journal metadata lookup, formatting, and email logic.
- `.github/workflows/daily-ai-paper-briefing.yml`: GitHub Actions schedule for the AI paper inspiration briefing.
- `scripts/daily_ai_paper_briefing.py`: Looks up fresh arXiv AI papers and recent high-citation AI papers from OpenAlex, then emails source metadata.

## AI Paper Briefing

The second workflow sends a simple AI paper briefing at 10:37 Asia/Shanghai. It uses source metadata only and does not call an LLM.

The AI briefing separates papers into:

- Fresh arXiv AI papers: up to 10 recent arXiv papers from AI-related categories such as `cs.AI`, `cs.CL`, `cs.LG`, `cs.CV`, `cs.RO`, and `stat.ML`.
- Trending AI papers: up to 10 AI-related OpenAlex papers from the last 30 days, sorted by recent citation signal.

Each paper includes title, source/venue, date, citation signal where available, authors, link, source keywords, and source abstract.

## Notes

The script uses public metadata APIs and standard-library Python only:

- OpenAlex
- arXiv

The result quality depends on source metadata freshness. For a production-grade version, add stateful deduplication and authenticated metadata sources.
