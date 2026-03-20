from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ExtractionFieldRule:
    field_name: str
    preferred_photo_types: List[str]
    min_confidence: float
    fallback_prompt: str


@dataclass(frozen=True)
class ExtractedField:
    value: str
    confidence: float
    source_photo_type: str


@dataclass
class ExtractionResult:
    """
    OCR/detection output keyed by canonical field name.
    Example fields:
      - serial_no
      - client_unit_id
      - manufacturer
      - model
      - owner_name
      - client_name
      - province
      - equip_type
    """

    fields: Dict[str, ExtractedField]


PHOTO_EXTRACTION_RULES: Dict[str, ExtractionFieldRule] = {
    "serial_no": ExtractionFieldRule(
        field_name="serial_no",
        preferred_photo_types=["data_plate"],
        min_confidence=0.85,
        fallback_prompt="Enter Serial Number",
    ),
    "client_unit_id": ExtractionFieldRule(
        field_name="client_unit_id",
        preferred_photo_types=["unit_id_decal", "data_plate"],
        min_confidence=0.80,
        fallback_prompt="Enter Client Unit ID",
    ),
    "manufacturer": ExtractionFieldRule(
        field_name="manufacturer",
        preferred_photo_types=["data_plate", "branding_sticker"],
        min_confidence=0.75,
        fallback_prompt="Enter Manufacturer",
    ),
    "model": ExtractionFieldRule(
        field_name="model",
        preferred_photo_types=["data_plate", "branding_sticker"],
        min_confidence=0.75,
        fallback_prompt="Enter Model",
    ),
    "equip_type": ExtractionFieldRule(
        field_name="equip_type",
        preferred_photo_types=["full_unit", "controls_panel", "data_plate"],
        min_confidence=0.65,
        fallback_prompt="Confirm Equipment Type",
    ),
    "owner_name": ExtractionFieldRule(
        field_name="owner_name",
        preferred_photo_types=["owner_label", "unit_id_decal"],
        min_confidence=0.70,
        fallback_prompt="Enter Owner Name",
    ),
    "client_name": ExtractionFieldRule(
        field_name="client_name",
        preferred_photo_types=["owner_label", "unit_id_decal"],
        min_confidence=0.70,
        fallback_prompt="Enter Client Name",
    ),
    "province": ExtractionFieldRule(
        field_name="province",
        preferred_photo_types=["data_plate", "location_signage"],
        min_confidence=0.60,
        fallback_prompt="Enter 2-letter Province (e.g. AB)",
    ),
    "capacity": ExtractionFieldRule(
        field_name="capacity",
        preferred_photo_types=["data_plate"],
        min_confidence=0.65,
        fallback_prompt="Enter Capacity (if shown on plate)",
    ),
    "client_reference": ExtractionFieldRule(
        field_name="client_reference",
        preferred_photo_types=["data_plate", "unit_id_decal"],
        min_confidence=0.65,
        fallback_prompt="Enter Client Reference (or -)",
    ),
    "lsd": ExtractionFieldRule(
        field_name="lsd",
        preferred_photo_types=["data_plate"],
        min_confidence=0.55,
        fallback_prompt="Enter LSD value (if applicable)",
    ),
    "basket_max_height": ExtractionFieldRule(
        field_name="basket_max_height",
        preferred_photo_types=["data_plate"],
        min_confidence=0.65,
        fallback_prompt="Enter Basket Maximum Height",
    ),
    "basket_max_reach": ExtractionFieldRule(
        field_name="basket_max_reach",
        preferred_photo_types=["data_plate"],
        min_confidence=0.65,
        fallback_prompt="Enter Basket Maximum Reach",
    ),
    "basket_length": ExtractionFieldRule(
        field_name="basket_length",
        preferred_photo_types=["data_plate"],
        min_confidence=0.65,
        fallback_prompt="Enter Basket Length",
    ),
    "basket_width": ExtractionFieldRule(
        field_name="basket_width",
        preferred_photo_types=["data_plate"],
        min_confidence=0.65,
        fallback_prompt="Enter Basket Width",
    ),
    "basket_height": ExtractionFieldRule(
        field_name="basket_height",
        preferred_photo_types=["data_plate"],
        min_confidence=0.65,
        fallback_prompt="Enter Basket Height",
    ),
}


def get_best_extracted_value(
    extraction: ExtractionResult,
    field_name: str,
) -> Optional[str]:
    """
    Returns OCR value only if confidence meets field threshold.
    """
    field = extraction.fields.get(field_name)
    if not field:
        return None
    rule = PHOTO_EXTRACTION_RULES.get(field_name)
    if not rule:
        return field.value
    if field.confidence >= rule.min_confidence and field.value.strip() != "":
        return field.value.strip()
    return None

