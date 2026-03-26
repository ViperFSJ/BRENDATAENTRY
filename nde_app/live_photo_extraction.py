import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .photo_extraction import ExtractedField, ExtractionResult


@dataclass(frozen=True)
class OCRSnippet:
    text: str
    source_photo_type: str


def _guess_photo_type(path: Path) -> str:
    name = path.name.lower()
    if any(k in name for k in ("plate", "nameplate", "data_plate")):
        return "data_plate"
    if any(k in name for k in ("unit", "decal", "id")):
        return "unit_id_decal"
    if any(k in name for k in ("owner", "client")):
        return "owner_label"
    if any(k in name for k in ("brand", "logo")):
        return "branding_sticker"
    return "unknown"


def _run_tesseract_on_image(path: Path) -> str:
    if shutil.which("tesseract") is None:
        raise RuntimeError(
            "Live extraction requires Tesseract OCR. Install it (e.g. `brew install tesseract`) "
            "or provide Extraction JSON."
        )
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "--psm", "6"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Tesseract failed on {path.name}: {result.stderr.strip()}")
    return result.stdout or ""


def _first_match(patterns: Iterable[str], text: str, group: int = 1) -> Optional[str]:
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return (m.group(group) or "").strip()
    return None


def _pick_best(candidate_hits: List[Tuple[str, str]], preferred_type: str) -> Optional[Tuple[str, str]]:
    if not candidate_hits:
        return None
    for value, src in candidate_hits:
        if src == preferred_type:
            return value, src
    return candidate_hits[0]


def extract_from_photos(
    photo_paths: Sequence[Union[str, Path]],
) -> ExtractionResult:
    """
    Lightweight offline OCR extraction from current session photos.
    Uses local `tesseract` binary if available.
    """
    snippets: List[OCRSnippet] = []
    for p in photo_paths:
        path = Path(p)
        if not path.is_file():
            continue
        text = _run_tesseract_on_image(path)
        snippets.append(OCRSnippet(text=text, source_photo_type=_guess_photo_type(path)))

    if not snippets:
        return ExtractionResult(fields={})

    combined = "\n".join(s.text for s in snippets)
    field_hits: Dict[str, List[Tuple[str, str]]] = {
        "serial_no": [],
        "client_unit_id": [],
        "manufacturer": [],
        "model": [],
        "owner_name": [],
        "client_name": [],
        "equip_type": [],
        "capacity": [],
    }

    for sn in snippets:
        t = sn.text
        serial = _first_match(
            [
                r"\bserial\s*(?:no|number|#)?\s*[:\-]?\s*([A-Z0-9\-\/]{4,})",
                r"\bS\/N\s*[:\-]?\s*([A-Z0-9\-\/]{4,})",
            ],
            t,
        )
        if serial:
            field_hits["serial_no"].append((serial, sn.source_photo_type))

        unit = _first_match(
            [
                r"\bunit\s*(?:id|no|number|#)?\s*[:\-]?\s*([A-Z0-9\-\/]{3,})",
                r"\basset\s*(?:id|no|number|#)?\s*[:\-]?\s*([A-Z0-9\-\/]{3,})",
            ],
            t,
        )
        if unit:
            field_hits["client_unit_id"].append((unit, sn.source_photo_type))

        mfr = _first_match([r"\bmanufacturer\s*[:\-]?\s*([A-Za-z0-9 \-]{2,})"], t)
        if mfr:
            field_hits["manufacturer"].append((mfr.splitlines()[0].strip(), sn.source_photo_type))

        model = _first_match([r"\bmodel\s*(?:no|number|#)?\s*[:\-]?\s*([A-Za-z0-9 \-\/]{2,})"], t)
        if model:
            field_hits["model"].append((model.splitlines()[0].strip(), sn.source_photo_type))

        owner = _first_match([r"\bowner\s*[:\-]?\s*([A-Za-z0-9 &\-\.,]{3,})"], t)
        if owner:
            field_hits["owner_name"].append((owner.splitlines()[0].strip(), sn.source_photo_type))

        client = _first_match([r"\bclient\s*[:\-]?\s*([A-Za-z0-9 &\-\.,]{3,})"], t)
        if client:
            field_hits["client_name"].append((client.splitlines()[0].strip(), sn.source_photo_type))

        capacity = _first_match([r"\bcapacity\s*[:\-]?\s*([A-Za-z0-9 \-\/\.]{2,})"], t)
        if capacity:
            field_hits["capacity"].append((capacity.splitlines()[0].strip(), sn.source_photo_type))

    equip_type = _first_match(
        [
            r"\b(telescopic boom lift|scissor lift|bucket truck|manbasket|mobile crane|overhead crane|jib crane|forklift)\b"
        ],
        combined,
        group=1,
    )
    if equip_type:
        field_hits["equip_type"].append((equip_type.title(), "unknown"))

    fields: Dict[str, ExtractedField] = {}
    best_map = {
        "serial_no": _pick_best(field_hits["serial_no"], "data_plate"),
        "client_unit_id": _pick_best(field_hits["client_unit_id"], "unit_id_decal"),
        "manufacturer": _pick_best(field_hits["manufacturer"], "data_plate"),
        "model": _pick_best(field_hits["model"], "data_plate"),
        "owner_name": _pick_best(field_hits["owner_name"], "owner_label"),
        "client_name": _pick_best(field_hits["client_name"], "owner_label"),
        "equip_type": _pick_best(field_hits["equip_type"], "unknown"),
        "capacity": _pick_best(field_hits["capacity"], "data_plate"),
    }
    for name, hit in best_map.items():
        if not hit:
            continue
        value, src = hit
        fields[name] = ExtractedField(value=value, confidence=0.75, source_photo_type=src)
    return ExtractionResult(fields=fields)
