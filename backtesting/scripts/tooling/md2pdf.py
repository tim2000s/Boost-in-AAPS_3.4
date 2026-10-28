#!/usr/bin/env python3
"""Markdown to PDF for the Boost reports, styled for reading rather than for the terminal.

Takes one or more markdown files and writes a single PDF. Where several are given they are
concatenated with a page break between, which is how a repository's set of reports is put on Drive
as one document.

Usage: python3 md2pdf.py --out FILE.pdf --title "Document title" a.md b.md ...
"""
import argparse
import re

import markdown
from weasyprint import CSS, HTML

CSS_TEXT = """
@page { size: A4; margin: 20mm 18mm 18mm 18mm;
        @bottom-center { content: counter(page); font: 9pt Georgia, serif; color: #666; } }
body { font: 10.5pt/1.5 Georgia, 'Times New Roman', serif; color: #1a1a1a; }
h1 { font-size: 17pt; margin: 0 0 4mm 0; line-height: 1.25; }
h2 { font-size: 12.5pt; margin: 7mm 0 2mm 0; border-bottom: 0.5pt solid #ccc;
     padding-bottom: 1mm; }
h3 { font-size: 11pt; margin: 5mm 0 1.5mm 0; }
p { margin: 0 0 2.6mm 0; text-align: justify; hyphens: auto; }
em { color: #444; }
code { font: 9pt 'SF Mono', Menlo, monospace; background: #f4f4f4; padding: 0 1mm; }
pre { font: 8.5pt/1.35 'SF Mono', Menlo, monospace; background: #f7f7f7;
      padding: 2.5mm; border-left: 2pt solid #ccc; white-space: pre-wrap; }
table { border-collapse: collapse; width: 100%; margin: 3mm 0 4mm 0; font-size: 8.8pt; }
th { text-align: left; border-bottom: 1pt solid #333; padding: 1.2mm 2mm;
     font-weight: bold; }
td { border-bottom: 0.4pt solid #ddd; padding: 1.1mm 2mm; vertical-align: top; }
tr { page-break-inside: avoid; }
h1, h2, h3 { page-break-after: avoid; }
blockquote { margin: 0 0 3mm 4mm; color: #555; font-style: italic; }
.docbreak { page-break-before: always; }
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default=None)
    a = ap.parse_args()

    parts = []
    for i, f in enumerate(a.files):
        txt = open(f).read()
        # a leading H1 in a continuation file keeps its level; the break separates documents
        html = markdown.markdown(txt, extensions=["tables", "fenced_code", "sane_lists"])
        cls = ' class="docbreak"' if i else ""
        parts.append(f"<div{cls}>{html}</div>")

    title = a.title or a.files[0]
    doc = (f"<html><head><meta charset='utf-8'><title>{title}</title></head>"
           f"<body>{''.join(parts)}</body></html>")
    HTML(string=doc).write_pdf(a.out, stylesheets=[CSS(string=CSS_TEXT)])
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
