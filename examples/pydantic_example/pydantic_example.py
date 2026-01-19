import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, Optional

from pydantic_ai import Agent, RunContext, Tool

from apply_patch_py import apply_patch
from apply_patch_py.utils import (
    get_patch_format_instructions,
    get_patch_format_tool_instructions,
)


@dataclass(frozen=True)
class Deps:
    workspace: Path


EXAMPLE_ROOT = Path(__file__).resolve().parent / "example_repo"


async def list_files_tool(ctx: RunContext[Deps], glob: str = "*") -> list[str]:
    """List files under the current workspace.

    Args:
        ctx: Run context containing dependencies. Uses `ctx.deps.workspace` as the root directory.
        glob: Glob pattern relative to `workspace` used to select files.

    Returns:
        A sorted list of relative paths (POSIX-style).
    """
    root = ctx.deps.workspace.resolve()
    paths = [
        p.relative_to(root).as_posix()
        for p in root.glob(glob)
        if p.is_file()
    ]
    return sorted(paths)


async def read_file_tool(ctx: RunContext[Deps], path: str) -> str:
    """Read a UTF-8 text file from the workspace.

    Args:
        ctx: Run context containing dependencies. Uses `ctx.deps.workspace` as the root directory.
        path: File path relative to `workspace`.

    Returns:
        The file contents as UTF-8 text.
    """
    root = ctx.deps.workspace.resolve()
    target = (root / path).resolve()
    if root != target and root not in target.parents:
        raise ValueError("Path must be within the workspace")
    return target.read_text(encoding="utf-8")


async def apply_patch_tool(ctx: RunContext[Deps], patch: str) -> int:
    """Apply a Codex-style patch to the workspace.

    Args:
        ctx: Run context containing dependencies. Uses `ctx.deps.workspace` as the root directory.
        patch: The patch text to apply. Must follow these instructions exactly:
            {get_patch_format_instructions()}

    Returns:
        0 on success, 1 on failure.
    """
    print("\n--- PATCH RECEIVED BY TOOL (BEGIN) ---\n")
    print(patch.rstrip())
    print("\n--- PATCH RECEIVED BY TOOL (END) ---\n")

    affected = await apply_patch(patch, workdir=ctx.deps.workspace)
    return 0 if affected.success else 1


LIST_FILES_TOOL = Tool(
    list_files_tool,
    takes_ctx=True,
    docstring_format="google",
    require_parameter_descriptions=True,
    description="List files in the workspace. Use this to discover what exists before reading or patching.",
)

READ_FILE_TOOL = Tool(
    read_file_tool,
    takes_ctx=True,
    docstring_format="google",
    require_parameter_descriptions=True,
    description="Read a text file from the workspace. Use this to fetch exact contents before producing a patch.",
)

APPLY_PATCH_TOOL = Tool(
    apply_patch_tool,
    takes_ctx=True,
    docstring_format="google",
    require_parameter_descriptions=True,
    description=get_patch_format_tool_instructions(),
)


async def run_agent_loop() -> NoReturn:
    deps = Deps(workspace=EXAMPLE_ROOT)
    message_history: Optional[list] = None
    system_prompt = (
        "You are a coding agent working in a local workspace. "
        "Use list_files and read_file to inspect. "
        "When you are ready to make changes, use apply_patch\n\n"
        "Patch format rules:\n"
        f"{get_patch_format_instructions()}\n"
    )

    agent = Agent(
        "openai:gpt-5.2",  # any supported provider model
        deps_type=Deps,
        tools=[LIST_FILES_TOOL, READ_FILE_TOOL, APPLY_PATCH_TOOL],
        system_prompt=system_prompt,
    )

    print("Interactive patching session. Press Ctrl+C to exit.")
    print(f"Workspace: {deps.workspace}")

    while True:
        try:
            user_request = input("\nRequest> ").strip()
        except EOFError:
            raise KeyboardInterrupt

        if not user_request:
            continue

        result = await agent.run(user_request, deps=deps, message_history=message_history)
        message_history = result.all_messages()
        print(result.output)


async def main() -> None:
    try:
        await run_agent_loop()
    except KeyboardInterrupt:
        print("\nExiting.")
        raise SystemExit(0)


if __name__ == "__main__":
    asyncio.run(main())
