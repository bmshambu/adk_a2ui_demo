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

from google.genai import types as genai_types

A2UI_MIME_TYPE = "application/json+a2ui"
_TAG_START = b"<a2a_datapart_json>"
_TAG_END = b"</a2a_datapart_json>"

SURFACE_ID = "followup-buttons-surface"


def followup_messages(prompt: str, buttons: list[dict]) -> list[dict]:
    """Builds the A2UI v0.8 message sequence for a prompt + follow-up buttons.

    Args:
        prompt: Text shown above the buttons.
        buttons: List of {"label": str, "action": str} dicts.
                 label  – button caption
                 action – follow-up question reported back via userAction
    """
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
                            "name": "followup_question",
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
        {"surfaceUpdate": {"surfaceId": SURFACE_ID, "components": components}},
        {"dataModelUpdate": {"surfaceId": SURFACE_ID, "contents": {}}},
        {"beginRendering": {"surfaceId": SURFACE_ID, "root": "root"}},
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
DEMO_FOLLOWUPS = followup_messages(
    prompt="What would you like to explore next?",
    buttons=[
        {"label": "Tell me more",       "action": "Can you tell me more about that?"},
        {"label": "Give an example",    "action": "Can you give me a concrete example?"},
        {"label": "Summarize",          "action": "Please summarize the key points in bullet form"},
        {"label": "Why does it matter?", "action": "Why does this matter in a real-world context?"},
    ],
)
