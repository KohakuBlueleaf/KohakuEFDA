"""Docs gate: front matter, one H1, resolving relative links, and a site config that lists real pages."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.glob("*/**/*.md"))
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CONFIG_PATH = re.compile(r'"((?:[a-z0-9-]+/)*(?:README|[a-z0-9-]+)\.md)"')


def _front_matter(text: str) -> dict[str, str]:
    assert text.startswith("---\n"), "missing front matter"
    end = text.index("\n---\n", 4)
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if line and not line.startswith(" ") and ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def test_docs_tree_has_pages() -> None:
    assert (DOCS / "en" / "README.md").is_file()
    assert len(PAGES) > 20


def test_every_page_has_front_matter_and_one_heading() -> None:
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        fields = _front_matter(text)
        assert {"title", "summary", "tags"} <= set(fields), page
        assert fields["title"] and fields["summary"], page
        body = text[text.index("\n---\n", 4) + 5 :]
        headings = [line for line in body.splitlines() if line.startswith("# ")]
        assert len(headings) == 1, (page, headings)


def test_relative_links_resolve() -> None:
    broken: list[tuple[Path, str]] = []
    for page in PAGES:
        for target in LINK.findall(page.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path = target.split("#", 1)[0]
            if not path:
                continue
            resolved = (page.parent / path).resolve()
            if not resolved.exists():
                locale_root = DOCS / page.relative_to(DOCS).parts[0]
                fallback = DOCS / "en" / resolved.relative_to(locale_root)
                if not fallback.exists():
                    broken.append((page, target))
    assert broken == []


def test_site_config_lists_existing_english_pages() -> None:
    config = (DOCS / "docs.config.js").read_text(encoding="utf-8")
    listed = set(CONFIG_PATH.findall(config))
    assert "README.md" in listed
    missing = sorted(p for p in listed if not (DOCS / "en" / p).is_file())
    assert missing == []
    english = {
        str(p.relative_to(DOCS / "en")).replace("\\", "/")
        for p in (DOCS / "en").glob("**/*.md")
    }
    assert sorted(english - listed) == []
