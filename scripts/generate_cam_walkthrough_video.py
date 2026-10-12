from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
ASSET_DIR = OUTPUT_DIR / "video_assets"
SCREEN_DIR = ASSET_DIR / "screens"
SLIDE_DIR = ASSET_DIR / "slides"
AUDIO_DIR = ASSET_DIR / "audio"
VIDEO_DIR = ASSET_DIR / "scenes"
TMP_DIR = ASSET_DIR / "tmp"

CANVAS = (1920, 1080)
BG = "#09192F"
PANEL = "#0F2847"
CARD = "#122D50"
ACCENT = "#D6A528"
TEXT = "#F4F7FB"
SUBTEXT = "#A9BDD7"
MUTED = "#7F98B8"

FONT_REGULAR = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\segoeuib.ttf")
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


@dataclass(frozen=True)
class Scene:
    slug: str
    title: str
    caption: str
    narration: str
    image: str | None = None
    mode: str = "image"


STANDARD_SCENES = [
    Scene(
        slug="01_intro",
        title="CAM Intelligence Platform",
        caption="Corporate Lending Product Walkthrough",
        narration=(
            "This is the CAM Intelligence Platform, a corporate lending workflow that brings onboarding, "
            "analysis, documentation, and committee-ready memo generation into one workspace. "
            "In this demo environment, the platform is loaded with nineteen sample companies and six analyzed cases."
        ),
        mode="title",
    ),
    Scene(
        slug="02_dashboard",
        title="Portfolio Dashboard",
        caption="Instant visibility into analyzed cases, grades, and recommendations",
        narration=(
            "The dashboard gives credit teams an immediate portfolio view. "
            "You can see analyzed cases, recommendations, and grade distribution at a glance, "
            "then drill straight into the latest borrower assessments from the same screen."
        ),
        image="dashboard.png",
    ),
    Scene(
        slug="03_onboarding",
        title="Smart Onboarding",
        caption="Start with one identifier and structure the request up front",
        narration=(
            "Smart Onboard starts with a single identifier such as PAN, GSTIN, CIN, or company name. "
            "The platform auto-resolves borrower data, classifies the case as new-to-bank or existing-to-bank, "
            "captures facility type and amount, and prepares the case for downstream enrichment."
        ),
        image="onboard.png",
    ),
    Scene(
        slug="04_documents",
        title="Documents Workspace",
        caption="Evidence coverage, gap tracking, pack generation, and extraction control",
        narration=(
            "The document workspace acts as a controlled evidence layer. "
            "Teams can generate or backfill document packs, review coverage by category, "
            "spot data gaps, and run extraction so every narrative statement stays anchored to source artifacts."
        ),
        image="documents.png",
    ),
    Scene(
        slug="05_pipeline",
        title="Deterministic Pipeline",
        caption="Run ingestion, validation, benchmarking, policy, and narrative generation",
        narration=(
            "From Pipeline, users execute the deterministic analysis flow. "
            "The system chains ingestion, validation, benchmarking, policy logic, and narrative rendering, "
            "then stores the resulting score, grade, recommendation, and audit trail for each company."
        ),
        image="pipeline.png",
    ),
    Scene(
        slug="06_cases",
        title="Case Workbench",
        caption="Open any analyzed borrower and inspect the full credit file",
        narration=(
            "Cases become the working cockpit for underwriters. "
            "Each analyzed borrower can be reopened to inspect summary metrics, CAM text, validation exceptions, "
            "policy decisions, document evidence, extraction results, ETB analytics, pipeline logs, and the structured fact pack."
        ),
        image="cases.png",
    ),
    Scene(
        slug="07_cam_report",
        title="Committee-Ready CAM",
        caption="A full credit appraisal memorandum generated from the approved fact pack",
        narration=(
            "The full CAM report is generated in committee-ready format. "
            "It compiles borrower profile, business analysis, financial ratios, facility structure, security, "
            "risk assessment, compliance checks, peer benchmarks, and the final recommendation into a single shareable narrative."
        ),
        image="cam_fresh.png",
    ),
    Scene(
        slug="08_one_pager",
        title="Executive One-Page Memo",
        caption="A compact decision snapshot for quick senior review",
        narration=(
            "For senior reviewers, the one-page memo compresses the case into a decision snapshot. "
            "It highlights score breakdown, key strengths, risk flags, financial trend tables, collateral coverage, "
            "and the final credit view without opening the full report."
        ),
        image="one_pager.png",
    ),
    Scene(
        slug="09_settings",
        title="Configurable Narrative Layer",
        caption="Switch provider and narrative mode without changing code",
        narration=(
            "Configuration stays exposed instead of buried in code. "
            "Operations teams can switch narrative mode between template and LLM, choose providers, "
            "and manage the engines and benchmarks that drive the platform's scoring and memo outputs. "
            "In this environment, the active local provider is Ollama."
        ),
        image="settings.png",
    ),
    Scene(
        slug="10_outro",
        title="From Intake To Credit Decision",
        caption="Onboard the borrower, gather evidence, run analysis, and publish decision-ready outputs",
        narration=(
            "End to end, CAM turns fragmented corporate lending work into a reproducible pipeline: "
            "onboard the borrower, gather evidence, run analysis, and publish decision-ready outputs in HTML, PDF, and memo form."
        ),
        mode="title",
    ),
]

SALES_SCENES = [
    Scene(
        slug="01_intro",
        title="CAM Intelligence Platform",
        caption="Accelerate corporate lending decisions with auditable AI-assisted workflows",
        narration=(
            "CAM helps lenders compress borrower intake, document chasing, analysis, and memo writing into one product. "
            "Instead of working across spreadsheets, shared drives, and email trails, teams move from opportunity to decision-ready case inside a single platform."
        ),
        mode="title",
    ),
    Scene(
        slug="02_dashboard",
        title="Portfolio Visibility That Sells",
        caption="Show pipeline momentum, risk posture, and decision status in one screen",
        narration=(
            "The dashboard gives business, credit, and management teams a live operating view of the book. "
            "You can immediately surface active cases, recommendation trends, and borrower quality, making reviews faster and customer conversations sharper."
        ),
        image="dashboard.png",
    ),
    Scene(
        slug="03_onboarding",
        title="Borrower Intake In Minutes",
        caption="Start from PAN, GSTIN, CIN, or company name and reduce onboarding friction",
        narration=(
            "Smart Onboard is designed to cut turnaround time at the very first step. "
            "With a single borrower identifier, the platform resolves company data, frames the facility request, and gets the case ready for enrichment without manual rekeying."
        ),
        image="onboard.png",
    ),
    Scene(
        slug="04_documents",
        title="A Structured Digital Credit Room",
        caption="Organize evidence, close gaps, and control document readiness",
        narration=(
            "The document workspace turns scattered borrower files into a structured evidence layer. "
            "Teams can generate packs, backfill missing artifacts, track completeness, and run extraction so relationship managers and analysts spend less time chasing paperwork."
        ),
        image="documents.png",
    ),
    Scene(
        slug="05_pipeline",
        title="Underwriting At Product Speed",
        caption="Automate validation, scoring, benchmarking, and recommendation flow",
        narration=(
            "This is where CAM creates real commercial leverage. "
            "The deterministic pipeline runs ingestion, validation, benchmarking, policy logic, and narrative generation in sequence, giving lenders faster decisions with far better consistency."
        ),
        image="pipeline.png",
    ),
    Scene(
        slug="06_cases",
        title="One Workspace For Credit Teams",
        caption="Bring reviewers, underwriters, and approvers onto the same case record",
        narration=(
            "Each case becomes a shared operating workspace. "
            "Analysts can review scores, exceptions, evidence, logs, and structured fact packs in one place, which reduces handoffs and improves confidence before the case reaches committee."
        ),
        image="cases.png",
    ),
    Scene(
        slug="07_cam_report",
        title="Credit Memo Generation That Scales",
        caption="Produce committee-ready CAM reports without rebuilding the story each time",
        narration=(
            "The generated CAM report is the product's strongest commercial outcome. "
            "It packages borrower profile, financial analysis, risk commentary, facility structure, compliance checks, and recommendation into a polished memo that is ready for internal circulation."
        ),
        image="cam_fresh.png",
    ),
    Scene(
        slug="08_one_pager",
        title="Executive Storytelling Built In",
        caption="Give decision makers the full case in one glance",
        narration=(
            "For senior approvers, the one-page memo distills the opportunity into a clean decision snapshot. "
            "It highlights strengths, risks, score composition, financial movement, and the final credit view so leadership can move quickly without losing context."
        ),
        image="one_pager.png",
    ),
    Scene(
        slug="09_settings",
        title="Deployment Flexibility",
        caption="Template or LLM narrative modes, provider control, and local deployment options",
        narration=(
            "CAM is designed to fit enterprise constraints, not fight them. "
            "Teams can choose template or LLM narrative modes, control providers, and operate with a local stack, which makes the platform easier to position for regulated credit environments."
        ),
        image="settings.png",
    ),
    Scene(
        slug="10_outro",
        title="Sell Speed, Control, And Confidence",
        caption="Win more lending opportunities with faster, more consistent credit decisions",
        narration=(
            "The value proposition is simple: faster turnaround, cleaner evidence, better underwriting consistency, and decision-ready outputs for every stakeholder in the credit chain. "
            "CAM helps lenders scale corporate credit without scaling manual complexity."
        ),
        mode="title",
    ),
]

AGGRESSIVE_SCENES = [
    Scene(
        slug="01_intro",
        title="CAM Intelligence Platform",
        caption="Stop losing lending capacity to manual credit operations",
        narration=(
            "Most corporate lending teams are still burning time on fragmented intake, document chasing, spreadsheet analysis, and memo rewriting. "
            "CAM replaces that drag with a productized credit workflow that moves borrowers from first touch to decision-ready case far faster."
        ),
        mode="title",
    ),
    Scene(
        slug="02_dashboard",
        title="Expose Bottlenecks Immediately",
        caption="See decision flow, borrower quality, and pipeline status without waiting for updates",
        narration=(
            "The dashboard makes operating friction visible. "
            "Instead of asking for status updates across teams, leaders can see analyzed cases, risk posture, and recommendation flow instantly, which means fewer blind spots and faster commercial follow-through."
        ),
        image="dashboard.png",
    ),
    Scene(
        slug="03_onboarding",
        title="Kill Slow Borrower Intake",
        caption="Start with one identifier and eliminate repetitive data entry",
        narration=(
            "Manual onboarding is one of the first places lenders lose speed. "
            "CAM cuts that waste by resolving borrower context from a single identifier, structuring the request immediately, and getting the case ready for underwriting without clerical churn."
        ),
        image="onboard.png",
    ),
    Scene(
        slug="04_documents",
        title="Turn Document Chaos Into Control",
        caption="Stop chasing files across mailboxes, folders, and disconnected teams",
        narration=(
            "Borrower documents usually sit in scattered channels with no real control layer. "
            "CAM turns them into a managed digital credit room with completeness tracking, gap visibility, artifact generation, and extraction, so the team can work the case instead of hunting for files."
        ),
        image="documents.png",
    ),
    Scene(
        slug="05_pipeline",
        title="Scale Decisions Without Scaling Headcount",
        caption="Automate validation, scoring, benchmarking, and recommendation generation",
        narration=(
            "This is where the economics change. "
            "The pipeline runs ingestion, validation, benchmarking, policy logic, and narrative generation in a repeatable sequence, helping lenders process more cases with greater consistency instead of adding more manual effort."
        ),
        image="pipeline.png",
    ),
    Scene(
        slug="06_cases",
        title="One Case Record, No Excuses",
        caption="Give credit teams a single source of truth for every underwriting discussion",
        narration=(
            "When analysts, reviewers, and approvers work from different versions of the case, quality drops and cycle time expands. "
            "CAM brings scores, exceptions, evidence, logs, and fact packs into one case record, reducing rework and tightening decision discipline."
        ),
        image="cases.png",
    ),
    Scene(
        slug="07_cam_report",
        title="Replace Memo Rework With Instant Output",
        caption="Generate committee-ready CAM reports at the speed of the workflow",
        narration=(
            "Credit memo creation is usually a slow, repetitive bottleneck. "
            "CAM converts structured case output into a polished committee-ready memorandum, so teams stop rebuilding the same story manually and start moving decisions forward faster."
        ),
        image="cam_fresh.png",
    ),
    Scene(
        slug="08_one_pager",
        title="Win Senior Attention Faster",
        caption="Give decision makers the signal without burying them in operating detail",
        narration=(
            "Executives do not want to dig through a full case every time. "
            "The one-page memo gives them the decision, score logic, strengths, risks, and financial story in seconds, which improves responsiveness at the exact moment approvals matter."
        ),
        image="one_pager.png",
    ),
    Scene(
        slug="09_settings",
        title="Enterprise Ready, Not Experimental",
        caption="Control narrative mode, provider choice, and deployment model to fit regulated environments",
        narration=(
            "If a platform cannot adapt to enterprise constraints, it will not survive procurement or risk review. "
            "CAM supports template and LLM modes, provider control, and local deployment options, giving teams a practical path to adoption instead of a lab demo."
        ),
        image="settings.png",
    ),
    Scene(
        slug="10_outro",
        title="Move Faster Or Stay Manual",
        caption="Cut turnaround time, improve underwriting consistency, and ship decision-ready output at scale",
        narration=(
            "The commercial message is direct: lenders that keep relying on manual credit assembly will keep losing time, throughput, and control. "
            "CAM gives you speed to decision, stronger operating discipline, and output quality that scales with the business."
        ),
        mode="title",
    ),
]

VARIANT_SCENES = {
    "aggressive": AGGRESSIVE_SCENES,
    "standard": STANDARD_SCENES,
    "sales": SALES_SCENES,
}


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def output_paths(variant: str) -> tuple[Path, Path]:
    if variant == "aggressive":
        return (
            OUTPUT_DIR / "CAM_Product_Walkthrough_Aggressive.mp4",
            OUTPUT_DIR / "CAM_Product_Walkthrough_Aggressive_Transcript.txt",
        )
    if variant == "sales":
        return (
            OUTPUT_DIR / "CAM_Product_Walkthrough_Sales.mp4",
            OUTPUT_DIR / "CAM_Product_Walkthrough_Sales_Transcript.txt",
        )
    return (
        OUTPUT_DIR / "CAM_Product_Walkthrough.mp4",
        OUTPUT_DIR / "CAM_Product_Walkthrough_Transcript.txt",
    )


def ensure_dirs() -> None:
    for path in [ASSET_DIR, SLIDE_DIR, AUDIO_DIR, VIDEO_DIR, TMP_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def fetch_json(url: str) -> dict:
    with urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path.exists():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def rounded_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, radius: int) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_shadow(base: Image.Image, box: tuple[int, int, int, int], radius: int = 28) -> None:
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(box, radius=radius, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    base.alpha_composite(shadow)


def fit_image(img: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    fitted = img.copy()
    fitted.thumbnail(max_size, Image.Resampling.LANCZOS)
    return fitted


def markdown_to_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"</?div[^>]*>", "", text)
    h = html.escape(text)

    def table_repl(match: re.Match[str]) -> str:
        block = match.group(0)
        rows = [row for row in block.strip().split("\n") if row.strip()]
        if len(rows) < 2:
            return block
        parts = ["<table>"]
        for idx, row in enumerate(rows):
            if re.fullmatch(r"\|[\s\-:|]+\|", row):
                continue
            cells = row.split("|")[1:-1]
            tag = "th" if idx == 0 else "td"
            parts.append("<tr>" + "".join(f"<{tag}>{cell.strip()}</{tag}>" for cell in cells) + "</tr>")
        parts.append("</table>")
        return "".join(parts)

    h = re.sub(r"((?:^\|.+\|$\n?)+)", table_repl, h, flags=re.MULTILINE)
    h = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", h, flags=re.MULTILINE)
    h = re.sub(r"^### (.+)$", r"<h3>\1</h3>", h, flags=re.MULTILINE)
    h = re.sub(r"^## (.+)$", r"<h2>\1</h2>", h, flags=re.MULTILINE)
    h = re.sub(r"^# (.+)$", r"<h1>\1</h1>", h, flags=re.MULTILINE)
    h = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", h)
    h = re.sub(r"\*(.+?)\*", r"<em>\1</em>", h)
    h = re.sub(r"^---+$", "<hr>", h, flags=re.MULTILINE)
    h = re.sub(r"^[\-\*] (.+)$", r"<li>\1</li>", h, flags=re.MULTILINE)
    h = re.sub(r"((?:<li>.+</li>\n?)+)", r"<ul>\1</ul>", h)
    h = re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", h, flags=re.MULTILINE)
    h = re.sub(r"\n{2,}", "</p><p>", h)
    h = "<p>" + h + "</p>"
    h = re.sub(r"<p>\s*<(h[1-4]|table|ul|ol|hr|li)", r"<\1", h)
    h = re.sub(r"</(h[1-4]|table|ul|ol|hr|li)>\s*</p>", r"</\1>", h)
    return h


def generate_fresh_cam_screen(entity_id: str = "INFY001") -> Path:
    case_data = fetch_json(f"http://127.0.0.1:8001/api/cases/{entity_id}")
    cam_html = markdown_to_html(case_data.get("cam_text", ""))
    company_name = html.escape(case_data.get("company_name", entity_id))
    recommendation = html.escape((case_data.get("recommendation") or "").replace("_", " "))
    risk_grade = html.escape(str(case_data.get("risk_grade", "")))
    score = html.escape(str(case_data.get("composite_score", "")))

    html_path = TMP_DIR / "cam_fresh_view.html"
    screenshot_path = SCREEN_DIR / "cam_fresh.png"
    html_path.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Fresh CAM View</title>
  <style>
    :root {{
      --bg-body:#f0f2f7; --bg-sidebar:#003366; --bg-card:#ffffff; --bg-card-alt:#f7f9fc;
      --accent:#003366; --gold:#c9a227; --border:#cbd5e0; --border-light:#e2e8f0;
      --text:#1a202c; --text-sec:#4a5568; --muted:#718096; --red:#991b1b; --red-bg:#fee2e2;
      --red-border:#fca5a5; --green:#166534; --green-bg:#dcfce7; --green-border:#86efac;
      --shadow-sm:0 1px 3px rgba(0,0,0,.08); --radius:6px; --sidebar-w:220px; --font:'Segoe UI', Arial, sans-serif;
    }}
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:var(--font); background:var(--bg-body); color:var(--text); }}
    .app-shell {{ display:flex; min-height:100vh; }}
    .sidebar {{ width:var(--sidebar-w); background:var(--bg-sidebar); color:#fff; position:fixed; inset:0 auto 0 0; }}
    .sidebar-brand {{ padding:14px 16px; background:rgba(0,0,0,.2); display:flex; align-items:center; gap:10px; border-bottom:1px solid rgba(255,255,255,.1); }}
    .brand-icon {{ width:36px; height:36px; border-radius:6px; background:var(--gold); color:#003366; display:flex; align-items:center; justify-content:center; font-weight:800; }}
    .sidebar-brand h2 {{ font-size:13.5px; font-weight:700; }}
    .version {{ font-size:10px; color:rgba(255,255,255,.45); margin-top:2px; display:block; }}
    .nav-menu {{ list-style:none; padding:6px 0; }}
    .nav-menu li {{ padding:10px 16px; color:rgba(255,255,255,.76); font-size:12.5px; }}
    .nav-menu li.active {{ background:rgba(255,255,255,.13); color:#fff; border-left:3px solid var(--gold); font-weight:600; }}
    .sidebar-footer {{ position:absolute; bottom:10px; left:16px; font-size:10px; color:rgba(255,255,255,.65); }}
    .main-content {{ margin-left:var(--sidebar-w); flex:1; padding:20px 24px; }}
    .page-header {{ display:flex; align-items:center; gap:14px; margin-bottom:18px; padding-bottom:12px; border-bottom:2px solid var(--border-light); }}
    .page-header h1 {{ font-size:18px; font-weight:700; color:var(--accent); flex:1; }}
    .btn-ghost {{ border:1px solid var(--border); border-radius:6px; padding:7px 14px; background:transparent; color:var(--text-sec); font-size:12.5px; }}
    .badge {{ display:inline-flex; align-items:center; padding:4px 14px; border-radius:12px; font-size:12px; font-weight:600; }}
    .badge-red {{ background:var(--red-bg); color:var(--red); border:1px solid var(--red-border); }}
    .metric-cards {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:16px; }}
    .metric-card {{ background:var(--bg-card); border:1px solid var(--border-light); border-top:3px solid var(--accent); border-radius:6px; padding:10px 12px; box-shadow:var(--shadow-sm); }}
    .metric-label {{ font-size:10.5px; color:var(--text-sec); text-transform:uppercase; letter-spacing:.5px; margin-bottom:3px; }}
    .metric-value {{ font-size:18px; font-weight:700; color:var(--accent); }}
    .metric-sub {{ font-size:11px; color:var(--muted); margin-top:3px; }}
    .tabs {{ display:flex; gap:2px; background:var(--border-light); border-radius:6px 6px 0 0; padding:3px; border-bottom:1px solid var(--border); }}
    .tabs button {{ padding:6px 18px; border-radius:4px; font-size:12px; font-weight:600; color:var(--text-sec); background:transparent; border:1px solid transparent; }}
    .tabs button.active {{ background:#fff; color:var(--accent); border-color:var(--border-light); box-shadow:var(--shadow-sm); }}
    .card {{ background:#fff; border:1px solid var(--border-light); border-radius:6px; box-shadow:var(--shadow-sm); padding:16px; }}
    .cam-actions {{ display:flex; gap:8px; margin-bottom:12px; }}
    .btn-secondary {{ background:#e2e8f0; color:#374151; border:1px solid #d1d5db; border-radius:6px; padding:5px 12px; font-size:11.5px; }}
    .cam-viewer {{ font-family:Georgia,serif; font-size:13.5px; line-height:1.7; color:#1a202c; max-height:640px; overflow:hidden; }}
    .cam-viewer h1 {{ font-size:20px; font-weight:700; color:var(--accent); border-bottom:2px solid var(--accent); padding-bottom:8px; margin:0 0 18px; }}
    .cam-viewer h2 {{ font-size:16px; font-weight:700; color:var(--accent); border-left:4px solid var(--gold); padding-left:10px; margin:24px 0 12px; }}
    .cam-viewer h3 {{ font-size:14px; font-weight:700; color:#1e3a5f; margin:18px 0 8px; }}
    .cam-viewer h4 {{ font-size:13px; font-weight:700; color:var(--text-sec); margin:12px 0 6px; }}
    .cam-viewer p {{ margin-bottom:10px; }}
    .cam-viewer ul,.cam-viewer ol {{ padding-left:20px; margin-bottom:10px; }}
    .cam-viewer li {{ margin-bottom:4px; }}
    .cam-viewer table {{ width:100%; border-collapse:collapse; font-size:12.5px; margin:12px 0; }}
    .cam-viewer th {{ background:#eef2f9; color:var(--accent); font-weight:700; font-size:11.5px; padding:8px 10px; border:1px solid var(--border); text-align:left; }}
    .cam-viewer td {{ padding:7px 10px; border:1px solid var(--border-light); vertical-align:top; }}
    .cam-viewer tr:nth-child(even) td {{ background:#f8fafc; }}
    .cam-viewer hr {{ border:none; border-top:1px solid var(--border-light); margin:20px 0; }}
    .cam-viewer strong {{ color:#1a202c; }}
  </style>
</head>
<body>
  <div class="app-shell">
    <nav class="sidebar">
      <div class="sidebar-brand">
        <div class="brand-icon">◆</div>
        <div><h2>CAM Intel</h2><span class="version">v2.0</span></div>
      </div>
      <ul class="nav-menu">
        <li>Dashboard</li>
        <li class="active">Cases</li>
        <li>Smart Onboard</li>
        <li>Documents</li>
        <li>Pipeline</li>
        <li>Reports</li>
        <li>Settings</li>
      </ul>
      <div class="sidebar-footer">LLM ollama</div>
    </nav>
    <main class="main-content">
      <div class="page-header">
        <button class="btn-ghost">← Back to Cases</button>
        <h1>{company_name}</h1>
        <span class="badge badge-red">{recommendation}</span>
      </div>
      <div class="metric-cards">
        <div class="metric-card"><div class="metric-label">Composite</div><div class="metric-value">{score}</div><div class="metric-sub">Grade {risk_grade}</div></div>
        <div class="metric-card"><div class="metric-label">Financial</div><div class="metric-value">0</div></div>
        <div class="metric-card"><div class="metric-label">Conduct</div><div class="metric-value">0</div></div>
        <div class="metric-card"><div class="metric-label">Governance</div><div class="metric-value">0</div></div>
        <div class="metric-card"><div class="metric-label">Market</div><div class="metric-value">0</div></div>
      </div>
      <div class="tabs">
        <button>Summary</button>
        <button class="active">CAM</button>
        <button>Validation</button>
        <button>Policy</button>
        <button>Documents</button>
        <button>Extraction</button>
        <button>ETB</button>
        <button>Pipeline Log</button>
        <button>Fact Pack</button>
      </div>
      <div class="card">
        <div class="cam-actions"><button class="btn-secondary">⬇ Download .md</button></div>
        <div class="cam-viewer">{cam_html}</div>
      </div>
    </main>
  </div>
</body>
</html>
""",
        encoding="utf-8",
    )

    if not EDGE.exists():
        raise FileNotFoundError(f"Edge not found at {EDGE}")
    run(
        [
            str(EDGE),
            "--headless",
            "--disable-gpu",
            "--window-size=1600,1200",
            "--virtual-time-budget=4000",
            f"--screenshot={screenshot_path}",
            html_path.as_uri(),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return screenshot_path


def title_bullets(variant: str, is_final: bool) -> list[str]:
    if variant == "aggressive" and not is_final:
        return [
            "Eliminate avoidable cycle time across intake, documents, analysis, and memo drafting",
            "Increase lending throughput without inheriting the same level of operational drag",
            "Position credit operations as a scalable product capability, not a manual bottleneck",
        ]
    if variant == "aggressive" and is_final:
        return [
            "Reduce turnaround time where manual workflows currently slow revenue conversion",
            "Create a tighter, more defensible underwriting process with better output quality",
            "Compete on speed, control, and repeatability instead of adding more manual layers",
        ]
    if variant == "sales" and not is_final:
        return [
            "Shorten corporate lending turnaround from intake to credit memo",
            "Replace fragmented analyst workflows with one product-led operating model",
            "Deliver decision-ready outputs for RM teams, underwriters, and approvers",
        ]
    if variant == "sales" and is_final:
        return [
            "Lead with speed to decision and a stronger borrower experience",
            "Differentiate on consistency, traceability, and committee-ready output quality",
            "Scale lending throughput without adding the same level of manual overhead",
        ]
    if not is_final:
        return [
            "Unified workflow for onboarding, documents, pipeline execution, and memo publishing",
            "Deterministic engines for validation, benchmarking, policy logic, and risk scoring",
            "Committee-ready outputs across CAM HTML, PDF, and executive one-page memo",
        ]
    return [
        "Reduce manual stitching across borrower intake, evidence review, and credit writing",
        "Preserve traceability from source documents through the final recommendation",
        "Deliver reusable credit outputs for analysts, approvers, and committee reviewers",
    ]


def create_title_slide(scene: Scene, index: int, total: int, variant: str) -> Path:
    canvas = Image.new("RGBA", CANVAS, BG)
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(FONT_BOLD, 78)
    heading_font = load_font(FONT_BOLD, 36)
    body_font = load_font(FONT_REGULAR, 32)
    small_font = load_font(FONT_REGULAR, 24)

    draw.rectangle((0, 0, CANVAS[0], 18), fill=ACCENT)
    draw.rectangle((110, 130, 430, 160), fill=ACCENT)
    draw.text((110, 210), scene.title, font=title_font, fill=TEXT)
    draw.text((110, 315), scene.caption, font=heading_font, fill=SUBTEXT)

    panel_box = (110, 430, 1810, 885)
    draw_shadow(canvas, panel_box)
    rounded_panel(draw, panel_box, PANEL, 32)

    bullets = title_bullets(variant, index == total)

    draw.text((165, 485), "Walkthrough Highlights", font=heading_font, fill=ACCENT)
    y = 565
    for bullet in bullets:
        wrapped = textwrap.wrap(bullet, width=60)
        draw.ellipse((170, y + 14, 188, y + 32), fill=ACCENT)
        for line in wrapped:
            draw.text((210, y), line, font=body_font, fill=TEXT)
            y += 44
        y += 18

    footer_label = "CAM Product Walkthrough"
    if variant == "sales":
        footer_label = "CAM Sales Walkthrough"
    if variant == "aggressive":
        footer_label = "CAM Aggressive Sales Walkthrough"
    draw.text((110, 955), footer_label, font=small_font, fill=MUTED)

    out_path = SLIDE_DIR / f"{variant}_{scene.slug}.png"
    canvas.convert("RGB").save(out_path, quality=95)
    return out_path


def create_image_slide(scene: Scene, index: int, variant: str) -> Path:
    canvas = Image.new("RGBA", CANVAS, BG)
    draw = ImageDraw.Draw(canvas)

    title_font = load_font(FONT_BOLD, 56)
    caption_font = load_font(FONT_REGULAR, 30)
    label_font = load_font(FONT_BOLD, 24)
    body_font = load_font(FONT_REGULAR, 26)

    draw.rectangle((0, 0, CANVAS[0], 14), fill=ACCENT)
    draw.text((120, 78), scene.title, font=title_font, fill=TEXT)

    caption_lines = textwrap.wrap(scene.caption, width=72)
    cap_y = 158
    for line in caption_lines:
        draw.text((120, cap_y), line, font=caption_font, fill=SUBTEXT)
        cap_y += 38

    frame_box = (120, 300, 1800, 900)
    draw_shadow(canvas, frame_box)
    rounded_panel(draw, frame_box, CARD, 34)

    img_path = SCREEN_DIR / scene.image if scene.image else None
    if not img_path or not img_path.exists():
        raise FileNotFoundError(f"Missing screenshot for scene {scene.slug}: {img_path}")

    screen = Image.open(img_path).convert("RGB")
    fitted = fit_image(screen, (1610, 560))
    img_x = frame_box[0] + (frame_box[2] - frame_box[0] - fitted.width) // 2
    img_y = frame_box[1] + 28
    canvas.paste(fitted, (img_x, img_y))

    note_box = (170, 890, 1750, 1002)
    rounded_panel(draw, note_box, PANEL, 22)
    note_lines = wrap_lines(draw, scene.narration, body_font, 1510)[:3]
    note_y = 922
    for line in note_lines:
        draw.text((205, note_y), line, font=body_font, fill=TEXT)
        note_y += 32

    footer = "Corporate Lending | Credit Appraisal Memorandum Automation"
    if variant == "sales":
        footer = "Corporate Lending | Faster Decisions, Cleaner Evidence, Stronger Credit Stories"
    if variant == "aggressive":
        footer = "Corporate Lending | Replace Manual Friction With Scalable Credit Operations"
    draw.text((120, 1018), footer, font=label_font, fill=MUTED)

    out_path = SLIDE_DIR / f"{variant}_{scene.slug}.png"
    canvas.convert("RGB").save(out_path, quality=95)
    return out_path


def create_slides(scenes: list[Scene], variant: str) -> list[Path]:
    slides: list[Path] = []
    total = len(scenes)
    for idx, scene in enumerate(scenes, start=1):
        if scene.mode == "title":
            slides.append(create_title_slide(scene, idx, total, variant))
        else:
            slides.append(create_image_slide(scene, idx, variant))
    return slides


def write_transcript(scenes: list[Scene], transcript_file: Path, variant: str) -> None:
    title = "CAM Product Walkthrough Transcript"
    if variant == "sales":
        title = "CAM Sales Walkthrough Transcript"
    if variant == "aggressive":
        title = "CAM Aggressive Sales Walkthrough Transcript"
    lines = [title, ""]
    for idx, scene in enumerate(scenes, start=1):
        lines.append(f"Scene {idx:02d} | {scene.title}")
        lines.append(scene.narration)
        lines.append("")
    transcript_file.write_text("\n".join(lines), encoding="utf-8")


def build_ssml(text: str, variant: str) -> str:
    safe = html.escape(text)
    rate = "-2%"
    if variant == "sales":
        rate = "+4%"
    if variant == "aggressive":
        rate = "+8%"
    return (
        "<speak version='1.0' xml:lang='en-US'>"
        f"<prosody rate='{rate}' pitch='+0st'>"
        f"{safe}"
        "</prosody>"
        "</speak>"
    )


def ps_single_quote(value: str) -> str:
    return value.replace("'", "''")


def synthesize_scene_audio(scene: Scene, variant: str) -> Path:
    wav_path = AUDIO_DIR / f"{variant}_{scene.slug}.wav"
    ssml = build_ssml(scene.narration, variant)
    ps_script = TMP_DIR / f"{variant}_{scene.slug}.ps1"
    wav_path_ps = ps_single_quote(str(wav_path))
    ps_script.write_text(
        "\n".join(
            [
                "Add-Type -AssemblyName System.Speech",
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer",
                "$synth.Rate = 0",
                "$synth.Volume = 100",
                f"$synth.SetOutputToWaveFile('{wav_path_ps}')",
                f"$ssml = @'\n{ssml}\n'@",
                "$synth.SpeakSsml($ssml)",
                "$synth.Dispose()",
            ]
        ),
        encoding="utf-8",
    )
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_script)])
    return wav_path


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def render_scene_video(slide: Path, audio: Path, slug: str, variant: str) -> Path:
    duration = ffprobe_duration(audio) + 0.8
    fade_out = max(duration - 0.6, 0.2)
    out_path = VIDEO_DIR / f"{variant}_{slug}.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(slide),
            "-i",
            str(audio),
            "-t",
            f"{duration:.3f}",
            "-filter_complex",
            (
                f"[0:v]fps=30,format=yuv420p,"
                f"fade=t=in:st=0:d=0.45,"
                f"fade=t=out:st={fade_out:.3f}:d=0.55[v];"
                f"[1:a]afade=t=in:st=0:d=0.20,"
                f"afade=t=out:st={fade_out:.3f}:d=0.55[a]"
            ),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out_path


def concat_videos(scene_videos: list[Path], final_video: Path, variant: str) -> None:
    concat_file = TMP_DIR / f"{variant}_concat.txt"
    concat_lines = []
    for path in scene_videos:
        concat_lines.append(f"file '{ps_single_quote(str(path))}'")
    concat_file.write_text(
        "\n".join(concat_lines),
        encoding="utf-8",
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(final_video),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def verify_assets(scenes: list[Scene]) -> None:
    generate_fresh_cam_screen()
    required = [scene.image for scene in scenes if scene.image]
    missing = [name for name in required if not (SCREEN_DIR / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required screenshots in output/video_assets/screens: " + ", ".join(missing)
        )
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg and ffprobe must be available on PATH.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate narrated CAM walkthrough videos.")
    parser.add_argument(
        "--variant",
        choices=sorted(VARIANT_SCENES.keys()),
        default="standard",
        help="Walkthrough style to generate.",
    )
    args = parser.parse_args()
    scenes = VARIANT_SCENES[args.variant]
    final_video, transcript_file = output_paths(args.variant)

    ensure_dirs()
    verify_assets(scenes)
    slides = create_slides(scenes, args.variant)
    write_transcript(scenes, transcript_file, args.variant)

    scene_videos: list[Path] = []
    for scene, slide in zip(scenes, slides, strict=True):
        audio = synthesize_scene_audio(scene, args.variant)
        scene_videos.append(render_scene_video(slide, audio, scene.slug, args.variant))

    concat_videos(scene_videos, final_video, args.variant)
    print(f"Generated walkthrough video: {final_video}")
    print(f"Generated transcript: {transcript_file}")


if __name__ == "__main__":
    main()
