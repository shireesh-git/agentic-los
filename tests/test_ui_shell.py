"""The SPA shell is assembled from one file per page (src/ui/templates/pages/)."""

from src.core.ui_paths import TEMPLATES_ROOT, render_spa


def test_every_include_is_inlined():
    html = render_spa()
    assert html.startswith("<!DOCTYPE html>")  # no byte-order mark before it (quirks mode)
    assert "<!-- include:" not in html
    assert 'href="/static/css/dashboard.css?v=' in html  # cache-busted
    assert 'src="/static/js/app.js?v=' in html
    for page in ("summary", "cases", "detail", "onboard", "pipeline", "approvals", "settings"):
        assert f"page==='{page}'" in html


def test_every_page_file_is_included():
    shell = (TEMPLATES_ROOT / "index.html").read_text(encoding="utf-8")
    for page_file in (TEMPLATES_ROOT / "pages").glob("*.html"):
        assert f"<!-- include: pages/{page_file.name} -->" in shell
