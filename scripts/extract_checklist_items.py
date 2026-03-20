import argparse
import sys
from pathlib import Path

# Allow running this script directly from repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.checklist_xml import extract_checklist_items_for_class


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--templates-root", required=True)
    ap.add_argument("--class-name", required=True)
    args = ap.parse_args()

    rows = extract_checklist_items_for_class(args.templates_root, args.class_name)
    for r in rows:
        print(f"{r.index}\t{r.label_slug}\t{r.item_label}")


if __name__ == "__main__":
    main()

