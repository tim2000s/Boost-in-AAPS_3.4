# Tooling

Small utilities shared across the analyses, kept here rather than in a session scratchpad so that a
report can be regenerated months later by whoever needs it.

`md2pdf.py` renders one or more markdown files to a single styled PDF, which is the form the
reports take when they go to Drive. Several files given at once are concatenated with a page break
between them, which is how a set of reports that must be read together is published as one
document.

    python3 md2pdf.py --out Boost_topic_YYYY-MM-DD.pdf --title "Document title" a.md b.md

It needs `markdown` and `weasyprint`. Regenerate the Drive copy whenever the source markdown
changes, and verify the output before copying it out: check the PDF opens, that the page count is
sensible and that tables have rendered as tables rather than collapsing into runs of text.
