"""Helpers for building A2UI payloads (application/json+a2ui MIME type)."""
import json


def followup_buttons(prompt: str, buttons: list[dict]) -> dict:
    """Build a Card payload with a prompt text and clickable buttons.

    Args:
        prompt: Text shown above the buttons (e.g. "What would you like next?")
        buttons: List of {"label": str, "action": str} dicts.
                 label  – displayed on the button
                 action – exact text injected as the next user message on click
    """
    return {
        "type": "Card",
        "children": [
            {"type": "Text", "value": prompt},
            *[{"type": "Button", "label": b["label"], "action": b["action"]} for b in buttons],
        ],
    }


def encode(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


# ── Static follow-up set used by the demo agent ────────────────────────────
DEMO_FOLLOWUPS = followup_buttons(
    prompt="What would you like to explore next?",
    buttons=[
        {"label": "Tell me more",      "action": "Can you tell me more about that?"},
        {"label": "Give an example",   "action": "Can you give me a concrete example?"},
        {"label": "Summarize",         "action": "Please summarize the key points in bullet form"},
        {"label": "Why does it matter?","action": "Why does this matter in a real-world context?"},
    ],
)
