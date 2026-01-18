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
        print(str(e), file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Apply a patch to files.")
    parser.add_argument("patch_file", nargs="?", help="Path to the patch file. If omitted, reads from stdin.")
    
    args = parser.parse_args()
    
    if args.patch_file:
        with open(args.patch_file, "r", encoding="utf-8") as f:
            patch_text = f.read()
    else:
        if sys.stdin.isatty():
            parser.print_help()
            sys.exit(2)
        patch_text = sys.stdin.read()

    sys.exit(asyncio.run(run_apply_patch(patch_text)))