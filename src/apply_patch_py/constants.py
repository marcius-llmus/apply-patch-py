PATCH_FORMAT_INSTRUCTIONS = """
Use the `apply_patch` shell command to edit files.
Your patch language is a stripped‑down, file‑oriented diff format designed to be easy to parse and safe to apply. You can think of it as a high‑level envelope:

*** Begin Patch
[ one or more file sections ]
*** End Patch

Within that envelope, you get a sequence of file operations.
You MUST include a header to specify the action you are taking.
Each operation starts with one of three headers:

*** Add File: <path> - create a new file. Every following line is a + line (the initial contents).
*** Delete File: <path> - remove an existing file. Nothing follows.
*** Update File: <path> - patch an existing file in place (optionally with a rename).

May be immediately followed by *** Move to: <new path> if you want to rename the file.
Then one or more “hunks”, each introduced by @@ (optionally followed by a hunk header).
Within a hunk each line starts with:

For instructions on [context_before] and [context_after]:
- By default, include 2‑5 lines of unchanged code immediately above and below each change.
  If a change is within a few lines of a previous change, do NOT duplicate the previous change’s post‑context as the next change’s pre‑context.
- The @@ marker is a literal anchor: the text after @@ must match an entire line in the target file.
  Do NOT put labels or descriptions after @@ unless those exact characters appear as a full line.
  Prefer anchoring to an existing definition line that already exists.
- If 3 lines of context is insufficient to uniquely identify the snippet of code within the file, use the @@ operator to indicate the class or function to which the snippet belongs. For instance, we might have:
@@ class BaseClass
[3 lines of pre-context]
- [old_code]
+ [new_code]
[3 lines of post-context]

- If a code block is repeated so many times in a class or function such that even a single `@@` statement and 3 lines of context cannot uniquely identify the snippet of code, you can use multiple `@@` statements to jump to the right context. For instance:

@@ class BaseClass
@@ 	 def method():
[3 lines of pre-context]
- [old_code]
+ [new_code]
[3 lines of post-context]

The full grammar definition is below:
Patch := Begin { FileOp } End
Begin := "*** Begin Patch" NEWLINE
End := "*** End Patch" NEWLINE
FileOp := AddFile | DeleteFile | UpdateFile
AddFile := "*** Add File: " path NEWLINE { "+" line NEWLINE }
DeleteFile := "*** Delete File: " path NEWLINE
UpdateFile := "*** Update File: " path NEWLINE [ MoveTo ] { Hunk }
MoveTo := "*** Move to: " newPath NEWLINE
Hunk := "@@" [ header ] NEWLINE { HunkLine } [ "*** End of File" NEWLINE ]
HunkLine := (" " | "-" | "+") text NEWLINE

A full patch can combine several operations:

*** Begin Patch
*** Add File: hello.txt
+Hello world
*** Update File: src/app.py
*** Move to: src/main.py
@@ def greet():
-print("Hi")
+print("Hello, world!")
*** Delete File: obsolete.txt
*** End Patch

It is important to remember and follow strictly:

- You must include a header with your intended action (Add/Delete/Update)
- You must prefix new lines with `+` even when creating a new file
- File references can only be relative, NEVER ABSOLUTE.
- Avoid single‑line update hunks unless the line is unique.
- Order update hunks from top to bottom in the file.
- Each update chunk begins with an optional `@@` context marker. Prefer using `@@` whenever the surrounding
  code may appear multiple times in the file.
- The `@@` marker is used as a literal anchor line. It must match a full line in the target file (after trimming
  leading/trailing whitespace).
- When using multiple update hunks within the same file, hunks must be ordered strictly from top to bottom in the file.
  If a later hunk targets lines that appear earlier than a previous hunk, it may fail to apply.
- When you include multiple hunks for the same file, order them strictly from top to bottom in the file.
- Your patch hunks MUST be ordered from top to bottom in the file.
- When a change targets a line that appears multiple times, you MUST disambiguate by using an @@ context marker
  (e.g. "@@ # region: duplication and shadowing") so the patch applies to the intended occurrence.
  The text after "@@" MUST match a full line in the file.
- Do NOT include duplicate hunks for the same change.
"""
