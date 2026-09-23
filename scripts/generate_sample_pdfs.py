#!/usr/bin/env python3
"""Generate synthetic test PDFs for ingestion testing.

Creates:
  - sample-data/simple.pdf: one page with minimal text
  - sample-data/multi-page.pdf: three pages with content
  - sample-data/large.pdf: one page with enough text to span multiple chunks
"""

import sys
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def create_pdf_with_text(pages_text: list[str]) -> bytes:
    """Create a PDF from a list of page texts."""
    writer = PdfWriter()

    for page_text in pages_text:
        # Create a page using reportlab
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)

        # Wrap text across multiple lines
        y_position = 750
        line_height = 14
        margin = 50
        max_width = letter[0] - 2 * margin

        # Simple text wrapping
        words = page_text.split()
        current_line = ""

        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if len(test_line) > 80:  # Rough line length
                if current_line:
                    c.drawString(margin, y_position, current_line)
                    y_position -= line_height
                    if y_position < margin:
                        break
                current_line = word
            else:
                current_line = test_line

        if current_line and y_position > margin:
            c.drawString(margin, y_position, current_line)

        c.showPage()
        c.save()

        buffer.seek(0)
        reader = PdfReader(buffer)
        for page in reader.pages:
            writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output.getvalue()


def main():
    sample_dir = Path(__file__).parent.parent / "sample-data"
    sample_dir.mkdir(exist_ok=True)

    # Simple PDF
    simple_pdf = create_pdf_with_text([
        "This is a simple one-page PDF for testing. It contains minimal text."
    ])
    (sample_dir / "simple.pdf").write_bytes(simple_pdf)
    print(f"[OK] Created {sample_dir / 'simple.pdf'}")

    # Multi-page PDF
    multi_pdf = create_pdf_with_text([
        "Page 1: Introduction to Course Syllabus. This course covers the fundamentals of computer science and software engineering. Students will learn about data structures, algorithms, and system design.",
        "Page 2: Course Schedule. The course runs from September to December. Lectures are held on Mondays, Wednesdays, and Fridays at 10:00 AM. Lab sessions are on Tuesdays and Thursdays at 2:00 PM.",
        "Page 3: Assessment and Grading. Grading is based on participation (10%), assignments (40%), midterm exam (20%), and final project (30%). The final grade is calculated on a scale of A to F."
    ])
    (sample_dir / "multi-page.pdf").write_bytes(multi_pdf)
    print(f"[OK] Created {sample_dir / 'multi-page.pdf'}")

    # Large PDF with enough text to create multiple chunks
    large_text = " ".join([
        "Computer science is the study of computation and information.",
        "It involves theoretical foundations and practical applications.",
        "Algorithms are step-by-step procedures for solving problems.",
        "Data structures organize information for efficient access and modification.",
        "Software engineering applies engineering principles to software development.",
    ] * 50)  # Repeat to create ~2000+ tokens

    large_pdf = create_pdf_with_text([large_text])
    (sample_dir / "large.pdf").write_bytes(large_pdf)
    print(f"[OK] Created {sample_dir / 'large.pdf'}")

    print(f"\nAll sample PDFs created in {sample_dir}")


if __name__ == "__main__":
    main()
