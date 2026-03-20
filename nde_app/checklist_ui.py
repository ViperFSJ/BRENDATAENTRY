from typing import Callable, Dict, List

from .checklist_xml import ChecklistRow


def _parse_index_list(raw: str, max_index: int) -> List[int]:
    """
    Parse a comma/space-separated list of 0-based indexes.
    Accepts empty string => [].
    """
    raw = (raw or "").strip()
    if raw == "":
        return []

    parts = []
    for token in raw.replace(",", " ").split():
        token = token.strip()
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(f"Invalid index: {token} (expected integer)")
        parts.append(int(token))

    # Validate bounds
    for i in parts:
        if i < 0 or i >= max_index:
            raise ValueError(f"Index out of range: {i} (valid 0..{max_index-1})")

    # Preserve order but dedupe
    out: List[int] = []
    for i in parts:
        if i not in out:
            out.append(i)
    return out


def prompt_checklist_results_cli(
    rows: List[ChecklistRow],
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> Dict[str, str]:
    """
    Prompt for per-checklist-row inspection results.

    Rules:
    - Default is OK for all items.
    - Technician can mark any items as RR and/or N/A.
    - If an item is selected in both RR and N/A lists, N/A wins (RR is overridden).
    """
    if not rows:
        raise ValueError("No checklist rows provided")

    print_fn("Checklist items:")
    for r in rows:
        print_fn(f"  [{r.index}] {r.item_label}  (LABELSLUG={r.label_slug})")

    all_ok = input_fn("All checklist items OK? (y/n): ").strip().lower()
    if all_ok in ("y", "yes"):
        return {r.label_slug: "OK" for r in rows}

    rr_raw = input_fn(
        "Enter indexes to mark RR (comma or space separated). Press Enter for none: "
    )
    rr_indexes = _parse_index_list(rr_raw, max_index=len(rows))

    na_raw = input_fn(
        "Enter indexes to mark N/A (comma or space separated). Press Enter for none: "
    )
    na_indexes = _parse_index_list(na_raw, max_index=len(rows))

    rr_set = set(rr_indexes)
    na_set = set(na_indexes)

    results: Dict[str, str] = {}
    for r in rows:
        if r.index in na_set:
            results[r.label_slug] = "N/A"
        elif r.index in rr_set:
            results[r.label_slug] = "RR"
        else:
            results[r.label_slug] = "OK"

    return results

