import argparse
import sys
import asyncio
from pathlib import Path
from .applier import PatchApplier


async def run_apply_patch(patch_text: str) -> int:
    try:
        affected = await PatchApplier.apply(patch_text, Path("."))
        print("Success. Updated the following files:")
        for path in affected.added:
            print(f"A {path}")
        for path in affected.modified:
            print(f"M {path}")
        for path in affected.deleted:
            print(f"D {path}")
        return 0
    except Exception as e:
        print(f"{e}", file=sys.stderr)
        return 1
    except BaseException as e:
        # Catch-all for non-Exception errors (excluding SystemExit which is handled by caller/Python)
        if isinstance(e, SystemExit):
            raise
        print(f"{e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Apply a patch to files.")
    parser.add_argument(
        "patch", nargs="?", help="The patch content. If omitted, reads from stdin."
    )

    args = parser.parse_args()

    if args.patch:
        patch_text = args.patch
    else:
        if sys.stdin.isatty():
            parser.print_help()
            sys.exit(2)
        patch_text = sys.stdin.read()

    try:
        sys.exit(asyncio.run(run_apply_patch(patch_text)))
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
