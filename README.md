# apply-patch-py

Apply **Codex-style patch blocks** to a working directory.

This project is heavily inspired by (and effectively a Python port of) the patching mechanism used by **OpenAI Codex** and tools in that ecosystem.
Some tools (including **Codex** and **opencode**) already use this patch format; this implementation aims to be **more forgiving** and will try harder to apply *slightly malformed* patches by using whitespace/normalization fallbacks.

## What it does

`apply-patch-py` consumes patch text shaped like:

```diff
*** Begin Patch
*** Update File: path/to/file.txt
@@
-old line
+new line
*** End Patch
```

Supported operations:

- `*** Add File: {path}`
- `*** Delete File: {path}`
- `*** Update File: {path}` (optionally with `*** Move to: {new_path}`)

## Why it exists

LLMs sometimes emit patches that are:

- missing exact whitespace matches
- slightly different punctuation (e.g. Unicode dashes/quotes)
- otherwise "close enough" to the file content

This tool attempts to apply the patch anyway using increasingly forgiving matching strategies (exact match  rstrip match  trim match  normalized match).

## Install

From PyPI:

```bash
uv tool install apply-patch-py
```

Or run without installing:

```bash
uvx apply-patch-py "*** Begin Patch
*** End Patch"
```

## Usage

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

```diff
Success. Updated the following files:
A hello.txt
M existing.txt
D obsolete.txt
```

## Patch format examples

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

## Development

### Run tests

```bash
uv run pytest
```

### Integration tests (LLM providers)

This repo also contains integration tests that validate patch generation via real LLM providers.
They are **skipped by default** unless explicitly selected:
+
```bash
uv run pytest -m integration
```

See `tests/integration/` for provider configuration.

## Notes on lineage

- The patch format and workflow are **directly inspired by OpenAI Codex** diff patching.
- Some other tools (e.g. opencode) emit the same format.
- This project is essentially a **port** with a few pragmatic changes to improve success rates on imperfect LLM output.

## License

MIT. See [LICENSE](LICENSE).
