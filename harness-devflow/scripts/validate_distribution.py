#!/usr/bin/env python3
"""Validate the distributable without relying on an installed host or third-party libs."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.cli import skill_for
from harness.model import STAGES, BUNDLED_CAPABILITIES, validate_config


def validate(root=ROOT):
    errors = []
    manifests = [json.loads((root / host / "plugin.json").read_text())
                 for host in (".codex-plugin", ".claude-plugin")]
    if any(m["name"] != root.name or m["version"] != manifests[0]["version"] for m in manifests):
        errors.append("Host manifests must agree on plugin name/version")
    if not re.fullmatch(r"\d+\.\d+\.\d+", manifests[0]["version"]):
        errors.append("Expected release semver")
    if "hooks" in manifests[0]:
        errors.append("Unsupported Codex manifest hooks field")
    expected = {skill_for(stage) for stage in STAGES} | {"flow"} | BUNDLED_CAPABILITIES
    actual = {p.parent.name for p in (root / "skills").glob("*/SKILL.md")}
    if actual != expected:
        errors.append(f"Skill routing mismatch: expected {expected}, found {actual}")
    for path in (root / "skills").glob("*/SKILL.md"):
        text = path.read_text()
        if not text.startswith(f"---\nname: {path.parent.name}\n") or "\ndescription: " not in text:
            errors.append(f"Invalid skill discovery frontmatter: {path}")
    for path in root.rglob("*.md"):
        if any(p in {".git", "dist", ".harness"} for p in path.relative_to(root).parts):
            continue
        text = path.read_text()
        if "[TODO:" in text:
            errors.append(f"Unfinished scaffold marker: {path}")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if target.startswith(("http:", "https:", "codex:", "#")):
                continue
            target = target.split("#", 1)[0]
            if not (path.parent / target).exists():
                errors.append(f"Broken link in {path.relative_to(root)}: {target}")
    for path in (root / "examples").glob("*.json"):
        try:
            validate_config(json.loads(path.read_text()))
        except Exception as error:
            errors.append(f"Invalid example {path.name}: {error}")
    for name, files in {
        "brownfield-recon": ["scripts/collect_evidence.py", "references/report-contract.md", "references/search-playbook.md"],
        "server-tech-design": ["references/section-guide.md", "references/writing-style.md", "references/review-checklist.md", "references/template.md"],
    }.items():
        for file in files:
            if not (root / "skills" / name / file).is_file():
                errors.append(f"Missing bundled capability resource: {name}/{file}")
    errors.extend(bundled_drift(root))
    return errors


def skill_files(directory):
    return {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*")
            if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts}


def bundled_drift(root):
    """Bundled capabilities must stay byte-identical to the standalone copies beside the plugin, when present."""
    errors = []
    for name in sorted(BUNDLED_CAPABILITIES):
        standalone = root.parent / name
        if not standalone.is_dir():
            continue
        bundled, source = skill_files(root / "skills" / name), skill_files(standalone)
        for path in sorted(set(bundled) ^ set(source)):
            errors.append(f"Bundled {name} differs from standalone copy: {path} exists on one side only")
        for path in sorted(set(bundled) & set(source)):
            if bundled[path] != source[path]:
                errors.append(f"Bundled {name} differs from standalone copy: {path}")
    return errors


if __name__ == "__main__":
    found = validate()
    print(json.dumps({"status": "failed" if found else "passed", "errors": found}, indent=2))
    sys.exit(bool(found))
