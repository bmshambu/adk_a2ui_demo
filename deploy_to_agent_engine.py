import json
import os
import sys
import subprocess
import vertexai
from dotenv import load_dotenv
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp
from google.api_core import exceptions
from google.cloud import storage, secretmanager

# ── Environment selection ────────────────────────────────────────────────────
# Override by setting DEPLOYMENT_ENVIRONMENT=prod before running
environmentsuffix = os.getenv("DEPLOYMENT_ENVIRONMENT", "dev").lower()
load_dotenv(dotenv_path=f".env.{environmentsuffix}")

# ── Agent and Deployment Configuration ──────────────────────────────────────
PROJECT_ID                  = os.getenv("GCP_CLOUD_PROJECT", "")
GOOGLE_CLOUD_STAGING_BUCKET = os.getenv("GOOGLE_CLOUD_STAGING_BUCKET", "")
GOOGLE_CLOUD_LOCATION       = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
AGENT_NAME                  = os.getenv("AGENT_NAME", "a2ui-demo-agent")
AGENT_DISPLAY_NAME          = os.getenv("AGENT_DISPLAY_NAME", "A2UI Demo Agent")
AGENT_DESCRIPTION           = os.getenv("AGENT_DESCRIPTION", "ADK agent that emits A2UI follow-up buttons as a DataPart.")
BUCKET_NAME                 = os.getenv("BUCKET_NAME", "")
SECRET_NAME                 = os.getenv("SECRET_NAME", "")


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_secret_as_env_vars(project_id: str, secret_name: str) -> dict:
    """Retrieves a JSON secret from Secret Manager and returns its key/value
    pairs as a dict suitable for merging into env_vars.

    The secret payload is expected to be a JSON object, e.g.:
        {
            "GOOGLE_API_KEY": "...",
            "SOME_OTHER_VAR": "..."
        }

    Returns an empty dict if the secret is missing or cannot be parsed.
    """
    if not project_id or not secret_name:
        print("load_secret_as_env_vars: project_id and secret_name are required; skipping.")
        return {}
    try:
        client   = secretmanager.SecretManagerServiceClient()
        resource = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": resource})
        payload  = response.payload.data.decode("UTF-8")
        values   = json.loads(payload)
        if not isinstance(values, dict):
            print(f"load_secret_as_env_vars: secret '{secret_name}' is not a JSON object; skipping.")
            return {}
        print(f"load_secret_as_env_vars: loaded {len(values)} key(s) from secret '{secret_name}'.")
        return {k: str(v) for k, v in values.items()}
    except Exception as e:
        print(f"load_secret_as_env_vars: failed to load secret '{secret_name}': {e}")
        return {}


def create_gcs_bucket_if_not_exists():
    """Creates the GCS staging bucket if it does not already exist."""
    if not BUCKET_NAME or not PROJECT_ID:
        print("Error: BUCKET_NAME and GCP_CLOUD_PROJECT must be set in the .env file.")
        return
    print(f"Checking for GCS bucket '{BUCKET_NAME}' in project '{PROJECT_ID}'...")
    try:
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        if bucket.exists():
            print(f"Info: GCS bucket '{BUCKET_NAME}' already exists. No action taken.")
        else:
            new_bucket = storage_client.create_bucket(BUCKET_NAME, location=GOOGLE_CLOUD_LOCATION)
            print(f"Info: GCS bucket '{new_bucket.name}' created in '{GOOGLE_CLOUD_LOCATION}'.")
    except exceptions.Conflict:
        print(f"Info: GCS bucket '{BUCKET_NAME}' already exists (conflict). No action taken.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


# ── Pre-flight: ensure staging bucket exists ─────────────────────────────────
create_gcs_bucket_if_not_exists()

# ── Agent env vars ───────────────────────────────────────────────────────────
# Start with any vars that should always be set on the deployed agent
agent_env_vars: dict = {}

# Pull additional secrets from Secret Manager (if SECRET_NAME is configured)
if SECRET_NAME:
    agent_env_vars.update(load_secret_as_env_vars(PROJECT_ID, SECRET_NAME))

# Inject local env vars that start with AGENT_VAR_ (optional convention)
for key, value in os.environ.items():
    if key.startswith("AGENT_VAR_"):
        agent_env_vars[key.removeprefix("AGENT_VAR_")] = str(value)

print(
    f"Environment variables ({len(agent_env_vars)}) configured for the agent: "
    f"{sorted(agent_env_vars.keys())}"
)

# ── Continue with Agent Deployment ───────────────────────────────────────────
print(f"\nDeploying agent '{AGENT_DISPLAY_NAME}' to project '{PROJECT_ID}'...")

from agent.agent import root_agent  # noqa: E402 — import after env is set up

vertexai.init(project=PROJECT_ID, location=GOOGLE_CLOUD_LOCATION)

app = AdkApp(
    agent=root_agent,
    enable_tracing=True,
    staging_bucket=GOOGLE_CLOUD_STAGING_BUCKET,
)

# Check whether the agent already exists (match on display name)
agent = next(
    (a for a in agent_engines.list() if a.display_name == AGENT_DISPLAY_NAME),
    None,
)
print(
    f"Found agent! Resource name: {agent.resource_name}, "
    f"display name: {agent.display_name}, name: {agent.name}"
    if agent else "No existing agent found. Creating a new one..."
)

agent_requirements = [
    "google-cloud-aiplatform[agent_engines,adk]",
    "google-adk[a2a]>=2.2.0",
    "a2a-sdk>=0.3.4,<0.4",
    "python-dotenv>=1.0.0",
    "google-cloud-secret-manager",
    "google-cloud-storage",
]

if agent:
    print("Updating the existing agent...")
    remote_app = agent_engines.update(
        resource_name=agent.resource_name,
        display_name=agent.display_name,
        agent_engine=app,
        description=AGENT_DESCRIPTION,
        requirements=agent_requirements,
        extra_packages=["./agent"],
        env_vars=agent_env_vars,
    )
    print(f"=======> Success! Agent updated. Resource name is: {remote_app.resource_name}.")
else:
    print("Creating a new agent...")
    remote_app = agent_engines.create(
        agent_engine=app,
        requirements=agent_requirements,
        display_name=AGENT_DISPLAY_NAME,
        description=AGENT_DESCRIPTION,
        extra_packages=["./agent"],
        env_vars=agent_env_vars,
    )
    print(f"=======> Success! Agent deployed. Resource name is: {remote_app.resource_name}.")
