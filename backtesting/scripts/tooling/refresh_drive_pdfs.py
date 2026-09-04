#!/usr/bin/env python3
"""Rebuild the Drive PDFs whose source markdown has changed since they were rendered.

The Drive copy is a convenience for reading; the markdown in the repository is the record. That
only holds if the two agree, and on 2026-09-04 all eleven matched PDFs were older than their
source, some by five weeks. A reader was being handed a paper whose conclusions had since been
withdrawn.

Filenames are left alone and the file is overwritten in place, so a link into the folder keeps
working and the date in the name stays the date the document was written.

  python3 refresh_drive_pdfs.py            rebuild what is stale
  python3 refresh_drive_pdfs.py --check    report without writing
  python3 refresh_drive_pdfs.py --all      rebuild everything
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MD2PDF = os.path.join(HERE, "md2pdf.py")
DRIVE = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-street.tj@gmail.com/My Drive/Boost-v2-Analysis")
R = os.path.expanduser("~/StudioProjects/Boost-AAPS-core/backtesting/reports")
ML = os.path.expanduser("~/StudioProjects/boost-ml-library/docs")
MI = os.path.expanduser("~/meal-investigations")
TS = os.path.expanduser("~/StudioProjects/TimSim/docs")
BT = os.path.expanduser("~/StudioProjects/Boost-AAPS-core/backtesting")

# One entry per Drive PDF: its sources, in order, and the title on the first page.
MAP = [
    ("Boost_exercise_premeal_research_2026-09-04.pdf",
     [f"{R}/2026-09_exercise_premeal_research.md"], "Pre-meal exercise mode"),
    ("Boost_LGBM_methods_2026-09-02.pdf",
     [f"{R}/2026-09_boost_lgbm_methods.md"], "Gradient-boosted trees on the Boost dose path"),
    ("Boost_ML_paper_2026-09-03.pdf",
     [f"{ML}/BOOST_ML_PAPER.md", f"{ML}/REPRODUCIBILITY.md", f"{ML}/CALIBRATION.md"],
     "Machine learning on the Boost dose path"),
    ("Boost_meal_signal_timing_preprint_2026-09-01.pdf",
     [f"{R}/2026-08_meal_signal_timing_preprint.md"], "Meal information in continuous glucose traces"),
    ("Boost_meal_investigations_findings_2026-09-02.pdf",
     [f"{MI}/FINDINGS.md"], "How carbohydrate is announced"),
    ("Boost_onemin_cadence_preprint_2026-07-30.pdf",
     [f"{R}/2026-07_onemin_cadence_preprint.md"], "One-minute continuous glucose data"),
    ("Padova_vs_realworld_article_2026-07-29.pdf",
     [f"{R}/2026-07_padova_vs_realworld_article.md"], "The simulator against the real world"),
    ("CGM_cadence_report_2026-07-30.pdf",
     [f"{R}/2026-07_cgm_cadence_report.md"], "CGM cadence"),
    ("Boost_Statistical_Methods_2026-07-09.pdf",
     [f"{BT}/STATISTICAL_METHODS.md"], "Statistical methods"),
    ("TimSim_second_machine_requirements_2026-09-04.pdf",
     [f"{TS}/PC_REQUIREMENTS.md"], "Requirements for a second machine running part of a sweep"),
]


def main():
    check = "--check" in sys.argv
    force = "--all" in sys.argv
    rebuilt = skipped = missing = 0
    for pdf, srcs, title in MAP:
        out = os.path.join(DRIVE, pdf)
        present = [s for s in srcs if os.path.exists(s)]
        if not present:
            print(f"  source missing   {pdf}")
            missing += 1
            continue
        newest = max(os.path.getmtime(s) for s in present)
        have = os.path.getmtime(out) if os.path.exists(out) else 0
        if not force and have >= newest:
            skipped += 1
            continue
        age = (newest - have) / 86400 if have else None
        note = f"source newer by {age:.1f} d" if age else "not on Drive"
        if check:
            print(f"  STALE  {pdf:<52} {note}")
            rebuilt += 1
            continue
        r = subprocess.run([sys.executable, MD2PDF, "--out", out, "--title", title] + present,
                           capture_output=True, text=True)
        if r.returncode:
            print(f"  FAILED {pdf}: {r.stderr.strip()[:120]}")
        else:
            print(f"  rebuilt {pdf:<52} {note}")
            rebuilt += 1
    verb = "would rebuild" if check else "rebuilt"
    print(f"\n{verb} {rebuilt}, up to date {skipped}, source missing {missing}")


if __name__ == "__main__":
    main()
