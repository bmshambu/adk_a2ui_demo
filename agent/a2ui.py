"""A2UI v0.8 payload helpers for Gemini Enterprise.

Gemini Enterprise renders A2UI v0.8 only, and expects each A2UI message as an
A2A *DataPart* (structured JSON) with metadata {"mimeType": "application/json+a2ui"}
— NOT as a file/blob attachment ("Unsupported attachment" otherwise).

ADK convention for emitting a custom A2A DataPart from agent code: wrap the
DataPart JSON in <a2a_datapart_json>...</a2a_datapart_json> inside a text/plain
inline_data blob. ADK's part converter (google.adk.a2a.converters.part_converter)
unwraps it into a real DataPart on the A2A wire.

v0.8 message sequence per response (one DataPart each):
    1. surfaceUpdate    — flat list of components, referenced by id
    2. dataModelUpdate  — data model (empty for static buttons)
    3. beginRendering   — signals client to render from the root component
"""
import json
import uuid

from google.genai import types as genai_types

A2UI_MIME_TYPE = "application/json+a2ui"
_TAG_START = b"<a2a_datapart_json>"
_TAG_END = b"</a2a_datapart_json>"


def followup_messages(prompt: str, buttons: list[dict]) -> list[dict]:
    """Builds the A2UI v0.8 message sequence for a prompt + follow-up buttons.

    A fresh surfaceId is generated on every call: the GE chat keys rendered
    cards by surfaceId, so reusing one makes later responses update the first
    card instead of rendering a new one (buttons would appear only once per
    conversation).

    Args:
        prompt: Text shown above the buttons.
        buttons: List of {"label": str, "action": str} dicts.
                 label  – button caption
                 action – follow-up question reported back via userAction
    """
    surface_id = f"followup-buttons-{uuid.uuid4().hex[:12]}"
    components = [
        {
            "id": "root",
            "component": {"Card": {"child": "content"}},
        },
        {
            "id": "content",
            "component": {
                "Column": {
                    "children": {
                        "explicitList": ["prompt_text"]
                        + [f"btn_{i}" for i in range(len(buttons))]
                    }
                }
            },
        },
        {
            "id": "prompt_text",
            "component": {"Text": {"text": {"literalString": prompt}}},
        },
    ]

    for i, b in enumerate(buttons):
        components.append(
            {
                "id": f"btn_{i}",
                "component": {
                    "Button": {
                        "child": f"btn_{i}_label",
                        "action": {
                            # Workaround test: use the question text as the
                            # action name — if the GE client displays the name
                            # for button clicks, the transcript shows the real
                            # question instead of "User action triggered."
                            # The agent reads the question from context either way.
                            "name": b["action"],
                            "context": [
                                {
                                    "key": "question",
                                    "value": {"literalString": b["action"]},
                                }
                            ],
                        },
                    }
                },
            }
        )
        components.append(
            {
                "id": f"btn_{i}_label",
                "component": {"Text": {"text": {"literalString": b["label"]}}},
            }
        )

    return [
        {"surfaceUpdate": {"surfaceId": surface_id, "components": components}},
        {"dataModelUpdate": {"surfaceId": surface_id, "contents": {}}},
        {"beginRendering": {"surfaceId": surface_id, "root": "root"}},
    ]


def references_modal(references: list[dict], title: str | None = None) -> list[dict]:
    """Builds an A2UI v0.8 message sequence showing references behind a Modal.

    The chat shows a single compact entry point ("View references (N)");
    clicking it opens an overlay listing all reference links — keeps the
    chat window clean even with 10+ references.

    Args:
        references: List of {"title": str, "url": str} dicts.
        title: Entry-point label; defaults to "View references (N)".
    """
    surface_id = f"references-{uuid.uuid4().hex[:12]}"
    label = title or f"View references ({len(references)})"

    components = [
        {
            "id": "root",
            "component": {
                "Modal": {
                    "entryPointChild": "entry_button",
                    "contentChild": "ref_list",
                }
            },
        },
        {
            "id": "entry_button",
            "component": {"Text": {"text": {"literalString": f"📚 {label}"}}},
        },
        {
            "id": "ref_list",
            "component": {
                "Column": {
                    "children": {
                        "explicitList": ["ref_header"]
                        + [f"ref_{i}" for i in range(len(references))]
                    }
                }
            },
        },
        {
            "id": "ref_header",
            "component": {
                "Text": {
                    "usageHint": "h3",
                    "text": {"literalString": "References"},
                }
            },
        },
    ]

    for i, ref in enumerate(references):
        # GE renders markdown links inside Text components
        components.append(
            {
                "id": f"ref_{i}",
                "component": {
                    "Text": {
                        "text": {
                            "literalString": f"{i + 1}. [{ref['title']}]({ref['url']})"
                        }
                    }
                },
            }
        )

    return [
        {"surfaceUpdate": {"surfaceId": surface_id, "components": components}},
        {"dataModelUpdate": {"surfaceId": surface_id, "contents": {}}},
        {"beginRendering": {"surfaceId": surface_id, "root": "root"}},
    ]


def to_genai_part(a2ui_message: dict) -> genai_types.Part:
    """Wraps one A2UI message so ADK emits it as an A2A DataPart.

    Produces the tagged text/plain blob that ADK's part converter unwraps
    into: DataPart(data=<a2ui_message>, metadata={"mimeType": A2UI_MIME_TYPE}).
    """
    data_part_json = json.dumps(
        {
            "kind": "data",
            "data": a2ui_message,
            "metadata": {"mimeType": A2UI_MIME_TYPE},
        }
    )
    return genai_types.Part(
        inline_data=genai_types.Blob(
            mime_type="text/plain",
            data=_TAG_START + data_part_json.encode("utf-8") + _TAG_END,
        )
    )


# ── Static follow-up set used by the demo agent ────────────────────────────
# Must be a function (not a module-level constant): each call generates a
# fresh surfaceId so every response renders its own button card in GE.
def demo_followups() -> list[dict]:
    return followup_messages(
        prompt="What would you like to explore next?",
        buttons=[
            {"label": "Tell me more",       "action": "Can you tell me more about that?"},
            {"label": "Give an example",    "action": "Can you give me a concrete example?"},
            {"label": "Summarize",          "action": "Please summarize the key points in bullet form"},
            {"label": "Why does it matter?", "action": "Why does this matter in a real-world context?"},
        ],
    )
