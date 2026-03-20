import argparse
import sys
import zipfile
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

# Ensure we can import the repo packages when run as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# pypdf is installed into .pydeps so we can run in this environment.
sys.path.insert(0, str(REPO_ROOT / ".pydeps"))
from pypdf import PdfReader  # type: ignore

from nde_app.checklist_xml import extract_checklist_items_for_class
from nde_app.docx_fill_checklist import (
    _cell_text,
    _find_checklist_table_and_columns,
    _local_name,
)
from nde_app.docx_fill_checklist import fill_checklist_results_in_dotx


def _read_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            # Continue; some pages might fail extraction but overall text should still be present.
            parts.append("")
    return "\n".join(parts)


def _expected_results_from_pdf(
    pdf_text: str,
    *,
    class_name: str,
    templates_root: Path,
) -> Dict[str, str]:
    """
    Extract expected results for each checklist item by:
    - iterating the checklist Item labels (from the checklist XML)
    - finding each label in the extracted PDF text
    - looking for the nearest OK/RR/N/A token within a short window
    """
    rows = extract_checklist_items_for_class(templates_root, class_name)
    results: Dict[str, str] = {}

    # Normalize tokens for matching.
    for r in rows:
        # The PDF text extractor may introduce line breaks or punctuation differences inside labels.
        # So match each label as a sequence of tokens separated by flexible whitespace/punctuation.
        tokens = [t for t in re.findall(r"[A-Za-z0-9]+", r.item_label) if t.strip()]
        if not tokens:
            raise ValueError(f"Could not tokenize checklist item label: {r.item_label}")

        # Match across whitespace/punctuation differences introduced by PDF text extraction.
        # Allow *any non-alphanumeric* characters between tokens so labels like "pin(s)" still match.
        sep = r"[^A-Za-z0-9]*"
        pattern = sep.join(map(re.escape, tokens))
        m = re.search(pattern, pdf_text, flags=re.IGNORECASE)
        if not m:
            # Fallback: drop common stopwords.
            stop = {"AND", "OF", "THE", "TO", "IN", "FOR", "WITH", "AND/OR"}
            tokens2 = [t for t in tokens if t.upper() not in stop]
            if not tokens2:
                raise ValueError(f"Could not match checklist item label in PDF text: {r.item_label}")
            pattern2 = sep.join(map(re.escape, tokens2))
            m = re.search(pattern2, pdf_text, flags=re.IGNORECASE)

        if not m:
            raise ValueError(f"Could not match checklist item label in PDF text: {r.item_label}")

        idx = m.start()
        snippet = pdf_text[idx : idx + 300]
        # Prefer the most informative token when multiple could appear.
        snip_upper = snippet.upper()
        if "N/A" in snip_upper:
            results[r.label_slug] = "N/A"
        elif "RR" in snip_upper:
            results[r.label_slug] = "RR"
        elif "OK" in snip_upper:
            results[r.label_slug] = "OK"
        else:
            raise ValueError(f"No OK/RR/N/A token found near item label {r.item_label}")

    return results


def _extract_results_from_filled_docx(
    docx_path: Path,
) -> Dict[str, str]:
    with zipfile.ZipFile(docx_path, "r") as z:
        doc_name = next(n for n in z.namelist() if n.endswith("word/document.xml"))
        doc_xml = z.read(doc_name).decode("utf-8", "ignore")
    root = ET.fromstring(doc_xml)
    _, header_i, item_col, results_col = _find_checklist_table_and_columns(root)

    # Recreate the same table scanning logic as the fill engine.
    for tbl in root.iter():
        if _local_name(tbl.tag) != "tbl":
            continue
        rows = [tr for tr in tbl.iter() if _local_name(tr.tag) == "tr"]
        if header_i < 0 or header_i >= len(rows):
            continue
        header_tr = rows[header_i]
        header_tcs = [tc for tc in header_tr if _local_name(tc.tag) == "tc"]
        header_cells = [_cell_text(tc) for tc in header_tcs]
        joined = " | ".join(header_cells).lower()
        if not ("item" in joined and "type of inspection" in joined and "result" in joined and "comments" in joined):
            continue

        extracted: Dict[str, str] = {}
        # Fill should have one result per checklist row.
        for tr in rows[header_i + 1 :]:
            tcs = [tc for tc in tr if _local_name(tc.tag) == "tc"]
            if len(tcs) <= max(item_col, results_col):
                continue
            item_text = _cell_text(tcs[item_col])
            if not item_text or item_text.strip().lower() == "item":
                continue
            results_text = _cell_text(tcs[results_col]).strip()
            if results_text == "":
                # Mobile Crane templates may initially be empty, but after fill they should not be.
                continue

            # Map extracted result by label slug computed elsewhere (caller compares by label slug).
            # Here we store by raw item label text for now.
            extracted[item_text] = results_text
        return extracted

    raise ValueError(f"Could not locate checklist table in filled docx: {docx_path}")


def _compare_expected_vs_extracted(
    expected_results_by_slug: Dict[str, str],
    expected_rows,
    extracted_results_by_item_label_text: Dict[str, str],
) -> Dict[str, str]:
    """
    Compare extracted results against expected results keyed by LABELSLUG.
    extracted_results_by_item_label_text is keyed by the raw item label text.
    """
    mismatches: Dict[str, str] = {}

    # Duplicate item labels can exist; so compare by order.
    expected_slugs_by_item_label = {}
    for r in expected_rows:
        expected_slugs_by_item_label.setdefault(r.item_label, []).append(r.label_slug)

    seen_counts = {}
    for r in expected_rows:
        seen_counts[r.item_label] = seen_counts.get(r.item_label, 0) + 1

    # Better: use list-based counter to find which slug occurrence corresponds.
    label_seen_idx = {}
    for r in expected_rows:
        label_seen_idx[r.item_label] = label_seen_idx.get(r.item_label, 0)
        occ = label_seen_idx[r.item_label]
        label_seen_idx[r.item_label] += 1
        slug_list = expected_slugs_by_item_label.get(r.item_label, [])
        chosen_slug = slug_list[occ] if occ < len(slug_list) else slug_list[-1]

        expected = expected_results_by_slug.get(chosen_slug)
        if expected is None:
            continue
        extracted = extracted_results_by_item_label_text.get(r.item_label)
        if extracted != expected:
            mismatches[chosen_slug] = f"expected={expected} extracted={extracted}"

    return mismatches


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--templates-root", required=True)
    ap.add_argument("--telescopic-pdf", required=True, help="Example tel boom checklist PDF")
    ap.add_argument("--mobile-pdf", default=None, help="Optional example mobile crane checklist PDF")
    args = ap.parse_args()

    templates_root = Path(args.templates_root)
    telescopic_pdf = Path(args.telescopic_pdf)
    mobile_pdf = Path(args.mobile_pdf) if args.mobile_pdf else None

    work_dir = REPO_ROOT / "__validation_out__"
    work_dir.mkdir(parents=True, exist_ok=True)

    # ---- Telescopic Boom Lift: compare against example PDF ----
    tel_class = "Telescopic Boom Lift"
    tel_template = next((templates_root / tel_class).glob("Checklist*.dotx"))
    tel_rows = extract_checklist_items_for_class(templates_root, tel_class)

    tel_pdf_text = _read_pdf_text(telescopic_pdf)
    tel_expected = _expected_results_from_pdf(
        tel_pdf_text, class_name=tel_class, templates_root=templates_root
    )

    tel_out = work_dir / "telescopic_boom_lift_filled.docx"
    fill_checklist_results_in_dotx(
        tel_template, tel_out, templates_root, tel_class, tel_expected
    )

    tel_extracted_by_item = _extract_results_from_filled_docx(tel_out)
    tel_mismatches = _compare_expected_vs_extracted(tel_expected, tel_rows, tel_extracted_by_item)
    if tel_mismatches:
        raise SystemExit(f"Telescopic Boom Lift mismatches: {list(tel_mismatches.items())[:10]}")
    print("Telescopic Boom Lift validation: PASS")

    # ---- Mobile Crane: if example PDF is provided compare, else structural validation ----
    mob_class = "Mobile Crane"
    mob_template = next((templates_root / mob_class).glob("Checklist*.dotx"))
    mob_rows = extract_checklist_items_for_class(templates_root, mob_class)

    mob_out = work_dir / "mobile_crane_filled.docx"

    if mobile_pdf:
        mob_pdf_text = _read_pdf_text(mobile_pdf)
        mob_expected = _expected_results_from_pdf(
            mob_pdf_text, class_name=mob_class, templates_root=templates_root
        )
        fill_checklist_results_in_dotx(
            mob_template, mob_out, templates_root, mob_class, mob_expected
        )
        mob_extracted_by_item = _extract_results_from_filled_docx(mob_out)
        mob_mismatches = _compare_expected_vs_extracted(
            mob_expected, mob_rows, mob_extracted_by_item
        )
        if mob_mismatches:
            raise SystemExit(f"Mobile Crane mismatches: {list(mob_mismatches.items())[:10]}")
        print("Mobile Crane validation: PASS")
    else:
        # No example PDF available in the local storage: validate fill writes a result into every row.
        mob_expected = {r.label_slug: "OK" for r in mob_rows}
        fill_checklist_results_in_dotx(
            mob_template, mob_out, templates_root, mob_class, mob_expected
        )
        mob_extracted_by_item = _extract_results_from_filled_docx(mob_out)
        # Ensure each expected item label has a non-empty extracted result.
        missing = [r.item_label for r in mob_rows if r.item_label not in mob_extracted_by_item]
        if missing:
            raise SystemExit(f"Mobile Crane structural validation FAIL; missing results for {missing[:10]}")
        print("Mobile Crane structural validation: PASS (no example PDF provided)")


if __name__ == "__main__":
    main()

