"""Optional bring-your-own-key assistant.

Nothing here writes to the user's working copy. The module builds a small,
bounded prompt from one column (name, detected type, issue kinds and at most
twelve short sample values), calls the user's chosen OpenAI-compatible provider
with the user's own key, and returns a suggestion for review. The key is used
for one request and is never stored, echoed or logged. Applying any suggestion
still goes through the existing previewed decision, audit and undo path.
"""
import json
import os
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..core.common import missing

PROVIDERS = {
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.0-flash",
    ),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "meta-llama/llama-3.3-70b-instruct:free",
    ),
}
COLUMN_TYPES = [
    "text",
    "identifier",
    "category",
    "numeric",
    "location",
    "currency",
    "percentage",
    "boolean",
    "date",
    "datetime",
    "time",
    "duration",
    "phone",
    "email",
    "coordinate",
    "url",
    "ip",
]
MODEL_PATTERN = re.compile(r"[A-Za-z0-9._:/-]{1,100}")
MAX_SAMPLES = 12
MAX_SAMPLE_LENGTH = 120


class AssistRequest(BaseModel):
    file_id: str = Field(min_length=36, max_length=36)
    column: str = Field(min_length=1, max_length=512)
    provider: str = Field(min_length=3, max_length=20)
    key: str = Field(min_length=8, max_length=4096)
    model: str = Field(default="", max_length=100)
    mode: str = Field(default="suggest_type", pattern="^(suggest_type|explain)$")
    message: str = Field(default="", max_length=600)
    consent: bool = False

    @field_validator("provider")
    @classmethod
    def known_provider(cls, value):
        if value not in PROVIDERS:
            raise ValueError("Choose one of the supported providers")
        return value

    @field_validator("model")
    @classmethod
    def sane_model(cls, value):
        if value and not MODEL_PATTERN.fullmatch(value):
            raise ValueError("The model name contains unsupported characters")
        return value


def _samples(record, column):
    frame = record.get("editor_df")
    if frame is None:
        frame = record.get("df")
    if frame is None or column not in frame.columns:
        raise ValueError("Unknown column")
    values = []
    for value in frame[column]:
        if missing(value):
            continue
        text = " ".join(str(value).split())[:MAX_SAMPLE_LENGTH]
        if not text or text in values:
            continue
        values.append(text)
        if len(values) >= MAX_SAMPLES:
            break
    if not values:
        raise ValueError("This column has no sample values to describe")
    return values


def _issue_kinds(record, column):
    counts = {}
    for cells in (record.get("workflow_annotations") or {}).get(column, {}).values():
        for flag in cells:
            kind = flag.get("kind", "")
            if kind:
                counts[kind] = counts.get(kind, 0) + 1
    return sorted(counts, key=counts.get, reverse=True)[:6]


def _ask(base, key, model, messages, timeout=30):
    try:
        response = httpx.post(
            base.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": 400,
            },
            timeout=timeout,
            follow_redirects=False,
        )
    except httpx.HTTPError:
        raise HTTPException(
            504,
            "The AI provider did not respond in time. Try again or use manual settings.",
        ) from None
    if response.status_code in (401, 403):
        raise HTTPException(
            422, "The provider rejected this key. Check the key and try again."
        )
    if response.status_code == 429:
        raise HTTPException(
            429, "The provider is rate-limiting this key. Wait a minute and retry."
        )
    if response.status_code >= 400:
        raise HTTPException(
            502,
            "The AI provider returned an error. Try again or use manual settings.",
        )
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(
            502,
            "The provider returned an unreadable answer. Try again or use manual settings.",
        ) from None
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(502, "The provider returned an empty answer.")
    return content.strip()


def _json_object(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise HTTPException(
            502, "The provider did not return a usable suggestion."
        )
    try:
        return json.loads(text[start : end + 1])
    except ValueError:
        raise HTTPException(
            502, "The provider did not return a usable suggestion."
        ) from None


def install_assist(app, store):
    router = APIRouter(prefix="/api")

    @router.post("/assist")
    def assist(body: AssistRequest, request: Request):
        if os.getenv("AI_ASSIST_ENABLED", "true").lower() != "true":
            raise HTTPException(
                403, "The optional AI assistant is turned off on this server."
            )
        if not body.consent:
            raise HTTPException(
                422,
                "Confirm that the selected column samples may be sent to your provider.",
            )
        record = store.get(body.file_id, request.state.session)
        samples = _samples(record, body.column)
        rules = (record.get("column_rules") or {}).get(body.column, {})
        profile = next(
            (
                column
                for column in (
                    record.get("editor_profile") or record.get("profile") or {}
                ).get("columns", [])
                if column.get("column_name") == body.column
            ),
            {},
        )
        detected = profile.get("detected_type") or "unknown"
        declared = rules.get("type") or "none"
        base, default_model = PROVIDERS[body.provider]
        model = body.model or default_model
        if body.mode == "suggest_type":
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You review spreadsheet columns. Reply with one JSON object only, "
                        'shape {"type": "...", "rationale": "..."}. Never invent data.'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Column: {body.column!r}\n"
                        f"Automatically detected type: {detected}\n"
                        f"Type declared by the user: {declared}\n"
                        f"Issue kinds: {', '.join(_issue_kinds(record, body.column)) or 'none'}\n"
                        f"Sample values: {json.dumps(samples, ensure_ascii=False)}\n"
                        f"Choose exactly one type from: {', '.join(COLUMN_TYPES)}.\n"
                        "Treat labels as reviewable suggestions, not facts. "
                        "Keep the rationale under 240 characters."
                    ),
                },
            ]
            data = _json_object(_ask(base, body.key, model, messages))
            suggested = str(data.get("type", "")).strip().lower()
            if suggested not in COLUMN_TYPES:
                raise HTTPException(
                    502,
                    "The provider suggested a type DataNeat does not support. "
                    "Try again or use manual settings.",
                )
            rationale = str(data.get("rationale", "")).strip()[:400]
            return {
                "mode": "suggest_type",
                "provider": body.provider,
                "model": model,
                "suggestion": {"type": suggested, "rationale": rationale},
            }
        if not body.message.strip():
            raise HTTPException(422, "Provide the finding you want explained.")
        messages = [
            {
                "role": "system",
                "content": (
                    "You explain spreadsheet review findings to non-technical users. "
                    "Reply in plain text, at most 80 words. Do not invent facts and "
                    "do not tell the user a finding is wrong without evidence."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Column: {body.column!r}\n"
                    f"Detected type: {detected}\n"
                    f"Finding: {body.message}\n"
                    f"Sample values: {json.dumps(samples, ensure_ascii=False)}"
                ),
            },
        ]
        explanation = _ask(base, body.key, model, messages)[:800]
        return {
            "mode": "explain",
            "provider": body.provider,
            "model": model,
            "explanation": explanation,
        }

    app.include_router(router)
