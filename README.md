# apply-patch-py

Apply **Codex-style patch blocks** to a working directory.

This project is heavily inspired by (and effectively a Python port of) the patching mechanism used by **Codex**. Some tools (including **Codex** and **opencode**) already emit this patch format; this implementation aims to be **more forgiving** and will try harder to apply *slightly malformed* patches by using whitespace/normalization fallbacks and an additional “anchor line” fallback.

The CLI exists and is useful for quick manual runs, but the primary intent is to use this package as the **patch-application backend for agent tools and MCP**

---


`apply-patch-py` consumes patch text shaped like:

```
*** Begin Patch
*** Update File: path/to/file.txt
@@
-old line
+new line
*** End Patch
```

Supported operations:

- `*** Add File: <path>`
- `*** Delete File: <path>`
- `*** Update File: <path>` (optionally with `*** Move to: <new_path>`)

---

LLMs sometimes emit patches that are “almost correct” but fail strict application due to:

- whitespace drift
- minor punctuation differences (Unicode quotes/dashes)
- slightly malformed hunks

This library tries strict matching first (OpenAI models will match almost everytime, strictly), then progressively relaxes how it matches context lines:

1. **Exact match**
2. **Right-stripped match** (`rstrip`)
3. **Trimmed match** (`strip`)
4. **Normalized match** (Unicode punctuation normalization + whitespace normalization)

---

### Install

From PyPI:

```bash
uv add apply-patch-py
```

Or run without installing:

```bash
uvx apply-patch-py "*** Begin Patch
*** End Patch"
```

---

### PydanticAI tool Example

You can try it from examples folder:

```bash
# 1) Clone and run the example
git clone https://github.com/marcius-llmus/apply-patch-py
cd apply-patch-py

# Provide your LLM key (example: OpenAI)
export OPENAI_API_KEY="sk-proj-..."

# Run the example with uv
uv run examples/pydantic_example/pydantic_example.py
```

Then you can start asking edits to files inside `example_repo` folder.

For example: 

```
Request> Create a new file named "notes/hello.txt" with the content:
hello from the patch tool
```
or
```
Request> Remove content "xyz" from existing_file.txt 123
```
or
```
Request> Edit file xyz, remove the middle block.
```


---

### Direct usage

You can also call the library directly:

```python
import asyncio

from apply_patch_py import apply_patch

patch = """\
*** Begin Patch
*** Add File: hello.txt
+hello
*** End Patch
"""

async def main() -> None:
    affected = await apply_patch(patch)
    assert affected.success

asyncio.run(main())
```

---

### CLI usage

Apply a patch provided as a command-line argument:

```bash
apply-patch-py "*** Begin Patch
*** Add File: hello.txt
+hello\n
*** End Patch"
```

Apply a patch from stdin:

```bash
cat patch.txt | apply-patch-py
```

The CLI prints a summary of affected files:

```text
Success. Updated the following files:
A hello.txt
M existing.txt
D obsolete.txt
```


### Add a file

```diff
*** Begin Patch
*** Add File: nested/new.txt
+created
*** End Patch
```

### Delete a file

```diff
*** Begin Patch
*** Delete File: obsolete.txt
*** End Patch
```

### Update a file (single hunk)

```diff
*** Begin Patch
*** Update File: modify.txt
@@
-line2
+changed
*** End Patch
```

### Update a file (multiple hunks)

```diff
*** Begin Patch
*** Update File: multi.txt
@@
-line2
+changed2
@@
-line4
+changed4
*** End Patch
```

### Rename/move a file while updating

```diff
*** Begin Patch
*** Update File: old/name.txt
*** Move to: renamed/dir/name.txt
@@
-old content
+new content
*** End Patch
```

---

### Run tests

```bash
uv run pytest
```

### Integration tests (LLM providers)

This repo also contains integration tests that validate patch generation via real LLM providers. They are **skipped by default** unless explicitly selected:

```bash
uv run pytest -m integration
```

See `tests/integration/` for provider configuration.

---

## Notes

- The patch format and workflow are **directly inspired by OpenAI Codex** diff patching.
- Some other tools (e.g. opencode) emit the same format.
- This project is essentially a **port** from their rust patcher with a few changes to improve success rates on imperfect LLM output.

---

## License

MIT. See [LICENSE](LICENSE).
