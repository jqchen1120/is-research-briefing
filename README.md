# Daily IS Design Science Research Briefing

This GitHub Actions workflow sends a daily Information Systems research briefing at 10:00 Asia/Shanghai.

The briefing prioritizes Design Science Research and separates papers into:

- Design Science Research
- Adjacent Empirical IS
- Behavioral / Organizational IS
- Other Relevant IS
- Recent High-Value DSR Reading
- Emerging Opportunities for DSR

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

The second workflow sends a broader AI paper briefing at 10:30 Asia/Shanghai. It mixes:

- Fresh arXiv papers
- Trending or highly cited recent AI papers
- Papers from notable authors and labs
- Large models and foundation models
- Small models and efficient AI
- Agents, tool use, and reasoning
- Multimodal and vision-language models
- RAG, memory, and knowledge systems
- Alignment, safety, and evaluation
- AI for science, code, and robotics

## Notes

The script uses public metadata APIs and standard-library Python only:

- OpenAlex
- arXiv
- Crossref

The result quality depends on source metadata freshness. For a production-grade version, add Semantic Scholar, SSRN, stateful deduplication, and a better LLM-based ranking step.

The high-value reading section recommends recent but not brand-new DSR-related papers, usually from 2018 onward and excluding the newest 60 days. It prioritizes design science, artifacts, design principles, human-AI collaboration, generative AI systems, platforms, decision support, health IT, and security/privacy tools. Older foundational classics are intentionally not the default recommendations.
