from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
}
SCANNED_ROOTS = (
    ROOT / "apps",
    ROOT / "configs",
    ROOT / "docs",
    ROOT / "frontend" / "src",
    ROOT / "frontend" / "public",
    ROOT / "scripts",
    ROOT / "src" / "rasa",
    ROOT / "tests",
)
TOP_LEVEL_FILES = (
    ROOT / "CONTRIBUTING.md",
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "render.yaml",
)


def _project_text_files() -> list[Path]:
    files = list(TOP_LEVEL_FILES)
    for root in SCANNED_ROOTS:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS
        )
    return sorted(set(files))


def test_published_project_content_contains_no_em_dash() -> None:
    forbidden = chr(0x2014)
    violations = []
    for path in _project_text_files():
        content = path.read_text(encoding="utf-8")
        if forbidden in content:
            violations.append(str(path.relative_to(ROOT)))

    assert violations == [], f"Replace em dashes in: {', '.join(violations)}"
