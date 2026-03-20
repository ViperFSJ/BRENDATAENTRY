import re
from typing import Dict, List, Tuple


def _slugify_base(label: str) -> str:
    """
    LABELSLUG base transform (without intra-class dedupe):
    - uppercase
    - remove parenthetical content like "(s)"
    - replace runs of non-[A-Z0-9] with underscores
    - collapse underscores and trim edges
    """
    s = (label or "").upper().strip()
    # Remove parenthetical content like "(s)".
    s = re.sub(r"\([^)]*\)", "", s)
    # Convert any non A-Z / 0-9 run to underscore.
    s = re.sub(r"[^A-Z0-9]+", "_", s)
    # Collapse multiple underscores.
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def slugify_label_base(label: str) -> str:
    """
    Public wrapper so other modules (e.g. docx fill) can compute a stable base key.
    """
    return _slugify_base(label)


def make_labelslugs(labels: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """
    Given ordered checklist row labels, create per-row LABELSLUG values:
    - Apply the base slug rules.
    - If duplicates occur within the class, append _2, _3, etc.

    Returns:
      - list of slugs aligned to `labels`
      - dict mapping original label text -> chosen slug (first occurrence)
    """
    slug_counts: Dict[str, int] = {}
    out: List[str] = []
    label_to_first_slug: Dict[str, str] = {}

    for label in labels:
        base = _slugify_base(label)
        if base == "":
            # Fallback: avoid empty token. (Won't usually happen for real checklist labels.)
            base = "ITEM"

        n = slug_counts.get(base, 0) + 1
        slug_counts[base] = n

        if n == 1:
            slug = base
        else:
            slug = f"{base}_{n}"

        out.append(slug)
        label_to_first_slug.setdefault(label, slug)

    return out, label_to_first_slug

