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

from .a2ui import (
    clicked_card_replacement,
    demo_followups,
    extract_user_action,
    references_modal,
    to_genai_part,
)

# Static references for testing the Modal pattern. In the real agent these
# would come from the retrieval/tool results for the current turn.
DEMO_REFERENCES = [
    {"title": "ISA 315 — Identifying and Assessing Risks", "url": "https://www.iaasb.org/publications/isa-315"},
    {"title": "COSO Internal Control Framework", "url": "https://www.coso.org/guidance-on-ic"},
    {"title": "NIST Cybersecurity Framework 2.0", "url": "https://www.nist.gov/cyberframework"},
    {"title": "ISO 27001:2022 Overview", "url": "https://www.iso.org/standard/27001"},
    {"title": "PCAOB AS 2110 — Risk Assessment", "url": "https://pcaobus.org/oversight/standards/auditing-standards/details/AS2110"},
    {"title": "GDPR Article 32 — Security of Processing", "url": "https://gdpr-info.eu/art-32-gdpr/"},
    {"title": "Basel III Framework Summary", "url": "https://www.bis.org/basel_framework/"},
    {"title": "OWASP Top 10 (2025)", "url": "https://owasp.org/Top10/"},
    {"title": "SOC 2 Trust Services Criteria", "url": "https://www.aicpa-cima.com/topic/audit-assurance/soc-2"},
    {"title": "EU AI Act — Compliance Checklist", "url": "https://artificialintelligenceact.eu/"},
]


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

    # If this turn was triggered by a button click, rewrite the clicked
    # button card in place to show the chosen question — mitigates GE's
    # fixed "User action triggered." bubble by making the card itself
    # display what was selected.
    user_action = extract_user_action(callback_context.user_content)
    if user_action:
        question = (user_action.get("context") or {}).get("question")
        surface_id = user_action.get("surfaceId")
        if question and surface_id:
            for message in clicked_card_replacement(surface_id, question):
                content.parts.append(to_genai_part(message))

    # References behind a Modal (compact entry point keeps the chat clean),
    # then the follow-up buttons card
    for message in references_modal(DEMO_REFERENCES):
        content.parts.append(to_genai_part(message))
    for message in demo_followups():
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
        "user's message. In that case, begin your reply by restating the "
        "question on its own line formatted as a markdown quote (e.g. "
        "'> Can you tell me more about that?'), then answer it. This is "
        "needed because the chat UI shows a generic label for button clicks."
    ),
    after_model_callback=_append_a2ui_parts,
)
