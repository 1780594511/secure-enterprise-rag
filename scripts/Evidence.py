"""Export sanitized test summaries and package only the standalone project's public files."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def test_reports():
    output = ROOT / "docs" / "results"
    browser = json.loads((ROOT / "var/browser-tests.json").read_text(encoding="utf8"))
    cases = []
    for suite in browser["suites"]:
        for spec in suite["specs"]:
            for test in spec["tests"]:
                for run in test["results"]:
                    cases.append({"case": spec["title"], "status": run["status"], "ms": run["duration"]})
    report = {"playwright": browser["config"]["version"], "stats": browser["stats"], "cases": cases}
    (output / "browser.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
    )
    tree = ET.parse(ROOT / "var/pytest.xml")
    for suite in tree.iter("testsuite"):
        suite.attrib.pop("hostname", None)
    tree.write(output / "pytest.xml", encoding="utf-8", xml_declaration=True)


def package():
    folders = ["rag", "evaluations", "tests", "docs", "examples", "scripts"]
    patterns = [
        "README.md",
        "LICENSE",
        "THIRD_PARTY.md",
        ".env.example",
        ".gitignore",
        "pyproject.toml",
        "requirements.in",
        "requirements.lock",
        "frontend/package*.json",
        "frontend/tsconfig.json",
        "frontend/playwright.config.ts",
        "frontend/index.html",
        "frontend/src/*",
        "frontend/e2e/*",
    ]
    files = {p for pattern in patterns for p in ROOT.glob(pattern) if p.is_file()}
    extensions = {".py", ".md", ".sql", ".json", ".xml", ".png", ".ps1"}
    files.update(
        p
        for folder in folders
        for p in (ROOT / folder).rglob("*")
        if p.is_file() and p.suffix.lower() in extensions and "__pycache__" not in p.parts
    )
    output = ROOT / "release/secure-enterprise-rag-source.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, Path("secure-enterprise-rag") / path.relative_to(ROOT))
    with ZipFile(output) as archive:
        assert archive.testzip() is None
    print(f"{len(files)} files: {output.name}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["reports", "package"])
    if parser.parse_args().action == "reports":
        test_reports()
    else:
        package()
