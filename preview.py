"""Save the input items Codex constructs for a new local prompt."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run Codex's experimental prompt-input diagnostic in a local workspace "
            "and save its JSON for import into Communication Inspector."
        ),
        epilog="This previews a new prompt. It does not run a model turn or recover past requests.",
    )
    parser.add_argument(
        "--workspace", type=Path, required=True, help="Existing working directory"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New JSON file to create"
    )
    parser.add_argument("--prompt", help="Optional prompt text")
    parser.add_argument(
        "--image",
        type=Path,
        action="append",
        default=[],
        help="Attach a local image (repeatable)",
    )
    options = parser.parse_args()

    workspace = options.workspace.resolve()
    if not workspace.is_dir():
        parser.error("--workspace must be an existing directory")
    output = options.output.absolute()
    if output.exists() or not output.parent.is_dir():
        parser.error("--output must name a new file in an existing directory")

    codex = shutil.which("codex.exe" if os.name == "nt" else "codex")
    if not codex:
        parser.error("The native Codex executable must be on PATH")

    command = [codex, "debug", "prompt-input"]
    for image in options.image:
        command.extend(("--image", str(image.resolve())))
    if options.prompt is not None:
        command.extend(("--", options.prompt))
    try:
        result = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            encoding="utf-8",
            timeout=60,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        parser.exit(
            1,
            f"Codex prompt-input failed. Check that your Codex version supports it.\n{error.stderr}",
        )
    except subprocess.TimeoutExpired:
        parser.exit(1, "Codex prompt-input timed out after 60 seconds.\n")
    except (OSError, UnicodeError) as error:
        parser.exit(1, f"Could not read the Codex prompt preview: {error}\n")

    try:
        items = json.loads(result.stdout)
    except ValueError:
        parser.exit(1, "Codex prompt-input did not return JSON.\n")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        parser.exit(1, "Codex prompt-input did not return an array of objects.\n")

    preview = {
        "format": "codex-prompt-preview",
        "version": 1,
        "workspace": str(workspace),
        "items": items,
    }
    try:
        with output.open("x", encoding="utf-8") as file:
            json.dump(preview, file, ensure_ascii=True, indent=2)
            file.write("\n")
    except OSError as error:
        parser.exit(1, f"Could not save the prompt preview: {error}\n")
    print(f"Saved Codex prompt preview to {output}")


if __name__ == "__main__":
    main()
