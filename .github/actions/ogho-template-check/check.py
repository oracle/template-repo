#!/usr/bin/env python3
"""Validate the GCAS template checks for the repository in GITHUB_WORKSPACE."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REQUIRED_FILES = ("LICENSE.txt", "README.md", "SECURITY.md")
OCA_URL = "https://oca.opensource.oracle.com"
REPOSITORY_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

README_SECTIONS = (
    ("Installation", frozenset(("installation", "how to run", "getting started"))),
    ("Documentation", frozenset(("documentation",))),
    ("Examples", frozenset(("examples",))),
    ("Help", frozenset(("help",))),
    ("Contributing", frozenset(("contributing",))),
    ("Security", frozenset(("security",))),
    ("License", frozenset(("license",))),
)

CONTRIBUTING_SECTIONS = (
    "opening issues",
    "contributing code",
    "pull request process",
    "code of conduct",
)


@dataclass(frozen=True)
class Result:
    name: str
    passed: bool
    message: str
    file: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--repository-name", default="")
    parser.add_argument("--default-branch", default="")
    parser.add_argument(
        "--contributing-policy",
        choices=("optional", "required", "disabled"),
        default="optional",
        help=(
            "Whether CONTRIBUTING.md is optional, required locally, or ignored. "
            "An optional local file is validated when present."
        ),
    )
    parser.add_argument("--canonical-security", type=Path, required=True)
    return parser.parse_args()


def github_event_repository() -> dict[str, object]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return {}
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    repository = event.get("repository", {})
    return repository if isinstance(repository, dict) else {}


def run_git(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ("git", "-C", str(root), *args),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


def repository_name(root: Path, override: str, event_repository: dict[str, object]) -> str:
    if override:
        return override
    event_name = event_repository.get("name")
    if isinstance(event_name, str) and event_name:
        return event_name
    github_repository = os.environ.get("GITHUB_REPOSITORY", "")
    if github_repository:
        return github_repository.rsplit("/", 1)[-1]
    remote = run_git(root, "config", "--get", "remote.origin.url")
    if remote:
        return re.split(r"[/:]", remote.rstrip("/"))[-1].removesuffix(".git")
    return root.name


def default_branch(root: Path, override: str, event_repository: dict[str, object]) -> str:
    if override:
        return override
    event_branch = event_repository.get("default_branch")
    if isinstance(event_branch, str) and event_branch:
        return event_branch
    remote_head = run_git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if remote_head.startswith("origin/"):
        return remote_head.removeprefix("origin/")
    return ""


def normalize_heading(value: str) -> str:
    value = re.sub(r"\s+#+\s*$", "", value.strip())
    value = value.replace("`", "").replace("*", "").replace("_", "")
    return " ".join(value.casefold().split())


def markdown_headings(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    headings: list[tuple[int, str]] = []
    fence: str | None = None

    index = 0
    while index < len(lines):
        line = lines[index]
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            index += 1
            continue
        if fence is not None:
            index += 1
            continue

        atx = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if atx:
            headings.append((len(atx.group(1)), normalize_heading(atx.group(2))))
            index += 1
            continue

        if index + 1 < len(lines) and line.strip():
            setext = re.match(r"^\s{0,3}(=+|-+)\s*$", lines[index + 1])
            if setext:
                level = 1 if setext.group(1).startswith("=") else 2
                headings.append((level, normalize_heading(line)))
                index += 2
                continue
        index += 1
    return headings


def exact_root_file(root: Path, name: str) -> Path | None:
    try:
        entries = {entry.name: entry for entry in root.iterdir()}
    except OSError:
        return None
    path = entries.get(name)
    return path if path is not None and path.is_file() else None


def annotation(result: Result) -> str:
    message = result.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    properties = "title=OGHO template compliance"
    if result.file:
        properties += f",file={result.file}"
    return f"::error {properties}::{message}"


def write_summary(results: list[Result]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    failures = [result for result in results if not result.passed]
    lines = ["## OGHO template compliance", ""]
    if failures:
        lines.append(f"❌ {len(failures)} of {len(results)} checks failed.")
    else:
        lines.append(f"✅ All {len(results)} checks passed.")
    lines.extend(("", "| Check | Result | Details |", "| --- | --- | --- |"))
    for result in results:
        status = "✅ Pass" if result.passed else "❌ Fail"
        details = result.message.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {result.name} | {status} | {details} |")
    try:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write("\n".join(lines) + "\n")
    except OSError as error:
        print(f"warning: could not write GitHub job summary: {error}", file=sys.stderr)


def validate(args: argparse.Namespace) -> list[Result]:
    root = args.repository_root.resolve()
    event_repository = github_event_repository()
    results: list[Result] = []

    name = repository_name(root, args.repository_name, event_repository)
    results.append(
        Result(
            "Repository name",
            bool(REPOSITORY_NAME_PATTERN.fullmatch(name)),
            (
                f"Repository name '{name}' uses only lowercase letters, digits, and single dashes."
                if REPOSITORY_NAME_PATTERN.fullmatch(name)
                else f"Repository name '{name}' must use only lowercase letters, digits, and single dashes."
            ),
        )
    )

    branch = default_branch(root, args.default_branch, event_repository)
    results.append(
        Result(
            "Default branch",
            branch == "main",
            (
                "Default branch is 'main'."
                if branch == "main"
                else (
                    f"Default branch is '{branch}', but it must be 'main'."
                    if branch
                    else "Could not determine the default branch; provide the default-branch input."
                )
            ),
        )
    )

    files: dict[str, Path] = {}
    for required_file in REQUIRED_FILES:
        path = exact_root_file(root, required_file)
        if path is not None:
            files[required_file] = path
        results.append(
            Result(
                f"Required file: {required_file}",
                path is not None,
                (
                    f"{required_file} exists at the repository root."
                    if path is not None
                    else f"{required_file} must exist as a file at the repository root with this exact name."
                ),
                required_file,
            )
        )

    if args.contributing_policy != "disabled":
        contributing_path = exact_root_file(root, "CONTRIBUTING.md")
        if contributing_path is not None:
            files["CONTRIBUTING.md"] = contributing_path

        contributing_required = args.contributing_policy == "required"
        results.append(
            Result(
                (
                    "Required file: CONTRIBUTING.md"
                    if contributing_required
                    else "Optional file: CONTRIBUTING.md"
                ),
                contributing_path is not None or not contributing_required,
                (
                    "CONTRIBUTING.md exists at the repository root and will be validated."
                    if contributing_path is not None
                    else (
                        "CONTRIBUTING.md must exist as a file at the repository root with this exact name."
                        if contributing_required
                        else (
                            "CONTRIBUTING.md is not present locally; GitHub may use the "
                            "organization-wide community health file."
                        )
                    )
                ),
                "CONTRIBUTING.md",
            )
        )

    license_path = files.get("LICENSE.txt")
    if license_path:
        license_bytes = license_path.read_bytes()
        is_ascii_text = all(byte in (9, 10, 12) or 32 <= byte <= 126 for byte in license_bytes)
        uses_lf = b"\r" not in license_bytes
        results.append(
            Result(
                "LICENSE.txt format",
                is_ascii_text and uses_lf,
                (
                    "LICENSE.txt is ASCII text with LF line endings."
                    if is_ascii_text and uses_lf
                    else "LICENSE.txt must contain only printable ASCII text and must not contain CR or CRLF line endings."
                ),
                "LICENSE.txt",
            )
        )

    readme_path = files.get("README.md")
    if readme_path:
        headings = markdown_headings(readme_path)
        all_heading_names = {heading for _, heading in headings}
        has_title = any(level == 1 for level, _ in headings)
        results.append(
            Result(
                "README title",
                has_title,
                "README.md contains a level-one project title." if has_title else "README.md must contain a level-one project title.",
                "README.md",
            )
        )
        for label, alternatives in README_SECTIONS:
            present = not all_heading_names.isdisjoint(alternatives)
            accepted = ", ".join(sorted(alternatives))
            results.append(
                Result(
                    f"README section: {label}",
                    present,
                    (
                        f"README.md contains the {label} section."
                        if present
                        else f"README.md is missing the {label} section (accepted heading: {accepted})."
                    ),
                    "README.md",
                )
            )

    contributing_path = files.get("CONTRIBUTING.md")
    if contributing_path:
        headings = markdown_headings(contributing_path)
        all_heading_names = {heading for _, heading in headings}
        has_title = any(level == 1 for level, _ in headings)
        results.append(
            Result(
                "CONTRIBUTING title",
                has_title,
                (
                    "CONTRIBUTING.md contains a level-one title."
                    if has_title
                    else "CONTRIBUTING.md must contain a level-one title."
                ),
                "CONTRIBUTING.md",
            )
        )
        for section in CONTRIBUTING_SECTIONS:
            present = section in all_heading_names
            display_name = section.title()
            results.append(
                Result(
                    f"CONTRIBUTING section: {display_name}",
                    present,
                    (
                        f"CONTRIBUTING.md contains the {display_name} section."
                        if present
                        else f"CONTRIBUTING.md is missing the {display_name} section."
                    ),
                    "CONTRIBUTING.md",
                )
            )
        contributing_text = contributing_path.read_text(encoding="utf-8", errors="replace")
        has_oca_link = OCA_URL in contributing_text
        results.append(
            Result(
                "Oracle Contributor Agreement link",
                has_oca_link,
                (
                    "CONTRIBUTING.md references the Oracle Contributor Agreement application."
                    if has_oca_link
                    else f"CONTRIBUTING.md must reference {OCA_URL}/."
                ),
                "CONTRIBUTING.md",
            )
        )

    security_path = files.get("SECURITY.md")
    if security_path:
        try:
            canonical_security = args.canonical_security.read_bytes()
        except OSError as error:
            results.append(
                Result(
                    "SECURITY.md template",
                    False,
                    f"Could not read the canonical SECURITY.md bundled with the action: {error}",
                    "SECURITY.md",
                )
            )
        else:
            exact_match = security_path.read_bytes() == canonical_security
            results.append(
                Result(
                    "SECURITY.md template",
                    exact_match,
                    (
                        "SECURITY.md is byte-for-byte identical to the canonical template."
                        if exact_match
                        else "SECURITY.md must be byte-for-byte identical to the canonical template bundled with this action."
                    ),
                    "SECURITY.md",
                )
            )

    return results


def main() -> int:
    args = parse_args()
    if not args.repository_root.is_dir():
        print(f"error: repository root does not exist or is not a directory: {args.repository_root}", file=sys.stderr)
        return 2

    results = validate(args)
    failures = [result for result in results if not result.passed]
    for result in results:
        marker = "PASS" if result.passed else "FAIL"
        print(f"[{marker}] {result.name}: {result.message}")
        if not result.passed:
            print(annotation(result))
    write_summary(results)
    print(f"\n{len(results) - len(failures)} passed; {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
