import os
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, Tool

from apply_patch_py import apply_patch as apply_patch_api
from apply_patch_py.utils import get_patch_format_instructions

from providers import ANTHROPIC_SPEC, GEMINI_SPEC, OPENAI_SPEC


class ApplyPatchResult(BaseModel):
    exit_code: int


def _apply_patch_test_system_prompt() -> str:
    return (
        "You are given a tool to apply patches to a working directory. "
        "Always generate a patch that follows these exact instructions:\n\n"
        f"{get_patch_format_instructions()}\n\n"
        "Call the tool exactly once."
    )


async def apply_patch_tool(ctx: RunContext[Path], patch: str) -> int: # noqa
    """Apply a patch to the current workspace.

    Args:
        patch: The patch text to apply.
            Must follow these instructions exactly:
            {get_patch_format_instructions()}
    """

    affected = await apply_patch_api(patch, workdir=ctx.deps)
    return 0 if affected.success else 1


APPLY_PATCH_TOOL = Tool(
    apply_patch_tool,
    takes_ctx=True,
    docstring_format="google",
    require_parameter_descriptions=True,
)


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason=(
        "skipping openai integration tests: requires OPENAI_API_KEY"
    ),
)
@pytest.mark.integration
def test_openai_can_call_apply_patch_tool(tmp_path):
    agent = Agent( # noqa
        OPENAI_SPEC.model,
        deps_type=Path,
        output_type=ApplyPatchResult,
        tools=[APPLY_PATCH_TOOL],
        system_prompt=_apply_patch_test_system_prompt(),
    )

    result = agent.run_sync(
        "Create a file named 'hello.txt' with content 'hello'. Return exit_code.",
        deps=tmp_path,
    )
    assert result.output.exit_code == 0
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello\n"


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason=(
        "skipping anthropic integration tests: requires ANTHROPIC_API_KEY"
    ),
)
@pytest.mark.integration
def test_anthropic_can_call_apply_patch_tool(tmp_path):
    agent = Agent( # noqa
        ANTHROPIC_SPEC.model,
        deps_type=Path,
        output_type=ApplyPatchResult,
        tools=[APPLY_PATCH_TOOL],
        system_prompt=_apply_patch_test_system_prompt(),
    )

    result = agent.run_sync(
        "Create a file named 'hello.txt' with content 'hello'. Return exit_code.",
        deps=tmp_path,
    )
    assert result.output.exit_code == 0
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello\n"


@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason=(
        "skipping gemini integration tests: requires GEMINI_API_KEY"
    ),
)
@pytest.mark.integration
def test_gemini_can_call_apply_patch_tool(tmp_path):
    agent = Agent( # noqa
        GEMINI_SPEC.model,
        deps_type=Path,
        output_type=ApplyPatchResult,
        tools=[APPLY_PATCH_TOOL],
        system_prompt=_apply_patch_test_system_prompt(),
    )

    result = agent.run_sync(
        "Create a file named 'hello.txt' with content 'hello'. Return exit_code.",
        deps=tmp_path,
    )
    assert result.output.exit_code == 0
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello\n"
