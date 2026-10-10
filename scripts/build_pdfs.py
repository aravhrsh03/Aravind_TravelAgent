"""Markdown deliverables -> styled PDFs via headless Chrome/Edge (no extra Python deps).

    python scripts/build_pdfs.py
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS = [  # (markdown source, pdf target)
    ("design/Design_Document.md", "design/Design_Document.pdf"),
    ("docs/API_Documentation.md", "docs/API_Documentation.pdf"),
    ("docs/Dataset_Details.md", "docs/Dataset_Details.pdf"),
    ("eval/results/Evaluation_Report.md", "docs/Evaluation_Report.pdf"),
    ("PROJECT_EXPLANATION.md", "docs/Project_Explanation.pdf"),
    ("docs/Presentation_Prep.md", "docs/Presentation_Prep.pdf"),
    ("docs/Setup_Guide.md", "docs/Setup_Guide.pdf"),
    ("docs/Test_Inputs.md", "docs/Test_Inputs.pdf"),
]
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            shutil.which("chromium") or "", shutil.which("google-chrome") or ""]

CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1f2933; }
h1 { color: #24544F; border-bottom: 3px solid #B4492A; padding-bottom: 6px; font-size: 22pt; }
h2 { color: #24544F; margin-top: 22px; border-bottom: 1px solid #D9CDB8; padding-bottom: 3px; }
h3 { color: #2F6F6B; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9.2pt; page-break-inside: auto; }
th { background: #F3ECE0; text-align: left; }
th, td { border: 1px solid #D9CDB8; padding: 4px 7px; vertical-align: top; }
tr { page-break-inside: avoid; }
code { background: #f1f3f5; padding: 1px 4px; border-radius: 3px; font-size: 9pt; }
pre { background: #f6f8fa; border: 1px solid #e1e4e8; padding: 8px; font-size: 8.2pt; white-space: pre-wrap;
      word-break: break-word; page-break-inside: auto; }
pre code { background: none; padding: 0; }
blockquote { border-left: 4px solid #B4492A; margin: 8px 0; padding: 4px 12px; background: #FBF3E6; }
img { max-width: 100%; }
hr { border: none; border-top: 1px solid #D9CDB8; }
"""


def browser() -> str:
    for b in BROWSERS:
        if b and Path(b).exists():
            return b
    raise SystemExit("No Chrome/Edge found for PDF rendering.")


def gfm_lists(text: str) -> str:
    """GitHub renders a list right after a paragraph line; Python-Markdown needs a blank line first."""
    out, in_code = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        is_item = bool(re.match(r"\s*([-*]|\d+\.)\s", line))
        prev = out[-1] if out else ""
        if not in_code and is_item and prev.strip() and not re.match(r"\s*([-*]|\d+\.)\s", prev) \
                and not prev.lstrip().startswith(("|", ">")):
            out.append("")
        out.append(line)
    return "\n".join(out)


def render(src: Path, dst: Path, exe: str) -> None:
    html = markdown.markdown(gfm_lists(src.read_text(encoding="utf-8")),
                             extensions=["tables", "fenced_code", "sane_lists", "toc"])
    page = src.with_suffix(".print.html")  # next to the source so relative image paths resolve
    page.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{html}</body></html>",
                    encoding="utf-8")
    profile = tempfile.mkdtemp()
    try:
        subprocess.run([exe, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}", "--no-pdf-header-footer",
                        f"--print-to-pdf={dst}", page.resolve().as_uri()], check=True, capture_output=True, timeout=120)
    finally:
        page.unlink(missing_ok=True)
        shutil.rmtree(profile, ignore_errors=True)
    print(f"{src.relative_to(ROOT)} -> {dst.relative_to(ROOT)} ({dst.stat().st_size // 1024} KB)")


def main() -> None:
    exe = browser()
    for s, d in DOCS:
        src, dst = ROOT / s, ROOT / d
        if src.exists():
            render(src, dst, exe)
        else:
            print(f"skip (missing): {s}")


if __name__ == "__main__":
    main()
