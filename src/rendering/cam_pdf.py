"""
CAM PDF renderer (ReportLab): cover page, running headers/footers, tables,
source tags and per-section RM comments.
"""

import html as _html_mod
import re as _re


def generate_cam_pdf(md: str, company_name: str, section_comments: dict[str, str] | None = None) -> bytes:
    """Generate a professional CAM PDF with cover page, headers, footers, and page breaks."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, PageBreak)
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER

    # ── Fix ₹ (U+20B9) which Helvetica cannot render (shows as ■) ──
    md = md.replace("\u20b9", "Rs.").replace("\u20a8", "Rs.")

    BANK_NAME = "INDIAN BANK"
    BANK_BLUE = colors.HexColor("#1e3a5f")
    HEADER_BLUE = colors.HexColor("#3b5998")
    ACCENT_GOLD = colors.HexColor("#c8a951")
    LIGHT_BG = colors.HexColor("#f0f4f8")
    SECTION_BG = colors.HexColor("#eaf0f7")
    SOURCE_GREY = colors.HexColor("#8899aa")

    buf = BytesIO()
    section_comments = section_comments or {}

    def _header_footer(canvas, doc):
        """Draw header and footer on each page."""
        canvas.saveState()
        w, h = A4
        # Header bar with bank blue background
        canvas.setFillColor(BANK_BLUE)
        canvas.rect(0, h - 13*mm, w, 13*mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.white)
        canvas.drawString(15*mm, h - 9.5*mm, BANK_NAME)
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(w - 15*mm, h - 9.5*mm, "CREDIT APPRAISAL MEMORANDUM")
        # Gold accent line below header
        canvas.setStrokeColor(ACCENT_GOLD)
        canvas.setLineWidth(1.5)
        canvas.line(0, h - 13*mm, w, h - 13*mm)
        # Footer
        canvas.setStrokeColor(colors.HexColor("#cccccc"))
        canvas.setLineWidth(0.5)
        canvas.line(15*mm, 14*mm, w - 15*mm, 14*mm)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawString(15*mm, 9*mm, "STRICTLY CONFIDENTIAL  |  For Internal Use Only")
        canvas.drawRightString(w - 15*mm, 9*mm, f"Page {doc.page}")
        # Gold dot accent
        canvas.setFillColor(ACCENT_GOLD)
        canvas.circle(w / 2, 10.5*mm, 1.2, fill=1, stroke=0)
        canvas.restoreState()

    def _first_page(canvas, doc):
        """Cover page has no header/footer."""
        pass

    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CamH1", fontSize=13, spaceAfter=6, spaceBefore=14,
                              textColor=BANK_BLUE, fontName="Helvetica-Bold",
                              borderWidth=0, borderPadding=0))
    styles.add(ParagraphStyle(name="CamH2", fontSize=10.5, spaceAfter=5, spaceBefore=10,
                              textColor=HEADER_BLUE, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="CamH3", fontSize=9.5, spaceAfter=3, spaceBefore=6,
                              textColor=colors.HexColor("#2c4a6e"), fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="CamBody", fontSize=8.5, spaceAfter=3, leading=12.5,
                              fontName="Helvetica", textColor=colors.HexColor("#222222")))
    styles.add(ParagraphStyle(name="CamBullet", fontSize=8.5, spaceAfter=2, leading=12,
                              bulletIndent=10, leftIndent=20, fontName="Helvetica",
                              textColor=colors.HexColor("#222222")))
    styles.add(ParagraphStyle(name="CamSource", fontSize=7, spaceAfter=6, leading=9.5,
                              fontName="Helvetica-Oblique", textColor=SOURCE_GREY))
    styles.add(ParagraphStyle(name="CoverBank", fontSize=26, leading=32, spaceAfter=2,
                              textColor=BANK_BLUE, fontName="Helvetica-Bold",
                              alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="CoverDivision", fontSize=11, spaceAfter=6, spaceBefore=2,
                              textColor=colors.HexColor("#555"), fontName="Helvetica",
                              alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="CoverTitle", fontSize=18, spaceAfter=6, spaceBefore=16,
                              textColor=BANK_BLUE, fontName="Helvetica-Bold",
                              alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="CoverCompany", fontSize=20, spaceAfter=6, spaceBefore=8,
                              textColor=colors.HexColor("#111111"), fontName="Helvetica-Bold",
                              alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="CoverDetail", fontSize=10, spaceAfter=3,
                              textColor=colors.HexColor("#444"), fontName="Helvetica",
                              alignment=TA_CENTER, leading=14))
    styles.add(ParagraphStyle(name="CoverConfidential", fontSize=7.5, spaceBefore=20,
                              textColor=colors.HexColor("#888"), fontName="Helvetica-Oblique",
                              alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="CamComment", fontSize=8, spaceAfter=0, leading=11,
                              textColor=colors.HexColor("#4b5563"), fontName="Helvetica"))

    story = []
    lines = md.split("\n")
    table_buf = []

    def _flush_table():
        if not table_buf:
            return
        data_rows = []
        for row in table_buf:
            # Skip separator rows: lines that are mostly dashes/colons/pipes/spaces
            stripped_row = row.strip()
            if _re.match(r"^\|[\s\-:|]+\|?$", stripped_row):
                continue
            # Also skip if > 60% dashes (LLM sometimes generates ultra-long separators)
            if len(stripped_row) > 0:
                dash_ratio = (stripped_row.count("-") + stripped_row.count(":")) / len(stripped_row)
                if dash_ratio > 0.6 and stripped_row.startswith("|"):
                    continue
            cells = [c.strip() for c in row.split("|")[1:-1]]
            if not cells:
                continue
            # Wrap cells in Paragraphs for word-wrapping
            wrapped = []
            for ci, c in enumerate(cells):
                c = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", c)
                style = styles["CamBody"]
                wrapped.append(Paragraph(c, style))
            data_rows.append(wrapped)
        # Skip header-only tables (1 row = header with no data)
        if len(data_rows) <= 1:
            table_buf.clear()
            return
        if data_rows:
            ncols = max(len(r) for r in data_rows)
            for r in data_rows:
                while len(r) < ncols:
                    r.append(Paragraph("", styles["CamBody"]))
            # ── Smart column widths based on content ──
            avail_w = A4[0] - 30*mm
            # Estimate character widths per column from all rows
            col_char_widths = [0] * ncols
            for r in data_rows:
                for ci, cell in enumerate(r):
                    txt = cell.text if hasattr(cell, 'text') else str(cell)
                    # Clean HTML tags for measuring
                    clean_txt = _re.sub(r"<[^>]+>", "", txt)
                    col_char_widths[ci] = max(col_char_widths[ci], len(clean_txt))
            total_chars = sum(col_char_widths) or 1
            # Ensure minimum width per column (at least 12% of avail)
            min_col_w = avail_w * 0.08
            col_widths = []
            for cw in col_char_widths:
                w = max((cw / total_chars) * avail_w, min_col_w)
                col_widths.append(w)
            # Normalize to fit available width
            total_w = sum(col_widths)
            if total_w > 0:
                col_widths = [(w / total_w) * avail_w for w in col_widths]

            t = Table(data_rows, repeatRows=1, colWidths=col_widths)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BANK_BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d0d8e0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                # Top rounding effect — thicker top border
                ("LINEABOVE", (0, 0), (-1, 0), 1.5, BANK_BLUE),
                # Bottom border accent
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, BANK_BLUE),
            ]))
            story.append(t)
            story.append(Spacer(1, 4*mm))
        table_buf.clear()

    # ── Build cover page manually ──
    # Skip markdown cover page lines and build a proper ReportLab cover instead
    cover_lines_text = []
    body_start_idx = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Cover page ends at TABLE OF CONTENTS heading
        if stripped.startswith("## TABLE OF CONTENTS") or stripped.startswith("## 1."):
            body_start_idx = i
            break
        cover_lines_text.append(stripped)
        body_start_idx = i + 1

    # Build professional cover page
    story.append(Spacer(1, 35*mm))
    # Gold accent line
    cover_gold_line = Table([[""]], colWidths=[140*mm])
    cover_gold_line.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 2.5, ACCENT_GOLD),
    ]))
    story.append(cover_gold_line)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(BANK_NAME, styles["CoverBank"]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Corporate Banking Division", styles["CoverDivision"]))
    story.append(Spacer(1, 4*mm))
    # Blue line under division
    cover_blue_line = Table([[""]], colWidths=[100*mm])
    cover_blue_line.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, BANK_BLUE),
    ]))
    story.append(cover_blue_line)
    story.append(Spacer(1, 14*mm))
    story.append(Paragraph("CREDIT APPRAISAL MEMORANDUM", styles["CoverTitle"]))
    story.append(Paragraph("(CAM)", styles["CoverDivision"]))
    story.append(Spacer(1, 12*mm))
    # Borrower name in a highlighted box
    borrower_tbl = Table([[Paragraph(company_name.upper(), styles["CoverCompany"])]], colWidths=[150*mm])
    borrower_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SECTION_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT_GOLD),
        ("LINEAFTER", (-1, 0), (-1, -1), 3, ACCENT_GOLD),
    ]))
    story.append(borrower_tbl)

    # Extract key details from cover text
    for ct in cover_lines_text:
        if ct.startswith("**CIN") or ct.startswith("CIN:"):
            clean = ct.replace("**", "").strip().rstrip("  ")
            story.append(Paragraph(clean, styles["CoverDetail"]))
        elif ct.startswith("**PAN"):
            clean = ct.replace("**", "").strip().rstrip("  ")
            story.append(Paragraph(clean, styles["CoverDetail"]))
        elif "Case Type:" in ct:
            clean = ct.replace("**", "").strip().rstrip("  ")
            story.append(Spacer(1, 6*mm))
            story.append(Paragraph(clean, styles["CoverDetail"]))
        elif "Amount Requested:" in ct:
            clean = ct.replace("**", "").strip().rstrip("  ")
            story.append(Paragraph(clean, styles["CoverDetail"]))
        elif "Recommendation:" in ct:
            clean = ct.replace("**", "").strip().rstrip("  ")
            story.append(Paragraph(clean, styles["CoverDetail"]))
        elif "Risk Grade:" in ct:
            clean = ct.replace("**", "").strip().rstrip("  ")
            story.append(Paragraph(clean, styles["CoverDetail"]))
        elif "Date:" in ct:
            clean = ct.replace("**", "").strip().rstrip("  ")
            story.append(Paragraph(clean, styles["CoverDetail"]))
        elif "Sector:" in ct:
            clean = ct.replace("**", "").strip().rstrip("  ")
            story.append(Paragraph(clean, styles["CoverDetail"]))

    story.append(Spacer(1, 20*mm))
    cover_line_tbl3 = Table([[""]], colWidths=[140*mm])
    cover_line_tbl3.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, ACCENT_GOLD),
    ]))
    story.append(cover_line_tbl3)
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("STRICTLY CONFIDENTIAL  |  For Internal Use Only  |  Credit Committee Circulation",
                            styles["CoverConfidential"]))
    story.append(PageBreak())

    # ── Process body content (from TOC onwards) ──
    prev_was_divider = False
    for idx, line in enumerate(lines[body_start_idx:], start=body_start_idx):
        stripped = line.strip()

        # Table row detection: starts with | (fix rows missing trailing |)
        if stripped.startswith("|"):
            if not stripped.endswith("|"):
                stripped = stripped + " |"
            # Skip absurdly long separator rows in the table buffer stage
            if len(stripped) > 200 and stripped.count("-") / len(stripped) > 0.5:
                pipes = stripped.count("|")
                ncols = max(pipes - 1, 2)
                stripped = "| " + " | ".join(["---"] * ncols) + " |"
            table_buf.append(stripped)
            continue
        elif table_buf:
            _flush_table()

        if not stripped:
            continue

        # Skip HTML div tags and emoji from markdown
        if stripped.startswith("<div") or stripped.startswith("</div"):
            continue

        # Collapse consecutive dividers
        if stripped.startswith("---"):
            if prev_was_divider:
                continue
            prev_was_divider = True
        else:
            prev_was_divider = False

        if stripped.startswith("# "):
            text = stripped[2:]
            # Page break before major numbered sections and annexures (not TOC or non-sections)
            if _re.match(r"^\d+\.", text) or text.upper().startswith("ANNEXURE") or text.upper().startswith("APPENDIX") or text.upper().startswith("DISCLAIMER"):
                story.append(PageBreak())
            # Skip "Generation Metadata" heading - render inline
            if text.strip().lower() == "generation metadata":
                story.append(Spacer(1, 4*mm))
                story.append(Paragraph(text, styles["CamH2"]))
                continue
            # Section heading with blue left bar
            h1_tbl = Table([[Paragraph(text, styles["CamH1"])]], colWidths=[A4[0] - 30*mm])
            h1_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), SECTION_BG),
                ("LINEBEFORE", (0, 0), (0, -1), 3, BANK_BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(h1_tbl)
            story.append(Spacer(1, 3*mm))
        elif stripped.startswith("## "):
            section_text = stripped[3:]
            # Subsection heading with subtle bottom border
            story.append(Spacer(1, 2*mm))
            story.append(Paragraph(section_text, styles["CamH2"]))
            # Add subtle underline
            h2_line = Table([[""]], colWidths=[A4[0] - 30*mm])
            h2_line.setStyle(TableStyle([
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#b8c8dc")),
            ]))
            story.append(h2_line)
            story.append(Spacer(1, 1.5*mm))
            comment_text = section_comments.get(section_text.strip())
            if comment_text:
                comment_html = (
                    '<font name="Helvetica-Bold" color="#8b6d2f">RM Comment</font><br/>'
                    f'{_html_mod.escape(comment_text)}'
                )
                comment_tbl = Table([[Paragraph(comment_html, styles["CamComment"])]], colWidths=[A4[0] - 30*mm])
                comment_tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbef")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e6d7aa")),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT_GOLD),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(comment_tbl)
                story.append(Spacer(1, 3*mm))
        elif stripped.startswith("### ") or stripped.startswith("#### "):
            text = _re.sub(r"^#{3,4}\s+", "", stripped)
            story.append(Spacer(1, 1.5*mm))
            story.append(Paragraph(text, styles["CamH3"]))
        elif stripped.startswith("---"):
            # Subtle section divider
            story.append(Spacer(1, 3*mm))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:]
            text = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            story.append(Paragraph(f"\u2022 {text}", styles["CamBullet"]))
        elif stripped.startswith("*Source:") and stripped.endswith("*"):
            # Source tags — render in distinctive italic grey style
            source_text = stripped[1:-1]  # Remove surrounding asterisks
            story.append(Paragraph(source_text, styles["CamSource"]))
        else:
            text = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", stripped)
            text = _re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
            story.append(Paragraph(text, styles["CamBody"]))

    _flush_table()
    doc.build(story, onFirstPage=_first_page, onLaterPages=_header_footer)
    return buf.getvalue()

