# Repository guidance for Codex

## Goal
Maintain a reliable literature-alert bot for electrochemical CO2 reduction in acidic media.

## Scientific relevance rules
A paper should only be alerted when its searchable metadata contains evidence for all three concepts:
1. CO2 or carbon dioxide.
2. Electrochemical reduction/electrolysis.
3. Acidic media or a proton-conducting/cation-exchange membrane environment.

Do not broaden the filter to generic CO2 capture, thermochemical hydrogenation, alkaline CO2RR, ORR, or water electrolysis.

## Engineering rules
- Keep secrets out of the repository and logs.
- Preserve DOI/OpenAlex deduplication.
- Add or update tests whenever relevance logic changes.
- Keep Telegram messages below the platform message-size limit.
- Scheduled runs must remain manually triggerable with `workflow_dispatch`.
- Do not replace primary-source APIs with web scraping.

## Validation
Run:

```bash
python -m pytest -q
python -m ruff check .
```
