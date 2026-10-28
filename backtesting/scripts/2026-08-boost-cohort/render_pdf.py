#!/usr/bin/env python3
"""Render a Markdown document to PDF locally.

Entirely local: markdown to HTML to weasyprint. No network and no service, so the same input gives
the same output on any machine with the dependencies installed.

Usage:
  python3 render_pdf.py INPUT.md OUTPUT.pdf ["Optional subtitle"]
"""
from __future__ import annotations

import sys

import markdown
from weasyprint import HTML

CSS = """
@page { size: A4; margin: 20mm 18mm;
        @bottom-center { content: counter(page) " of " counter(pages);
                         font: 8pt Georgia; color: #666; } }
body { font: 10pt/1.45 Georgia, "Times New Roman", serif; color: #111; text-align: justify;
       hyphens: auto; }
h1 { font-size: 16pt; line-height: 1.25; margin: 0 0 3mm 0; text-align: left; }
h2 { font-size: 11.5pt; margin: 7mm 0 2mm 0; text-align: left; break-after: avoid; }
h3 { font-size: 10.5pt; margin: 5mm 0 1.5mm 0; text-align: left; font-style: italic;
     break-after: avoid; }
p { margin: 0 0 2.5mm 0; }
table { border-collapse: collapse; width: 100%; margin: 3mm 0 4mm 0; font-size: 8.5pt;
        break-inside: avoid; }
th { text-align: left; padding: 1.3mm 1.8mm; border-top: 0.9pt solid #000;
     border-bottom: 0.5pt solid #000; }
td { padding: 1.1mm 1.8mm; }
tbody tr:last-child td { border-bottom: 0.9pt solid #000; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt; }
.sub { color: #555; font-size: 9pt; margin: 0 0 6mm 0; }
"""


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src, dst = sys.argv[1], sys.argv[2]
    sub = sys.argv[3] if len(sys.argv) > 3 else ""
    body = markdown.markdown(open(src).read(), extensions=["tables"])
    if sub:
        body = body.replace("</h1>", f"</h1><div class='sub'>{sub}</div>", 1)
    HTML(string=f"<style>{CSS}</style>{body}").write_pdf(dst)
    print(f"wrote {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
