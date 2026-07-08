# ChatGPT app submission kit

Everything needed to submit this server to the ChatGPT app directory (OpenAI
Apps SDK). The code-side prerequisites are done; the rest is portal work in the
OpenAI Platform Dashboard.

## Server facts

- **MCP endpoint:** `https://mcp.dynamical.org/mcp` (streamable HTTP, public, no auth)
- **Version:** 0.1.2
- **Base URL is permanent** once published — updates are metadata snapshots, not URL changes.

## Directory metadata (paste into the dashboard draft)

| Field | Value |
| --- | --- |
| App name | dynamical.org Weather & Climate Catalog |
| Short description | Search dynamical.org's open catalog of cloud-optimized weather & climate datasets (GFS, ECMWF, HRRR, and more) and get ready-to-run Python to open them. |
| Company URL | https://dynamical.org |
| Privacy policy URL | https://dynamical.org/privacy/ |
| Support contact | feedback@dynamical.org |
| Categories | Data / Research / Science |
| Country availability | Worldwide (public open data) |

## Tools advertised (all read-only)

| Tool | Purpose |
| --- | --- |
| `search_catalog` | Search datasets by model / variable / region / resolution; ranked results |
| `get_dataset_info` | Full structured dataset metadata (domain, resolution, variables, docs) |
| `get_access_pattern` | Ready-to-run `dynamical_catalog.open(...)` + low-level snippet |
| `list_recent_runs` | Forecast run freshness from status.dynamical.org |

## Reviewer test cases / screenshot prompts

Run these in Developer Mode and screenshot each (tool call + result):

1. "What weather datasets does dynamical.org have for the continental US?" → `search_catalog` → HRRR, MRMS, etc.
2. "How do I open the NOAA GFS forecast dataset in Python?" → `get_access_pattern` → `dynamical_catalog.open("noaa-gfs-forecast")`.
3. "Is the latest NOAA GFS forecast run available yet?" → `list_recent_runs`.
4. "What variables and resolution does the ECMWF AIFS ENS forecast have?" → `get_dataset_info`.

## Submission checklist (mapped to status)

- [x] HTTPS, public, stable MCP URL
- [x] Tool annotations (`readOnlyHint` + titles) match behavior
- [x] `structuredContent` returned
- [x] Content-Security-Policy header on the endpoint
- [x] Published privacy policy disclosing returned/telemetry data
- [x] Own the domain/API (no third-party wrapping)
- [x] No restricted data, no auth, no write actions
- [ ] **Business verification** as dynamical.org (OpenAI Platform Dashboard → identity verification)
- [ ] **Logo** asset (dynamical.org brand)
- [ ] **Screenshots** from the prompts above
- [ ] Owner role or `api.apps.write` permission

## Portal steps (OpenAI Platform Dashboard)

1. Complete **business verification** for the publishing name (dynamical.org).
2. Create an **app draft**; enter the metadata above + MCP URL.
3. Upload **logo** and **screenshots**.
4. **Scan** the MCP endpoint (captures tools/schemas/annotations into a version snapshot).
5. **Submit for review** → note the Case ID emailed back; track in the dashboard.
6. On approval, **Publish**. Later changes: new draft → scan → submit → publish (same base URL).

Note: `search`/`fetch` tools (the ChatGPT *deep research* convention) are
intentionally **not** implemented — they aren't required for the app directory,
only for the separate deep-research connector type.

Docs: https://developers.openai.com/apps-sdk/app-submission-guidelines ·
https://developers.openai.com/apps-sdk/deploy/submission
