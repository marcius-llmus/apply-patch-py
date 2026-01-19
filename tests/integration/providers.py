from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    model: str
    required_env: str


OPENAI_SPEC = ProviderSpec(
    name="openai", model="openai:gpt-5.2", required_env="OPENAI_API_KEY"
)
ANTHROPIC_SPEC = ProviderSpec(
    name="anthropic",
    model="anthropic:claude-sonnet-4-5-20250929",
    required_env="ANTHROPIC_API_KEY",
)
GEMINI_SPEC = ProviderSpec(
    name="gemini",
    model="google-gla:gemini-3-flash-preview",
    required_env="GOOGLE_API_KEY",
)
