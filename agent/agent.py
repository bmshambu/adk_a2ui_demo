"""Google ADK agent that emits A2UI follow-up buttons as a DataPart.

The after_model_callback appends an application/json+a2ui Part to the model's
final text response.  This is exactly the payload that Gemini Enterprise reads
and renders as clickable buttons — no server-side post-processing needed.
"""
import json
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .a2ui import DEMO_FOLLOWUPS, encode


def _append_a2ui_part(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Appends A2UI DataPart to every final text response from the model.

    Skips streaming chunks (partial=True) and tool-call responses so the
    A2UI card only appears once, after the complete answer.
    """
    # Skip streaming chunks — only act on the complete response
    if llm_response.partial:
        return None

    content = llm_response.content
    if not content or not content.parts:
        return None

    # Skip if this response is a function/tool call (no text yet)
    has_text = any(p.text for p in content.parts if p.text)
    has_function_call = any(p.function_call for p in content.parts if p.function_call)
    if not has_text or has_function_call:
        return None

    a2ui_part = types.Part(
        inline_data=types.Blob(
            mime_type="application/json+a2ui",
            data=encode(DEMO_FOLLOWUPS),
        )
    )
    content.parts.append(a2ui_part)
    return llm_response


root_agent = LlmAgent(
    name="a2ui_demo_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are a helpful, concise assistant. "
        "Answer every question clearly in 2-4 sentences. "
        "Do not mention follow-up options in your text — they are shown as "
        "interactive buttons below your response."
    ),
    after_model_callback=_append_a2ui_part,
)
