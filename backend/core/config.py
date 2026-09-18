"""Application configuration."""

from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()


def get_groq_api_key() -> str:
    """Return the configured Groq API key."""

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    return api_key


def get_groq_model() -> str:
    """Return the configured Groq model."""

    model = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b",
    )

    return model