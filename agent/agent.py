"""Google ADK agent that emits A2UI v0.8 follow-up buttons for Gemini Enterprise.

The after_model_callback appends the A2UI message sequence (surfaceUpdate,
dataModelUpdate, beginRendering) to the model's final text response. Each
message rides as an A2A DataPart with mimeType application/json+a2ui, which
Gemini Enterprise renders natively as clickable buttons.

When a button is clicked, GE sends back a userAction event containing the
chosen follow-up question in context.question — the instruction below tells
the model how to handle that input.
"""
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

from .a2ui import DEMO_FOLLOWUPS, to_genai_part


def _append_a2ui_parts(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Appends the A2UI v0.8 DataParts to every final text response."""
    # Skip streaming chunks — only act on the complete response
    if llm_response.partial:
        return None

    content = llm_response.content
    if not content or not content.parts:
        return None

    # Skip tool-call responses — only attach buttons to user-facing text
    has_text = any(p.text for p in content.parts if p.text)
    has_function_call = any(p.function_call for p in content.parts if p.function_call)
    if not has_text or has_function_call:
        return None

    for message in DEMO_FOLLOWUPS:
        content.parts.append(to_genai_part(message))
    return llm_response


root_agent = LlmAgent(
    name="a2ui_demo_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are a helpful, concise assistant. "
        "Answer every question clearly in 2-4 sentences. "
        "Do not mention follow-up options in your text — they are shown as "
        "interactive buttons below your response. "
        "If the user message contains a JSON userAction event with a "
        "'question' value in its context, treat that question text as the "
        "user's message and answer it directly."
    ),
    after_model_callback=_append_a2ui_parts,
)
