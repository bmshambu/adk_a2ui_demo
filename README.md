# A2UI Follow-up Button Demo — Google ADK Agent

A minimal Google ADK agent that emits A2UI follow-up buttons as a `DataPart` in every response. Built to validate the A2UI pattern locally before deploying to Gemini Enterprise.

---

## What it does

After every text response the agent appends an `application/json+a2ui` DataPart containing a Card with 4 clickable follow-up buttons. Gemini Enterprise reads this DataPart and renders the buttons natively in the chat shell — no custom frontend required.

```
User message
    │
    ▼
ADK LlmAgent (gemini-2.5-flash)
    │  after_model_callback fires on final response
    ▼
Content.parts = [
    Part(text="Agent answer..."),
    Part(inline_data=Blob(mime_type="application/json+a2ui", data=<Card JSON>))
]
    │
    ▼
A2A response → Gemini Enterprise renders buttons
```

---

## Project structure

```
gemini_ai2ui/
  agent/
    agent.py      ← LlmAgent + after_model_callback that appends A2UI DataPart
    a2ui.py       ← A2UI payload builder and static follow-up buttons
    __init__.py
  requirements.txt
  .env            ← GOOGLE_API_KEY (not committed)
```

---

## Setup

```bash
pip install -r requirements.txt
```

Set your API key in `.env`:
```
GOOGLE_API_KEY=your_key_here
```

---

## Run locally with adk web

```bash
# Load env (Git Bash)
export $(grep -v '^#' .env | xargs)

# Start ADK web server with A2A endpoint enabled
adk web . --port 8080 --a2a
```

Open **http://localhost:8080** — use the built-in ADK chat UI to send messages.

---

## Verify the A2UI DataPart

In the ADK web UI, open the raw event JSON after a response. You should see:

```json
{
  "content": {
    "role": "model",
    "parts": [
      { "text": "Agent answer..." },
      {
        "inlineData": {
          "mimeType": "application/json+a2ui",
          "data": "<base64 encoded Card JSON>"
        }
      }
    ]
  }
}
```

Decode the `data` field to confirm the Card payload:

```bash
python -c "import base64, json; print(json.dumps(json.loads(base64.b64decode('<data>')), indent=2))"
```

Expected output:

```json
{
  "type": "Card",
  "children": [
    { "type": "Text", "value": "What would you like to explore next?" },
    { "type": "Button", "label": "Tell me more",        "action": "Can you tell me more about that?" },
    { "type": "Button", "label": "Give an example",     "action": "Can you give me a concrete example?" },
    { "type": "Button", "label": "Summarize",           "action": "Please summarize the key points in bullet form" },
    { "type": "Button", "label": "Why does it matter?", "action": "Why does this matter in a real-world context?" }
  ]
}
```

---

## A2UI payload format

Defined in `agent/a2ui.py`. Each `Button`'s `action` string is injected verbatim as the next user message when clicked in Gemini Enterprise.

```python
{
    "type": "Card",
    "children": [
        {"type": "Text",   "value":  "<prompt shown above buttons>"},
        {"type": "Button", "label":  "<button text>", "action": "<sent as next message>"},
        ...
    ]
}
```

To customise the follow-up questions edit `DEMO_FOLLOWUPS` in `agent/a2ui.py`.

---

## How the DataPart is emitted

`agent/agent.py` uses `after_model_callback` on the `LlmAgent`:

```python
def _append_a2ui_part(callback_context, llm_response):
    # Skip streaming chunks and tool-call responses
    if llm_response.partial:
        return None
    # Append A2UI Part to the model's content
    llm_response.content.parts.append(
        types.Part(inline_data=types.Blob(
            mime_type="application/json+a2ui",
            data=encode(DEMO_FOLLOWUPS),
        ))
    )
    return llm_response
```

The callback fires after every LLM call. It skips partial (streaming) chunks and tool-call responses so the Card appears exactly once per final answer.

---

## Deploying to Gemini Enterprise

### 1. Fill in your `.env.dev`

```
GCP_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_CLOUD_STAGING_BUCKET=gs://your-project-adk-staging-dev
AGENT_DISPLAY_NAME=A2UI Demo Agent (Dev)
BUCKET_NAME=your-project-adk-staging-dev
```

### 2. Install deploy dependencies

```bash
pip install google-cloud-aiplatform[agent_engines,adk] google-cloud-secret-manager google-cloud-storage
```

### 3. Authenticate

```bash
gcloud auth application-default login
gcloud config set project your-gcp-project-id
```

### 4. Run the deploy script

```bash
# DEV (default)
python deploy_to_agent_engine.py

# PROD
DEPLOYMENT_ENVIRONMENT=prod python deploy_to_agent_engine.py
```

The script will:
- Create the GCS staging bucket if it doesn't exist
- Load any secrets from Secret Manager (if `SECRET_NAME` is set)
- Check if the agent already exists by `AGENT_DISPLAY_NAME`
- **Create** on first run → prints the resource name
- **Update** on subsequent runs → redeploys in place

### 5. Register in Gemini Enterprise console

1. Go to **Gemini Enterprise Admin console** → Agents
2. Click **Add agent** → **Vertex AI Agent Engine**
3. Paste the resource name printed by the script:  
   `projects/xxx/locations/us-central1/reasoningEngines/yyy`
4. Set visibility (all users / specific groups) → Save

GE automatically detects `application/json+a2ui` parts and renders the buttons natively.

---

Reference implementation: [github.com/wadave/agent-a2ui-demo](https://github.com/wadave/agent-a2ui-demo)  
A2UI spec: [a2ui.org](https://a2ui.org)
