"""Generate deterministic synthetic invoices and their exact ground truth.

The generator deliberately creates documents that exercise the later OCR and
validation stages: multiple layouts, several currencies, optional discounts
and taxes, long line items, European number formatting, and previous balances
that must not be included in the invoice total.

Usage:
    python scripts/generate_invoices.py --count 10
    python scripts/generate_invoices.py --count 500 --seed 42

ReportLab is used instead of WeasyPrint so generation works on Windows without
installing GTK or another system-level rendering dependency. Jinja2 HTML is
still rendered and saved beside each PDF for visual inspection and future
renderer swaps.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from faker import Faker
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

try:
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover - exercised only in minimal installations
    pdfium = None


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "templates" / "invoices"
DATA_DIR = REPO_ROOT / "data"
DEFAULT_OUTPUT_DIR = DATA_DIR / "synthetic"
DEFAULT_GT_PATH = DATA_DIR / "ground_truth" / "synthetic.jsonl"
DEFAULT_MANIFEST_PATH = DEFAULT_OUTPUT_DIR / "manifest.jsonl"

TEMPLATE_NAMES = (
    "classic_table.html",
    "modern_minimal.html",
    "two_column.html",
    "thermal_compact.html",
)

MONEY_QUANTUM = Decimal("0.01")
TAX_RATES = (Decimal("5"), Decimal("7.5"), Decimal("10"), Decimal("15"), Decimal("20"))

CURRENCIES: tuple[dict[str, str], ...] = (
    {"code": "USD", "symbol": "$", "word": "dollars"},
    {"code": "EUR", "symbol": "EUR", "word": "euros"},
    {"code": "GBP", "symbol": "GBP", "word": "pounds"},
    {"code": "PKR", "symbol": "Rs", "word": "rupees"},
    {"code": "AED", "symbol": "AED", "word": "dirhams"},
)

log = logging.getLogger(__name__)


def quantize_money(value: Decimal) -> Decimal:
    """Round an amount once, using ordinary accounting half-up rounding."""

    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def canonical_amount(value: Decimal | str | int | float | None) -> str | None:
    """Return the canonical amount representation used by DocFlow ground truth."""

    if value is None:
        return None
    return format(quantize_money(Decimal(str(value))), "f")


def format_amount(value: Decimal, number_format: str = "western") -> str:
    """Format an amount as it might appear on a printed invoice."""

    amount = quantize_money(value)
    rendered = f"{amount:,.2f}"
    if number_format == "european":
        rendered = rendered.replace(",", "X").replace(".", ",").replace("X", ".")
    return rendered


def _integer_to_words(value: int) -> str:
    ones = (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
    )
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

    if value < 20:
        return ones[value]
    if value < 100:
        return tens[value // 10] + (f"-{ones[value % 10]}" if value % 10 else "")
    if value < 1_000:
        remainder = value % 100
        return f"{ones[value // 100]} hundred" + (
            f" {_integer_to_words(remainder)}" if remainder else ""
        )
    if value < 1_000_000:
        remainder = value % 1_000
        return f"{_integer_to_words(value // 1_000)} thousand" + (
            f" {_integer_to_words(remainder)}" if remainder else ""
        )
    if value < 1_000_000_000:
        remainder = value % 1_000_000
        return f"{_integer_to_words(value // 1_000_000)} million" + (
            f" {_integer_to_words(remainder)}" if remainder else ""
        )
    return str(value)


def amount_in_words(value: Decimal, currency_word: str) -> str:
    """Create a compact, dependency-free printed total-in-words value."""

    amount = quantize_money(value)
    whole = int(amount)
    cents = int((amount - whole) * 100)
    result = f"{_integer_to_words(whole)} {currency_word}"
    return f"{result} and {cents:02d}/100" if cents else result


def _relative_path(path: Path) -> str:
    """Return a portable path for JSON manifests when possible."""

    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _paragraph_text(value: str) -> str:
    """Escape text for ReportLab's small XML-like paragraph language."""

    return escape(str(value)).replace("\n", "<br/>")


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")


def _date_for(rng: random.Random) -> date:
    return date(2024, 1, 1) + timedelta(days=rng.randrange(730))


def _make_description(
    fake: Faker,
    rng: random.Random,
    hard_case: bool,
    index: int,
    force_long: bool = False,
) -> str:
    if force_long:
        return (
            f"{fake.bs().capitalize()} implementation and integration support; "
            f"{fake.catch_phrase()}; includes documentation, configuration review, "
            "stakeholder workshops, migration assistance, testing, and handover"
        )
    if hard_case and index % 3 == 0:
        return (
            f"{fake.bs().capitalize()} implementation and integration support; "
            "includes documentation, configuration review, and handover"
        )
    return fake.bs().capitalize()


def build_invoice(
    index: int, rng: random.Random, fake: Faker, hard_case_rate: float = 0.30
) -> dict[str, Any]:
    """Build one JSON-serializable invoice and its source ground truth."""

    currency = (
        CURRENCIES[index % len(CURRENCIES)] if index < len(CURRENCIES) else rng.choice(CURRENCIES)
    )
    hard_case = rng.random() < hard_case_rate
    template = (
        TEMPLATE_NAMES[index % len(TEMPLATE_NAMES)]
        if index < len(TEMPLATE_NAMES)
        else rng.choice(TEMPLATE_NAMES)
    )
    invoice_date = _date_for(rng)
    due_date = invoice_date + timedelta(days=rng.choice((14, 21, 30, 45)))
    number_format = "european" if hard_case and rng.random() < 0.65 else "western"
    page_overflow = hard_case and index % 3 == 0

    item_count = (
        15
        if page_overflow
        else (rng.randint(10, 15) if hard_case and rng.random() < 0.55 else rng.randint(1, 8))
    )
    line_items: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    for item_index in range(item_count):
        quantity = Decimal(rng.randint(1, 8))
        unit_price = Decimal(rng.randint(12, 450)) + (Decimal(rng.randint(0, 99)) / 100)
        unit_price = quantize_money(unit_price)
        line_total = quantize_money(quantity * unit_price)
        subtotal += line_total
        line_items.append(
            {
                "description": _make_description(fake, rng, hard_case, item_index, page_overflow),
                "quantity": str(int(quantity)),
                "unit_price": canonical_amount(unit_price),
                "total": canonical_amount(line_total),
                "unit_price_fmt": format_amount(unit_price, number_format),
                "total_fmt": format_amount(line_total, number_format),
                "note": "Detailed scope included" if hard_case and item_index % 4 == 0 else None,
            }
        )
    subtotal = quantize_money(subtotal)

    discount_type: str | None = None
    discount_rate: Decimal | None = None
    discount = Decimal("0")
    if rng.random() < 0.55:
        discount_type = rng.choice(("percentage", "fixed"))
        if discount_type == "percentage":
            discount_rate = rng.choice(
                (Decimal("5"), Decimal("10"), Decimal("12.5"), Decimal("15"))
            )
            discount = quantize_money(subtotal * discount_rate / 100)
        else:
            discount = quantize_money(min(subtotal * Decimal("0.10"), Decimal(rng.randint(5, 75))))

    taxable_base = max(Decimal("0"), subtotal - discount)
    tax_lines: list[dict[str, str]] = []
    for tax_index in range(2 if hard_case and rng.random() < 0.25 else 1):
        rate = rng.choice(TAX_RATES)
        tax_amount = quantize_money(taxable_base * rate / 100)
        tax_lines.append(
            {
                "label": "VAT" if tax_index == 0 else "Local tax",
                "rate": str(rate),
                "amount": canonical_amount(tax_amount),
                "amount_fmt": format_amount(tax_amount, number_format),
            }
        )
    tax_total = quantize_money(sum((Decimal(line["amount"]) for line in tax_lines), Decimal("0")))

    service_charge = Decimal("0")
    if rng.random() < 0.35:
        service_charge = quantize_money(
            taxable_base * Decimal(rng.choice(("0.03", "0.05", "0.08")))
        )

    total = quantize_money(taxable_base + tax_total + service_charge)

    previous_balance = None
    if hard_case and rng.random() < 0.65:
        previous_balance = quantize_money(Decimal(rng.randint(50, 900)) + Decimal("0.25"))

    date_format = rng.choice(("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y"))
    date_display = invoice_date.strftime(date_format)
    currency_display = currency["symbol"] if rng.random() < 0.5 else currency["code"]
    total_words = (
        amount_in_words(total, currency["word"]) if hard_case and rng.random() < 0.75 else None
    )

    vendor_address = fake.address().replace("\n", ", ")
    ground_truth = {
        "vendor_name": fake.company(),
        "vendor_address": vendor_address,
        "invoice_number": f"INV-{invoice_date.year}-{rng.randint(10000, 99999)}",
        "date": invoice_date.isoformat(),
        "currency": currency["code"],
        "line_items": [
            {
                "description": item["description"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "total": item["total"],
            }
            for item in line_items
        ],
        "subtotal": canonical_amount(subtotal),
        "tax": canonical_amount(tax_total),
        "service_charge": canonical_amount(service_charge),
        "discount": canonical_amount(discount),
        "rounding": "0.00",
        "total": canonical_amount(total),
    }

    return {
        "doc_id": f"synthetic_{index:04d}",
        "source": "synthetic",
        "file": None,
        "doc_type": "invoice",
        "labeled_fields": [
            "vendor_name",
            "vendor_address",
            "invoice_number",
            "date",
            "currency",
            "line_items",
            "subtotal",
            "tax",
            "service_charge",
            "discount",
            "rounding",
            "total",
        ],
        "ground_truth": ground_truth,
        "_render_items": line_items,
        "_tax_lines": tax_lines,
        "pdf_file": None,
        "image_file": None,
        "render_metadata": {
            "template": template,
            "hard_case": hard_case,
            "page_overflow": page_overflow,
            "number_format": number_format,
            "date_display": date_display,
            "due_date_display": due_date.strftime("%Y-%m-%d"),
            "currency_display": currency_display,
            "discount_type": discount_type,
            "discount_rate": str(discount_rate) if discount_rate is not None else None,
            "previous_balance": canonical_amount(previous_balance),
            "total_in_words": total_words,
        },
        "degradations": [],
    }


def _render_context(record: dict[str, Any]) -> dict[str, Any]:
    ground_truth = record["ground_truth"]
    metadata = record["render_metadata"]
    currency_code = ground_truth["currency"]
    number_format = metadata["number_format"]
    tax_lines = record["_tax_lines"]
    discount = Decimal(ground_truth["discount"] or "0")
    service_charge = Decimal(ground_truth["service_charge"] or "0")

    return {
        "vendor_name": ground_truth["vendor_name"],
        "vendor_address": ground_truth["vendor_address"],
        "vendor_email": record["vendor_email"],
        "client_name": record["client_name"],
        "client_address": record["client_address"],
        "invoice_number": ground_truth["invoice_number"],
        "date": record["date_display"],
        "due_date": record["due_date_display"],
        "currency_code": currency_code,
        "currency_symbol": metadata["currency_display"],
        "line_items": record["_render_items"],
        "subtotal_fmt": format_amount(Decimal(ground_truth["subtotal"]), number_format),
        "discount": discount if discount else None,
        "discount_fmt": format_amount(discount, number_format) if discount else None,
        "discount_pct": metadata["discount_rate"],
        "tax": tax_lines[0] if tax_lines else None,
        "tax_fmt": tax_lines[0]["amount_fmt"] if tax_lines else None,
        "tax_rate": tax_lines[0]["rate"] if tax_lines else None,
        "tax2": tax_lines[1] if len(tax_lines) > 1 else None,
        "tax2_fmt": tax_lines[1]["amount_fmt"] if len(tax_lines) > 1 else None,
        "tax2_label": tax_lines[1]["label"] if len(tax_lines) > 1 else None,
        "tax2_rate": tax_lines[1]["rate"] if len(tax_lines) > 1 else None,
        "service_charge": service_charge if service_charge else None,
        "service_charge_fmt": format_amount(service_charge, number_format)
        if service_charge
        else None,
        "shipping_label": "Shipping" if service_charge else "Service Charge",
        "total_fmt": format_amount(Decimal(ground_truth["total"]), number_format),
        "total_in_words": metadata["total_in_words"],
        "previous_balance": metadata["previous_balance"],
        "previous_balance_fmt": (
            format_amount(Decimal(metadata["previous_balance"]), number_format)
            if metadata["previous_balance"]
            else None
        ),
        "notes": record["notes"],
    }


def render_html(record: dict[str, Any], template_dir: Path = TEMPLATE_DIR) -> str:
    """Render the selected Jinja2 invoice template to HTML."""

    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template(record["render_metadata"]["template"])
    return template.render(**_render_context(record))


def _pdf_styles(template_name: str) -> tuple[colors.Color, colors.Color]:
    palettes = {
        "classic_table.html": (colors.HexColor("#1A3A5C"), colors.HexColor("#F1F5F9")),
        "modern_minimal.html": (colors.HexColor("#222222"), colors.HexColor("#F7F7F7")),
        "two_column.html": (colors.HexColor("#2C2C2C"), colors.HexColor("#F0B429")),
        "thermal_compact.html": (colors.HexColor("#111111"), colors.HexColor("#E8E8E8")),
    }
    accent, light = palettes[template_name]
    return accent, light


def render_pdf(record: dict[str, Any], output_path: Path) -> None:
    """Render one invoice with ReportLab, allowing long tables to span pages."""

    template_name = record["render_metadata"]["template"]
    context = _render_context(record)
    accent, light = _pdf_styles(template_name)
    thermal = template_name == "thermal_compact.html"
    page_width = 80 * mm if thermal else A4[0]
    page_size = (page_width, 220 * mm) if thermal else A4
    margin = 8 * mm if thermal else 16 * mm

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=page_size,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=f"Invoice {context['invoice_number']}",
        author="DocFlow synthetic invoice generator",
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "InvoiceNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8 if thermal else 9,
        leading=10 if thermal else 11,
        spaceAfter=2,
    )
    small = ParagraphStyle(
        "InvoiceSmall",
        parent=normal,
        fontSize=7 if thermal else 8,
        textColor=colors.HexColor("#555555"),
    )
    title = ParagraphStyle(
        "InvoiceTitle",
        parent=normal,
        fontSize=15 if thermal else 20,
        leading=18,
        textColor=colors.white if template_name == "two_column.html" else accent,
        alignment=TA_RIGHT if not thermal else TA_CENTER,
        spaceAfter=4,
    )
    heading = ParagraphStyle(
        "InvoiceHeading",
        parent=normal,
        fontSize=13 if thermal else 16,
        leading=15,
        textColor=accent,
        alignment=TA_CENTER if thermal else TA_LEFT,
    )
    right = ParagraphStyle("InvoiceRight", parent=normal, alignment=TA_RIGHT)
    center = ParagraphStyle("InvoiceCenter", parent=normal, alignment=TA_CENTER)

    story: list[Any] = []
    if thermal:
        story.extend(
            [
                Paragraph(f"<b>{_paragraph_text(context['vendor_name'])}</b>", heading),
                Paragraph(_paragraph_text(context["vendor_address"]), center),
                Paragraph(f"{context['date']} | #{context['invoice_number']}", small),
                Spacer(1, 5),
            ]
        )
    else:
        header = Table(
            [
                [
                    Paragraph(
                        f"<b>{_paragraph_text(context['vendor_name'])}</b><br/>{_paragraph_text(context['vendor_address'])}<br/>{_paragraph_text(context['vendor_email'])}",
                        normal,
                    ),
                    Paragraph(
                        f"<b>INVOICE</b><br/><font size=8>#{_paragraph_text(context['invoice_number'])}<br/>{context['date']}<br/>Due {context['due_date']}</font>",
                        title,
                    ),
                ]
            ],
            colWidths=[page_width - 2 * margin - 75 * mm, 75 * mm],
        )
        header.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "BACKGROUND",
                        (1, 0),
                        (1, 0),
                        accent if template_name == "two_column.html" else colors.white,
                    ),
                    ("BOX", (1, 0), (1, 0), 0.5, accent),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.extend([header, Spacer(1, 12)])
        story.append(
            Paragraph(
                f"<b>Bill To</b><br/>{_paragraph_text(context['client_name'])}<br/>{_paragraph_text(context['client_address'])}",
                normal,
            )
        )
        story.append(Spacer(1, 10))

    if thermal:
        item_rows: list[list[Any]] = [
            [
                Paragraph("<b>Item</b>", small),
                Paragraph("<b>Qty</b>", small),
                Paragraph("<b>Amount</b>", small),
            ]
        ]
        for item in context["line_items"]:
            item_rows.append(
                [
                    Paragraph(_paragraph_text(item["description"]), normal),
                    Paragraph(f"{item['quantity']}x", right),
                    Paragraph(item["total_fmt"], right),
                ]
            )
        if context["previous_balance"]:
            item_rows.append(
                [
                    Paragraph("Previous balance (not included in total)", small),
                    "",
                    Paragraph(context["previous_balance_fmt"], right),
                ]
            )
        available_width = page_width - 2 * margin
        item_widths = [available_width - 10 * mm - 28 * mm, 10 * mm, 28 * mm]
    else:
        item_rows = [
            [
                Paragraph("<b>Description</b>", small),
                Paragraph("<b>Qty</b>", small),
                Paragraph("<b>Unit Price</b>", small),
                Paragraph("<b>Total</b>", small),
            ]
        ]
        for item in context["line_items"]:
            item_rows.append(
                [
                    Paragraph(_paragraph_text(item["description"]), normal),
                    Paragraph(item["quantity"], right),
                    Paragraph(item["unit_price_fmt"], right),
                    Paragraph(item["total_fmt"], right),
                ]
            )
        if context["previous_balance"]:
            item_rows.append(
                [
                    Paragraph("Previous balance (not included in total)", small),
                    "",
                    "",
                    Paragraph(context["previous_balance_fmt"], right),
                ]
            )
        item_widths = [
            page_width - 2 * margin - 24 * mm - 28 * mm - 28 * mm,
            12 * mm,
            28 * mm,
            28 * mm,
        ]
    item_table = Table(item_rows, colWidths=item_widths, repeatRows=1, splitByRow=1)
    item_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), accent if not thermal else light),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if not thermal else colors.black),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5D5D5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -2 if context["previous_balance"] else -1),
                    [colors.white, light],
                ),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#777777")),
            ]
        )
    )
    story.extend([item_table, Spacer(1, 10)])

    summary_rows = [[Paragraph("Subtotal", normal), Paragraph(context["subtotal_fmt"], right)]]
    if context["discount"]:
        label = "Discount"
        if context["discount_pct"]:
            label += f" ({context['discount_pct']}%)"
        summary_rows.append(
            [Paragraph(label, normal), Paragraph(f"-{context['discount_fmt']}", right)]
        )
    for tax_line in (context["tax"], context["tax2"]):
        if tax_line:
            summary_rows.append(
                [
                    Paragraph(f"{tax_line['label']} ({tax_line['rate']}%)", normal),
                    Paragraph(tax_line["amount_fmt"], right),
                ]
            )
    if context["service_charge"]:
        summary_rows.append(
            [
                Paragraph(context["shipping_label"], normal),
                Paragraph(context["service_charge_fmt"], right),
            ]
        )
    summary_rows.append(
        [Paragraph("<b>TOTAL</b>", normal), Paragraph(f"<b>{context['total_fmt']}</b>", right)]
    )
    summary = Table(
        summary_rows, colWidths=[page_width - 2 * margin - 45 * mm, 45 * mm], hAlign="RIGHT"
    )
    summary.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 1.2, accent),
                (
                    "BACKGROUND",
                    (0, -1),
                    (-1, -1),
                    light if template_name != "two_column.html" else accent,
                ),
                (
                    "TEXTCOLOR",
                    (0, -1),
                    (-1, -1),
                    colors.white if template_name == "two_column.html" else colors.black,
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(summary)
    if context["total_in_words"]:
        story.extend(
            [
                Spacer(1, 8),
                Paragraph(f"Amount in words: {_paragraph_text(context['total_in_words'])}", small),
            ]
        )
    if context["notes"]:
        story.extend([Spacer(1, 10), Paragraph(_paragraph_text(context["notes"]), small)])
    document.build(story)


def rasterize_pdf(pdf_path: Path, image_path: Path, dpi: int = 150) -> int:
    """Rasterize all PDF pages into one vertically stacked PNG.

    Keeping every page in the image artifact prevents a multi-page hard case
    from silently losing line items when an image manifest is used later.
    Returns the number of rendered pages.
    """

    if pdfium is None:
        raise RuntimeError("pypdfium2 is required to rasterize generated PDFs")
    document = pdfium.PdfDocument(str(pdf_path))
    page_images: list[Image.Image] = []
    for page_index in range(len(document)):
        page = document[page_index]
        bitmap = page.render(scale=dpi / 72)
        page_images.append(bitmap.to_pil().convert("RGB"))
        page.close()
    width = max(image.width for image in page_images)
    height = sum(image.height for image in page_images)
    combined = Image.new("RGB", (width, height), "white")
    offset = 0
    for page_image in page_images:
        combined.paste(page_image, (0, offset))
        offset += page_image.height
    image_path.parent.mkdir(parents=True, exist_ok=True)
    combined.save(image_path, format="PNG")
    document.close()
    return len(page_images)


def generate_invoices(
    count: int,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    ground_truth_path: Path = DEFAULT_GT_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    seed: int = 42,
    hard_case_rate: float = 0.30,
    rasterize: bool = True,
) -> list[dict[str, Any]]:
    """Generate invoices, rendered artifacts, and JSONL manifests."""

    if count < 1:
        raise ValueError("count must be at least 1")
    if not 0 <= hard_case_rate <= 1:
        raise ValueError("hard_case_rate must be between 0 and 1")

    output_dir = Path(output_dir)
    template_dir = TEMPLATE_DIR
    html_dir = output_dir / "html"
    pdf_dir = output_dir / "pdf"
    image_dir = output_dir / "images"
    for directory in (html_dir, pdf_dir, image_dir):
        directory.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)
    records: list[dict[str, Any]] = []

    for index in range(count):
        record = build_invoice(index, rng, fake, hard_case_rate)
        record["vendor_email"] = fake.company_email()
        record["client_name"] = fake.company()
        record["client_address"] = fake.address().replace("\n", ", ")
        record["date_display"] = record["render_metadata"]["date_display"]
        record["due_date_display"] = record["render_metadata"]["due_date_display"]
        record["notes"] = "Payment due by the date shown above. Thank you for your business."

        doc_id = record["doc_id"]
        html_path = html_dir / f"{doc_id}.html"
        pdf_path = pdf_dir / f"{doc_id}.pdf"
        image_path = image_dir / f"{doc_id}.png"
        html_path.write_text(render_html(record, template_dir), encoding="utf-8")
        render_pdf(record, pdf_path)
        if rasterize:
            record["render_metadata"]["page_count"] = rasterize_pdf(pdf_path, image_path)
            record["image_file"] = _relative_path(image_path)
            record["file"] = record["image_file"]
        record["pdf_file"] = _relative_path(pdf_path)
        record["html_file"] = _relative_path(html_path)
        if not rasterize:
            record["file"] = record["pdf_file"]
        del record["_render_items"]
        del record["_tax_lines"]
        records.append(record)

    _write_jsonl(ground_truth_path, records)
    _write_jsonl(manifest_path, records)
    log.info("Generated %d synthetic invoices in %s", len(records), output_dir)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count", type=int, default=10, help="Number of invoices to generate (default: 10)"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument(
        "--hard-case-rate", type=float, default=0.30, help="Fraction of hard cases (default: 0.30)"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GT_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--no-rasterize", action="store_true", help="Only create HTML and PDF files"
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    generate_invoices(
        count=args.count,
        output_dir=args.output_dir,
        ground_truth_path=args.ground_truth,
        manifest_path=args.manifest,
        seed=args.seed,
        hard_case_rate=args.hard_case_rate,
        rasterize=not args.no_rasterize,
    )


if __name__ == "__main__":
    main()
