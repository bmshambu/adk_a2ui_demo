# A2UI Demo Agent — Clickable Follow-up Buttons in Gemini Enterprise

A Google ADK agent that renders **clickable follow-up question buttons** and a **collapsible references modal** natively in the Gemini Enterprise chat, using the A2UI v0.8 protocol. Validated end-to-end: local → `adk web` → Agent Engine → Gemini Enterprise.

---

## What it does

After every text response, the agent attaches A2UI payloads that Gemini Enterprise renders natively — no custom frontend:

```
Agent:  <answer text>

        📚 View references (10)          ← Modal: links open in an overlay,
                                            keeping the chat clean
        What would you like to explore next?
        [Tell me more] [Give an example] [Summarize] [Why does it matter?]
                                          ← clickable follow-up buttons
```

Clicking a button sends a `userAction` event back to the agent, which answers the chosen follow-up question.

---

## Project structure

```
gemini_ai2ui/
  agent/
    agent.py                  ← LlmAgent + after_model_callback attaching A2UI parts
    a2ui.py                   ← A2UI v0.8 payload builders (buttons, references modal)
    __init__.py
  deploy_to_agent_engine.py   ← create-or-update deployment to Vertex AI Agent Engine
  requirements.txt            ← pinned (see Version pins below)
  .env                        ← GOOGLE_API_KEY for local testing
  .env.dev / .env.prod        ← per-environment deployment config
```

---

## How it works (the part that took debugging)

### 1. A2UI v0.8 message format — not a simple component tree

Gemini Enterprise supports **A2UI v0.8 only**. Each response carries a sequence of three messages:

```json
{"surfaceUpdate":   {"surfaceId": "...", "components": [ ...flat list, linked by id... ]}}
{"dataModelUpdate": {"surfaceId": "...", "contents": {}}}
{"beginRendering":  {"surfaceId": "...", "root": "root"}}
```

Components reference each other by id (not nested), e.g.:

```json
{"id": "btn_0", "component": {"Button": {
    "child": "btn_0_label",
    "action": {"name": "followup_question",
               "context": [{"key": "question",
                            "value": {"literalString": "Can you tell me more?"}}]}
}}}
```

### 2. Transport — must be an A2A DataPart, not a file blob

GE expects each A2UI message as an A2A **DataPart** with metadata `{"mimeType": "application/json+a2ui"}`. Emitting it as `inline_data` bytes produces **"Unsupported attachment"** in GE.

ADK's documented mechanism for emitting a custom DataPart from agent code: wrap the DataPart JSON in `<a2a_datapart_json>...</a2a_datapart_json>` inside a `text/plain` blob — ADK's part converter unwraps it on the A2A wire. See `to_genai_part()` in [agent/a2ui.py](agent/a2ui.py).

### 3. Fresh surfaceId per response

GE keys rendered cards by `surfaceId`. Reusing one means later responses *update the first card* instead of rendering a new one (buttons appear only once per conversation). Every builder call generates a unique id.

### 4. Button clicks arrive as userAction events

Clicking a button does **not** inject text as the user's message. GE sends a structured event:

```json
{"userAction": {"name": "followup_question", "context": {"question": "..."}}}
```

The chat shows a hardcoded **"User action triggered."** bubble for the click — this is GE client behavior and cannot be changed from the payload (tested). Mitigation: the agent instruction echoes the chosen question as a `> quote` at the top of its reply, keeping the transcript readable.

---

## Version pins — do not unpin

```
google-cloud-aiplatform[agent_engines,adk]==1.148.1
google-adk[a2a]==1.31.1
a2a-sdk>=0.3.4,<0.4
```

- **aiplatform ↔ adk**: unpinned, the `AdkApp` template inside aiplatform calls session methods synchronously while newer google-adk made them async → `'coroutine' object has no attribute 'id'` at runtime in Agent Engine.
- **Local must match the container**: `AdkApp` pickles the agent locally and unpickles it in the container — mismatched ADK versions break.
- Keep `requirements.txt` and `agent_requirements` in [deploy_to_agent_engine.py](deploy_to_agent_engine.py) in sync.

---

## Local testing with adk web

```bash
pip install -r requirements.txt

# Git Bash: load env
export $(grep -v '^#' .env | xargs)

adk web . --port 8080 --a2a
```

Open http://localhost:8080. The built-in UI does **not** render A2UI buttons — verify via the raw event JSON instead: each response should contain `inlineData` parts that convert to DataParts with `mimeType: application/json+a2ui` (the Events panel shows the tagged parts).

Quick payload sanity check without a server:

```bash
python -c "
from agent.a2ui import demo_followups, to_genai_part
from google.adk.a2a.converters.part_converter import convert_genai_part_to_a2a_part
for m in demo_followups():
    p = convert_genai_part_to_a2a_part(to_genai_part(m))
    print(type(p.root).__name__, p.root.metadata.get('mimeType'), list(p.root.data.keys()))
"
```

Expected: three `DataPart application/json+a2ui` lines with `surfaceUpdate`, `dataModelUpdate`, `beginRendering`.

---

## Deploying to Gemini Enterprise

### 1. Configure `.env.dev` (or `.env.prod`)

```
GCP_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_CLOUD_STAGING_BUCKET=gs://your-project-adk-staging-dev
AGENT_DISPLAY_NAME=A2UI Demo Agent (Dev)
BUCKET_NAME=your-project-adk-staging-dev
# SECRET_NAME=optional-secret-manager-json-secret
```

### 2. Authenticate and deploy

```bash
gcloud auth application-default login
gcloud config set project your-gcp-project-id

python deploy_to_agent_engine.py                          # dev (default)
DEPLOYMENT_ENVIRONMENT=prod python deploy_to_agent_engine.py   # prod
```

The script creates the staging bucket if missing, loads optional Secret Manager env vars, then **creates** the agent on first run or **updates in place** on later runs (matched by display name — resource name stays stable, so no GE re-registration on updates).

### 3. Register in Gemini Enterprise (first deploy only)

Gemini Enterprise Admin console → **Agents → Add agent → Vertex AI Agent Engine** → paste the printed resource name (`projects/.../reasoningEngines/...`) → set visibility → Save.

---

## A2UI v0.8 component catalog (all supported by GE)

| Category | Components |
|---|---|
| Display | `Text`, `Image`, `Icon`, `Video`, `AudioPlayer`, `Divider` |
| Layout | `Row`, `Column`, `List`, `Card`, `Tabs`, `Modal` |
| Interactive | `Button`, `CheckBox`, `TextField`, `DateTimeInput`, `MultipleChoice`, `Slider` |

Notes from testing:
- Markdown links render inside `Text` components (used by the references modal).
- There is **no accordion/collapsible component** — `Modal` (overlay on click) is the closest; `Tabs` works for parallel sections.
- A2UI provides *structure* (layout, alignment, dividers, text hierarchy) but not *styling* (no widths, colors, fonts) — GE's renderer owns the pixels.

## Customizing

- **Follow-up questions**: edit the `buttons` list in `demo_followups()` ([agent/a2ui.py](agent/a2ui.py)). `label` is the button caption; `action` is the question the agent answers on click.
- **References**: `references_modal(references)` takes `{"title", "url"}` dicts — in a real agent, populate from the turn's retrieval results instead of the static `DEMO_REFERENCES` in [agent/agent.py](agent/agent.py).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `application/json+a2ui: Unsupported attachment` in GE | Payload sent as file blob, not DataPart — use `to_genai_part()` wrapping |
| Buttons render only on the first response | Reused `surfaceId` — generate a fresh one per response |
| `'coroutine' object has no attribute 'id'` in Agent Engine logs | aiplatform/adk version mismatch — restore the pins above |
| `SessionNotFoundError` locally | Create the session via `await session_service.create_session(...)` before `runner.run_async` |
| "User action triggered." instead of the question | GE client behavior, not fixable from payload — agent echoes the question as a quote |

## References

- [A2UI v0.8 extension spec](https://github.com/google/a2ui/blob/main/specification/v0_8/docs/a2ui_extension_specification.md)
- [A2UI v0.8 standard catalog](https://github.com/google/a2ui/blob/main/specification/v0_8/json/standard_catalog_definition.json)
- [GE: register and manage A2UI agents](https://docs.cloud.google.com/gemini/enterprise/docs/a2ui-agents/register-and-manage-an-a2ui-agent)
- [GE: A2UI component gallery](https://docs.cloud.google.com/gemini/enterprise/docs/a2ui-agents/a2ui-component-gallery-reference)
- [Reference implementation (restaurant finder)](https://github.com/wadave/agent-a2ui-demo)
- [A2UI Composer playground](https://a2ui-composer.ag-ui.com/components)
