# Crypto Trading Bot — LLM Wiki

Mode: B (Repository) + concepts/ from Mode E
Purpose: Second brain for an autonomous Bybit trading bot — services, ports, deps, ADRs, signal flow, ML status, risk caps
Owner: mohammedsiradj05@gmail.com
Created: 2026-05-05

## Structure

```
wiki/
├── .raw/              # immutable source documents (README, CLAUDE.md snapshot, code dumps, transcripts)
├── _templates/        # frontmatter templates for new pages
├── modules/           # one note per service / package
├── components/        # reusable UI / utility units
├── decisions/         # ADRs
├── dependencies/      # external deps, models, infra notes
├── flows/             # data flows, request paths, signal pipeline, order lifecycle
├── concepts/          # cross-cutting domain ideas (risk, ML lifecycle, flags)
├── sources/           # one summary page per ingested raw source
├── questions/         # filed Q&A
├── meta/              # dashboards, lint reports
├── index.md           # master catalog
├── log.md             # append-only operation log
├── hot.md             # ~500-word recent context cache
└── overview.md        # executive summary
```

## Conventions

- All notes use YAML frontmatter: `type`, `status`, `created`, `updated`, `tags` (minimum)
- Wikilinks use `[[Note Name]]` format; filenames unique within their folder
- `.raw/` contains source documents — never modify them
- `index.md` master catalog — update on every ingest
- `log.md` append-only; new entries at TOP
- `hot.md` overwritten completely after every ingest / significant query (≤500 words)

## Operations

- Ingest: drop source in `wiki/.raw/`, say `/wiki-ingest <filename>`
- Query: `/wiki-query <question>`
- Lint: `/wiki-lint`
- Save current chat insight: `/save`
- Visual canvas: `/canvas`

## Cross-project hint

Other Claude Code sessions can reference this vault without duplicating context. Add to project CLAUDE.md:

```markdown
## Wiki Knowledge Base
Path: D:\Bimo_max\crypto-trading-bot\wiki

When you need context not already in the conversation:
1. Read wiki/hot.md first (≤500 words)
2. If not enough, read wiki/index.md
3. Then drill into wiki/<domain>/_index.md
4. Only then read individual pages

Skip the wiki for: general coding questions, language syntax, things already in conversation.
```

## Repo coexistence

Vault root = repo root (`D:\Bimo_max\crypto-trading-bot\`). Project's authoritative CLAUDE.md lives at repo root. **This file is wiki-only conventions.** Don't duplicate project rules here — link to repo's `CLAUDE.md` if needed.
