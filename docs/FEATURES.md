# FEATURES: the 35 feature expansion

Added after the hackathon core (PHASES 0-6). Each item lists where it lives and how it is
tested. The safety rules in CLAUDE.md still hold for every one of them: nothing unverified
is ever sent, exported, published or pushed to a webhook.

## Operator workflow and alert lifecycle

| # | Feature | Backend | Frontend | Tests |
|---|---|---|---|---|
| 1 | Operator review: approve or reject a REVIEW language (new `APPROVED` status, reviewer name, note) | `POST /alerts/{id}/review` | alert detail page | `test_features.py::test_review_*` |
| 2 | Alert lifecycle: Update and Cancel messages (CAP `msgType`, `<references>`) | `POST /compile` (`references`), `POST /alerts/{id}/cancel` | alert detail page | `test_lifecycle_*` |
| 3 | CAP export options: status Exercise/Test/Draft/System (Actual refused), sender, sender name | `POST /export/cap` | alert detail page | `test_cap_options_*` |
| 4 | CAP geographic area: polygon, circle and geocode with validation | `CompileRequest.area` | console area editor | `test_cap_area_*` |
| 5 | CAP 1.2 validator for any CAP document (ours or pasted) | `POST /validate/cap` | alert detail page shows result | `test_cap_validator_*` |
| 6 | Multi format export: JSON bundle, plain text per language, CSV | `GET /alerts/{id}/export.{json,txt,csv}` | alert detail page | `test_exports` |
| 7 | Atom feed of published alerts (sendable languages only) | `GET /feed.atom` | link in footer | `test_feed` |
| 8 | Batch compile: many alert texts in one call | `POST /batch` | | `test_batch` |
| 9 | Drafts: save, list, load and delete alert drafts | `/drafts` CRUD | console drafts panel | `test_drafts` |
| 10 | Language presets (audience profiles) | `/presets` CRUD | console preset picker | `test_presets` |
| 11 | Alert search, filters (hazard, status, language, text) and pagination | `GET /alerts?q=&hazard=&status=&lang=&offset=` | history page | `test_search` |
| 12 | Statistics: totals per status, language, hazard, top block reasons | `GET /stats` | stats page | `test_stats` |

## Language quality

| # | Feature | Backend | Frontend | Tests |
|---|---|---|---|---|
| 13 | Lexicon explorer: every approved phrase, side by side with English | `GET /lexicon/{lang}` | lexicon page | `test_lexicon_explorer` |
| 14 | Native speaker sign-off for a lexicon, kept in the audit trail | `POST /lexicon/{lang}/signoff` | lexicon page | `test_signoff` |
| 15 | Lexicon lint: missing variants, round trip failures, stray negation | `GET /lexicon/{lang}/lint` | lexicon page | `test_lexicon_lint` |
| 16 | Readability of the English source (grade level, long sentences, all caps) | `IntentResult.readability` | console panel | `test_readability` |
| 17 | Intent consistency lint (contradictions, expiry without time, hazard/action mismatch) | `IntentResult.lint` | intent card | `test_intent_lint_*` |
| 18 | Glossary: do-not-translate terms, always locked as names | `/glossary` CRUD, used by `/intent` | settings page | `test_glossary` |
| 19 | Back translation: what each language says, in English | `LangResult.back_english` | language card | `test_back_english` |
| 20 | Duplicate alert warning (same text compiled recently) | `CompileResponse.duplicate_of` | console notice | `test_duplicate` |

## Channels

| # | Feature | Backend | Frontend | Tests |
|---|---|---|---|---|
| 21 | Channel budgets: WEA 90, WEA 360, SMS segments, per language | `LangResult.channels` | language card | `test_channel_budget` |
| 22 | SSML for broadcast text-to-speech (phones read digit by digit, RTL safe) | `GET /alerts/{id}/ssml?lang=` | alert detail page | `test_ssml` |
| 23 | Audit log CSV export | `GET /alerts/{id}/audit.csv` | audit log panel | `test_audit_csv` |
| 24 | Webhooks: signed (HMAC SHA-256) delivery of sendable languages, delivery audited | `/webhooks` CRUD, `stentor/webhooks.py` | settings page | `test_webhooks_*` |
| 25 | Alert expiry awareness: `expires_at` and `expired` on the public data | `PublicAlert.expires_at` | public page banner | `test_public_expiry` |

## Platform

| # | Feature | Backend | Frontend | Tests |
|---|---|---|---|---|
| 26 | Optional operator token for every write endpoint (`STENTOR_OPERATOR_TOKEN`) | `middleware.py` | token field in settings | `test_auth_*` |
| 27 | Rate limiting on write endpoints (`STENTOR_RATE_LIMIT` per minute per client) | `middleware.py` | | `test_rate_limit` |
| 28 | Request ID and `Server-Timing` headers | `middleware.py` | | `test_request_id` |
| 29 | Prometheus metrics (`/metrics`) | `middleware.py` | | `test_metrics` |

## Interface

| # | Feature | Where | Tests |
|---|---|---|---|
| 30 | History page with search, filters, pagination | `/history` | type check + build |
| 31 | Alert detail page: results, review actions, update/cancel, exports, SSML, CAP validation | `/alerts/[id]` | type check + build |
| 32 | Stats dashboard | `/stats` | type check + build |
| 33 | Console productivity: autosave, Ctrl+Enter shortcuts, copy buttons, drafts and presets panel | `/` | type check + build |
| 34 | Public page: browser language detection, large text mode, share/copy link, expiry banner | `/a/[id]` | type check + build |
| 35 | Printable multilingual poster with QR code, and pictogram SVG download | `/a/[id]/print`, pictogram | type check + build |

## Status

Done, 2026-11-08. Every row above is implemented and its test passes (`tests/test_features.py`,
43 tests; 211 in the whole suite). `next build` passes with lint and type checks (11 routes).
The README demo path is covered by `tests/test_api.py::test_intent_compile_cap_public_flow`
and still passes; the offline eval still catches 100% of injected corruptions. CAP exports,
including Update and Cancel messages with geometry, pass the built-in CAP 1.2 validator.
Visual polish of the new pages is a separate, manual pass.
