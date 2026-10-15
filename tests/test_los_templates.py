"""Static checks on the LOS Alpine templates: mistakes Alpine fails on silently in the browser."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

TEMPLATES = sorted((Path(__file__).resolve().parents[1] / "src/ui/templates").glob("los*/**/*.html")) + \
    [Path(__file__).resolve().parents[1] / "src/ui/templates/los.html"]

# A valid attribute name: letters, digits and the punctuation Alpine/HTML use (x-on:click.prevent, :class, @click).
_ATTR = re.compile(r"^[@:]?[a-z][\w:.\-]*$", re.IGNORECASE)


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.problems = []

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        for name, _ in attrs:
            if not _ATTR.match(name):
                # e.g. x-text="a" + ' b'  → the quote closed early and the rest became attributes
                self.problems.append(f"line {line}: <{tag}> has a stray attribute {name!r} (misplaced quote?)")
        if tag != "template" and any(n == "x-for" for n, _ in attrs):
            # Alpine only honours x-for on <template>; elsewhere the list silently never renders
            self.problems.append(f"line {line}: x-for on <{tag}> (must be on <template>)")


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_template_has_no_silent_alpine_mistakes(path):
    scan = _Scan()
    scan.feed(path.read_text(encoding="utf-8"))
    assert not scan.problems, "\n".join(scan.problems)


def test_the_application_page_renders_only_once_loaded():
    text = (Path(__file__).resolve().parents[1] / "src/ui/templates/los/application.html").read_text(encoding="utf-8")
    assert '<template x-if="current">' in text            # nothing evaluates against a null application
