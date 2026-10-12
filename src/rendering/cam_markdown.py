"""
CAM markdown helpers: RM section edits → markdown, and markdown → styled HTML.
Pure functions with no application state.
"""

import html as _html_mod
import re as _re


def html_to_simple_markdown(html_str: str) -> str:
    """Convert contenteditable HTML back to simplified markdown for PDF rendering."""
    text = html_str
    # Block elements
    text = _re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n', text, flags=_re.DOTALL)
    text = _re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n', text, flags=_re.DOTALL)
    text = _re.sub(r'<h4[^>]*>(.*?)</h4>', r'#### \1\n', text, flags=_re.DOTALL)
    text = _re.sub(r'<br\s*/?>', '\n', text)
    text = _re.sub(r'</p>\s*', '\n\n', text)
    text = _re.sub(r'<p[^>]*>', '', text)
    text = _re.sub(r'</div>\s*', '\n', text)
    text = _re.sub(r'<div[^>]*>', '', text)
    # Inline formatting
    text = _re.sub(r'<(?:strong|b)>(.*?)</(?:strong|b)>', r'**\1**', text, flags=_re.DOTALL)
    text = _re.sub(r'<(?:em|i)>(.*?)</(?:em|i)>', r'*\1*', text, flags=_re.DOTALL)
    # Lists
    text = _re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=_re.DOTALL)
    text = _re.sub(r'</?[uo]l[^>]*>\s*', '', text)
    # Tables
    def _table_to_md(m):
        table_html = m.group(0)
        rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, _re.DOTALL)
        md_lines = []
        for i, row_html in enumerate(rows):
            cells = _re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, _re.DOTALL)
            cells = [_re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            md_lines.append('| ' + ' | '.join(cells) + ' |')
            if i == 0:
                md_lines.append('| ' + ' | '.join('---' for _ in cells) + ' |')
        return '\n'.join(md_lines) + '\n'
    text = _re.sub(r'<table[^>]*>.*?</table>', _table_to_md, text, flags=_re.DOTALL)
    # Strip remaining HTML tags
    text = _re.sub(r'<[^>]+>', '', text)
    # Clean up HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    # Clean up excessive whitespace
    text = _re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def apply_section_edits_to_markdown(md: str, edits: dict) -> str:
    """Merge RM CAM section edits into the markdown text for PDF generation."""
    if not edits:
        return md
    # Find all ## heading positions
    pattern = _re.compile(r'^## (.+)$', _re.MULTILINE)
    matches = list(pattern.finditer(md))
    if not matches:
        return md

    result_parts = []
    # Add content before first ## heading
    result_parts.append(md[:matches[0].start()])

    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        key = ' '.join(title.split())  # Normalize whitespace (same as UI camSectionKey)
        section_start = match.start()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(md)

        if key in edits and edits[key].get('html', '').strip():
            edited_md = html_to_simple_markdown(edits[key]['html'])
            # Remove heading from converted content if present (edit HTML includes heading)
            lines = edited_md.split('\n')
            body_start = 0
            for j, line in enumerate(lines):
                if line.strip().startswith('## '):
                    body_start = j + 1
                    break
            body_content = '\n'.join(lines[body_start:]).strip()
            result_parts.append(f'## {title}\n\n{body_content}\n\n')
        else:
            result_parts.append(md[section_start:section_end])

    return ''.join(result_parts)


def render_markdown_fragment(md: str) -> str:
    body = _html_mod.escape(md)

    def _table_block(block):
        rows = block.strip().split("\n")
        if len(rows) < 2:
            return block
        # Filter out separator rows (including malformed long-dash ones)
        data_rows = []
        for row in rows:
            stripped = row.strip()
            if _re.match(r"^\|[\s\-:|]+\|?$", stripped):
                continue
            if len(stripped) > 200 and stripped.count("-") / len(stripped) > 0.5:
                continue
            data_rows.append(row)
        if len(data_rows) <= 1:
            return ""  # Header-only table — skip
        out = '<table class="cam-table">'
        for i, row in enumerate(data_rows):
            cells = row.split("|")[1:-1]
            tag = "th" if i == 0 else "td"
            out += "<tr>" + "".join(f"<{tag}>{c.strip()}</{tag}>" for c in cells) + "</tr>"
        return out + "</table>"

    body = _re.sub(r"((?:^\|.+\|$\n?)+)", lambda m: _table_block(m.group(0)), body, flags=_re.MULTILINE)
    body = _re.sub(r"^#### (.+)$", r"<h4>\1</h4>", body, flags=_re.MULTILINE)
    body = _re.sub(r"^### (.+)$", r"<h3>\1</h3>", body, flags=_re.MULTILINE)
    body = _re.sub(r"^## (.+)$", r"<h2>\1</h2>", body, flags=_re.MULTILINE)
    body = _re.sub(r"^# (.+)$", r"<h1>\1</h1>", body, flags=_re.MULTILINE)
    body = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body)
    body = _re.sub(r"\*(.+?)\*", r"<em>\1</em>", body)
    body = _re.sub(r"^---+$", "<hr>", body, flags=_re.MULTILINE)
    body = _re.sub(r"^[\-\*] (.+)$", r"<li>\1</li>", body, flags=_re.MULTILINE)
    body = _re.sub(r"((?:<li>.+</li>\n?)+)", r"<ul>\1</ul>", body)
    body = _re.sub(r"\n{2,}", "</p><p>", body)
    body = "<p>" + body + "</p>"
    body = _re.sub(r"<p>\s*<(h[1-4]|table|ul|hr)", r"<\1", body)
    body = _re.sub(r"</(h[1-4]|table|ul|hr)>\s*</p>", r"</\1>", body)
    return body


def markdown_to_html(md: str, title: str = "CAM Report") -> str:
    """Convert CAM Markdown to a styled HTML document for on-screen viewing."""
    body = render_markdown_fragment(md)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>{_html_mod.escape(title)} — CAM Report</title>
<style>
  :root {{
    --bg-primary: #0d0d1a;
    --bg-section: #111128;
    --bg-table-header: #1e3a5f;
    --bg-table-alt: rgba(30,58,95,0.15);
    --text-primary: #c8c8e0;
    --text-secondary: #9595b0;
    --accent-blue: #60a5fa;
    --accent-indigo: #818cf8;
    --accent-purple: #a78bfa;
    --border-color: #252550;
    --border-section: #1e3a5f;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family:'Segoe UI',Tahoma,'Helvetica Neue',sans-serif;
         background:var(--bg-primary); color:var(--text-primary);
         max-width:960px; margin:0 auto; padding:2rem 2.5rem; line-height:1.75;
         font-size: 14px; }}
  h1 {{ color:var(--accent-blue); border-bottom:2px solid var(--border-section);
       padding-bottom:0.6rem; margin-top:2.5rem; font-size:1.6rem;
       letter-spacing: 0.03em; text-transform: uppercase; }}
  h2 {{ color:#3b82f6; margin-top:2.2rem; border-bottom:1px solid var(--border-color);
       padding-bottom:0.35rem; font-size:1.2rem; }}
  h3 {{ color:var(--accent-indigo); margin-top:1.5rem; font-size:1.05rem; }}
  h4 {{ color:var(--accent-purple); font-size:0.95rem; }}
  .cam-table {{ width:100%; border-collapse:collapse; margin:1rem 0; font-size:0.85rem;
               border-radius:6px; overflow:hidden; border:1px solid var(--border-color); }}
  .cam-table th {{ background:var(--bg-table-header); color:#fff; padding:10px 12px;
                  text-align:left; font-weight:600; font-size:0.82rem;
                  text-transform:uppercase; letter-spacing:0.04em; }}
  .cam-table td {{ padding:8px 12px; border-bottom:1px solid var(--border-color);
                  vertical-align:top; }}
  .cam-table tr:nth-child(even) td {{ background:var(--bg-table-alt); }}
  .cam-table tr:hover td {{ background:rgba(59,130,246,0.08); }}
  ul {{ padding-left:1.5rem; margin:0.6rem 0; }}
  li {{ margin:0.35rem 0; }}
  strong {{ color:#e0e0ff; }}
  em {{ color:var(--text-secondary); font-style:italic; }}
  hr {{ border:none; border-top:1px solid var(--border-color); margin:2.5rem 0; }}
  p {{ margin:0.5rem 0; }}
  /* Status badges */
  .cam-table td:nth-child(5) {{ font-size:0.82rem; }}
  /* Section containers for visual grouping */
  h1 + p, h1 + ul, h1 + .cam-table {{ margin-top:1rem; }}
  /* Print styles */
  @media print {{
    body {{ background:#fff; color:#111; font-size:11pt; max-width:100%; padding:1cm; }}
    h1 {{ color:#1e3a5f; border-bottom-color:#1e3a5f; page-break-before:always; }}
    h1:first-of-type {{ page-break-before:auto; }}
    h2 {{ color:#335577; border-bottom-color:#ccc; }}
    h3,h4 {{ color:#444; }}
    .cam-table th {{ background:#335577; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
    .cam-table {{ border-color:#ccc; }}
    .cam-table td {{ border-bottom-color:#ddd; color:#222; }}
    .cam-table tr:nth-child(even) td {{ background:#f8f8f8; -webkit-print-color-adjust:exact; }}
    strong {{ color:#111; }}
    hr {{ border-top-color:#ccc; }}
    a {{ color:#1e3a5f; }}
  }}
</style></head><body>
{body}
</body></html>"""


