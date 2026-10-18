"""Export bounded check evidence with unpredictable output delimiters."""
import os
from pathlib import Path
import sys
import uuid


def main():
    name, filename, status = sys.argv[1:]
    path = Path(filename)
    content = path.read_text(errors="replace") if path.exists() else "No check log was produced."
    content = "\n".join(content.splitlines()[-120:])[-16000:]
    delimiter = "REPORT_" + uuid.uuid4().hex
    output_text = f"{name}_status={status}\n{name}<<{delimiter}\n{content}\n{delimiter}\n"
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(output_text)
    else:
        sys.stdout.write(output_text)


if __name__ == "__main__":
    main()
