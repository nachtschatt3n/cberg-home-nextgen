#!/usr/bin/env python3
"""Generate PATCHT document-separator sheets for paperless-ngx.

Paperless splits a scanned batch at every page whose barcode decodes to the
value of PAPERLESS_CONSUMER_BARCODE_STRING (default "PATCHT") and discards that
page. Insert one of these sheets between documents in the ES-580W ADF.

The ES-580W scans duplex, so each sheet carries the barcode on BOTH sides
(emitted as two identical pages). Print the PDF DOUBLE-SIDED at 100% / "actual
size" (no fit-to-page scaling, which can shrink the barcode below detection).

Usage:
    python3 scripts/gen-patcht-separator.py [--copies N] [--out PATH] [--code STR]

Requires: reportlab  (pip install reportlab)
"""
import argparse

from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def draw_sheet(c, code):
    width, height = A4
    barcode = code128.Code128(code, barHeight=28 * mm, barWidth=1.1 * mm)
    bx = (width - barcode.width) / 2
    barcode.drawOn(c, bx, height / 2)

    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height / 2 - 18 * mm, code)
    c.setFont("Helvetica", 12)
    c.drawCentredString(
        width / 2,
        height / 2 - 28 * mm,
        "paperless document separator - this page is removed on import",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copies", type=int, default=10, help="number of sheets")
    ap.add_argument("--code", default="PATCHT", help="separator barcode value")
    ap.add_argument("--out", default="scratch/patcht-separator.pdf")
    args = ap.parse_args()

    import os

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    c = canvas.Canvas(args.out, pagesize=A4)
    for _ in range(args.copies):
        # Two identical pages per physical sheet => barcode on front AND back
        # when printed double-sided (duplex-safe, no blank leading page).
        draw_sheet(c, args.code)
        c.showPage()
        draw_sheet(c, args.code)
        c.showPage()
    c.save()
    print(
        "wrote {} ({} sheets, '{}') - print DOUBLE-SIDED at 100% scale".format(
            args.out, args.copies, args.code
        )
    )


if __name__ == "__main__":
    main()
