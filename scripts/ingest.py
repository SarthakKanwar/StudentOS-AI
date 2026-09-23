#!/usr/bin/env python3
"""CLI ingestion.

Local only (no cloud resources needed):
    python scripts/ingest.py sample-data/multi-page.pdf "Course Syllabus"

End to end, with Foundry embeddings and Supabase persistence:
    python scripts/ingest.py sample-data/multi-page.pdf "Course Syllabus" --persist

--persist requires:
  * an Entra login that can reach the Foundry endpoint (`az login`, or a
    managed identity with the Cognitive Services User role)
  * a provisioned Supabase project with migrations/0001_initial_schema.sql
    applied, and SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY set in .env
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ingestion.pipeline import ingest_and_store, ingest_pdf_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a PDF into StudentOS.")
    parser.add_argument("pdf_path", type=Path, help="path to the PDF")
    parser.add_argument("title", nargs="?", help="human-readable document title")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="embed via Foundry and store in Supabase (needs credentials)",
    )
    parser.add_argument("--json", action="store_true", help="print JSON only")
    args = parser.parse_args()

    if not args.pdf_path.is_file():
        print(f"[ERROR] File not found: {args.pdf_path}", file=sys.stderr)
        return 1

    title = args.title or args.pdf_path.stem

    if not args.json:
        print(f"Ingesting : {args.pdf_path}")
        print(f"Title     : {title}")
        print(f"Mode      : {'embed + persist' if args.persist else 'local only'}")
        print()

    if args.persist:
        from backend.services.persistence import SupabaseNotConfigured, is_supabase_configured

        if not is_supabase_configured():
            print(
                "[BLOCKED] Supabase is not provisioned.\n"
                "\n"
                "  SUPABASE_URL is unset or still a placeholder, so there is nowhere\n"
                "  to store chunks. To enable --persist:\n"
                "    1. Create a Supabase project.\n"
                "    2. Run migrations/0001_initial_schema.sql in the SQL editor.\n"
                "    3. Put SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.\n"
                "\n"
                "  Local ingestion works now - re-run without --persist.",
                file=sys.stderr,
            )
            return 2

        try:
            doc = ingest_and_store(args.pdf_path, title)
        except SupabaseNotConfigured as exc:
            print(f"[BLOCKED] {exc}", file=sys.stderr)
            return 2
    else:
        doc = ingest_pdf_file(args.pdf_path, title)

    if doc.status == "failed":
        print(f"[FAILED] {doc.error_message}", file=sys.stderr)
        if args.json:
            print(json.dumps(doc.to_dict(), indent=2))
        return 1

    if not args.json:
        print(f"[OK] status={doc.status}")
        print(f"  Pages     : {doc.page_count}")
        print(f"  Chunks    : {len(doc.chunks)}")
        print(f"  File hash : {doc.file_hash[:16]}...")
        if doc.id:
            print(f"  Stored as : {doc.id}")
        print()

    print(json.dumps(doc.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
