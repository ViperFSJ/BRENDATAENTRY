from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from .checklist_ui import prompt_checklist_results_cli
from .checklist_photo_embed import insert_photos_into_checklist_figures
from .checklist_xml import extract_checklist_items_for_class
from .template_paths import find_certificate_template, find_checklist_template
from .db import init_db, save_checklist_results
from .docx_fill_certificate import fill_certificate_dotx
from .docx_fill_checklist import (
    fill_checklist_results_in_dotx,
    read_status_choices_from_template,
    template_has_basket_section,
)
from .photo_extraction import (
    PHOTO_EXTRACTION_RULES,
    ExtractionResult,
    get_best_extracted_value,
)
from .raeq_assign import (
    identify_or_assign_raeq_with_confirmation,
    mark_inspection_started,
)


def _is_yes(value: str) -> bool:
    s = (value or "").strip().lower()
    return s == "" or s in ("y", "yes", "true", "1")


@dataclass
class SessionInput:
    class_name: str
    client_name: str
    owner_name: str
    client_unit_id: str
    serial_no: str
    manufacturer: str
    model: str
    inspection_date: str
    expiry_date: str
    equip_type: str
    job_no: str = ""
    location: str = ""
    capacity: str = ""
    client_reference: str = "-"
    lsd: str = ""
    photo_paths: Optional[list] = None
    province: str = ""
    basket_max_height: str = ""
    basket_max_reach: str = ""
    basket_length: str = ""
    basket_width: str = ""
    basket_height: str = ""
    technician_id: str = "DEFAULT_TECH"


@dataclass
class SessionResult:
    raeq: str
    decision: str
    checklist_docx: Path
    certificate_docx: Path
    checklist_results_by_slug: Dict[str, str]
    inserted_photo_count: int = 0


@dataclass
class PhotoFirstSessionInput:
    class_name: str
    inspection_date: str
    expiry_date: str
    extraction_result: ExtractionResult
    # Optional defaults if OCR misses/low confidence
    defaults: Optional[Dict[str, str]] = None
    technician_id: str = "DEFAULT_TECH"
    photo_paths: Optional[list] = None


@dataclass(frozen=True)
class StatusChoice:
    label: str
    is_default: bool = False


def _status_choices_for_template(checklist_template: Path) -> List[StatusChoice]:
    try:
        choices = read_status_choices_from_template(checklist_template)
    except Exception:
        choices = []
    if choices:
        return [StatusChoice(label=c["label"], is_default=bool(c.get("is_default"))) for c in choices]
    return [
        StatusChoice(label="Requires review", is_default=True),
        StatusChoice(label="Certification recommended", is_default=False),
    ]


def _class_uses_basket_fields(checklist_template: Path) -> bool:
    try:
        return template_has_basket_section(checklist_template)
    except Exception:
        return False


def run_inspection_session(
    *,
    db_path: Union[str, Path],
    templates_root: Union[str, Path],
    output_root: Union[str, Path],
    session: SessionInput,
    confirm_existing_callback: Callable[[Dict[str, str]], bool],
    resolve_missing_field_callback: Optional[Callable[[str, str], str]] = None,
    checklist_results_provider: Optional[Callable] = None,
    status_choice_callback: Optional[Callable[[List[StatusChoice]], str]] = None,
    history_root: Optional[Union[str, Path]] = None,
) -> SessionResult:
    """
    Orchestrates one inspection session:
      1) identify existing by unit+serial and ask tech confirmation
      2) assign new RAEQ if needed
      3) collect checklist OK/RR/N/A
      4) fill checklist + certificate docs
      5) persist checklist results + inspection record
    """
    db_path = Path(db_path)
    templates_root = Path(templates_root)
    output_root = Path(output_root)

    init_db(db_path)

    # Identify existing or assign new
    raeq, decision = identify_or_assign_raeq_with_confirmation(
        db_path,
        technician_id=session.technician_id,
        class_name=session.class_name,
        client_unit_id=session.client_unit_id,
        serial_no=session.serial_no,
        equipment_fields={
            "client_name": session.client_name,
            "client_unit_id": session.client_unit_id,
            "owner_name": session.owner_name,
            "province": session.province,
            "manufacturer": session.manufacturer,
            "model": session.model,
            "serial_no": session.serial_no,
        },
        confirm_existing_callback=confirm_existing_callback,
        history_root=history_root,
    )

    # Checklist results capture
    checklist_rows = extract_checklist_items_for_class(templates_root, session.class_name)
    if checklist_results_provider is None:
        checklist_results = prompt_checklist_results_cli(checklist_rows)
    else:
        checklist_results = checklist_results_provider(checklist_rows)

    # Output/template paths
    class_dir = templates_root / session.class_name
    checklist_template = find_checklist_template(class_dir)
    cert_template = find_certificate_template(class_dir)

    has_rr = any((v or "").strip().upper() == "RR" for v in checklist_results.values())
    status_value = "Certification recommended"
    if has_rr:
        status_choices = _status_choices_for_template(checklist_template)
        default_status = next((c.label for c in status_choices if c.is_default), status_choices[0].label)
        if status_choice_callback is not None:
            chosen = (status_choice_callback(status_choices) or "").strip()
            status_value = chosen or default_status
        elif resolve_missing_field_callback is not None:
            manual = (
                resolve_missing_field_callback(
                    "status",
                    f"RR items found. Enter Status (default: {default_status})",
                ).strip()
            )
            status_value = manual or default_status
        else:
            status_value = "Requires review"

    out_dir = output_root / session.class_name / raeq
    out_dir.mkdir(parents=True, exist_ok=True)

    checklist_docx = out_dir / f"{raeq}_checklist.docx"
    certificate_docx = out_dir / f"{raeq}_certificate.docx"

    # Fill docs
    fill_checklist_results_in_dotx(
        checklist_template,
        checklist_docx,
        templates_root,
        session.class_name,
        checklist_results,
        fields={
            "client_name": session.client_name,
            "owner_name": session.owner_name,
            "raeq": raeq,
            "job_no": session.job_no,
            "equip_type": session.equip_type,
            "location": session.location,
            "manufacturer": session.manufacturer,
            "model": session.model,
            "serial_no": session.serial_no,
            "client_unit_id": session.client_unit_id,
            "client_reference": session.client_reference,
            "capacity": session.capacity,
            "next_inspection_date": session.expiry_date,
            "status": status_value,
            "inspection_date": session.inspection_date,
            "inspection_type": "Visual/MPI",
            "lsd": session.lsd,
            "province": session.province,
            "basket_max_height": session.basket_max_height,
            "basket_max_reach": session.basket_max_reach,
            "basket_length": session.basket_length,
            "basket_width": session.basket_width,
            "basket_height": session.basket_height,
        },
    )

    inserted_photo_count = 0
    if session.photo_paths:
        inserted_photo_count = insert_photos_into_checklist_figures(
            checklist_docx,
            session.photo_paths,
        )

    fill_certificate_dotx(
        cert_template,
        certificate_docx,
        fields={
            "client_name": session.client_name,
            "raeq": raeq,
            "equip_type": session.equip_type,
            "inspection_date": session.inspection_date,
            "expiry_date": session.expiry_date,
            "manufacturer": session.manufacturer,
            "model": session.model,
            "serial_no": session.serial_no,
            "client_unit_id": session.client_unit_id,
            "inspector_name": "Brennan Maier MT CGSB No.20220",
            "engineer_name": "Shawn Santo, P.Eng.",
        },
    )

    # Persist inspection artifacts
    save_checklist_results(
        db_path,
        raeq=raeq,
        class_name=session.class_name,
        results_by_label_slug=checklist_results,
    )
    mark_inspection_started(
        db_path,
        technician_id=session.technician_id,
        raeq=raeq,
        inspection_date=session.inspection_date,
        class_name=session.class_name,
    )

    return SessionResult(
        raeq=raeq,
        decision=decision,
        checklist_docx=checklist_docx,
        certificate_docx=certificate_docx,
        checklist_results_by_slug=checklist_results,
        inserted_photo_count=inserted_photo_count,
    )


def run_photo_first_session(
    *,
    db_path: Union[str, Path],
    templates_root: Union[str, Path],
    output_root: Union[str, Path],
    session: PhotoFirstSessionInput,
    confirm_existing_callback: Callable[[Dict[str, str]], bool],
    resolve_missing_field_callback: Callable[[str, str], str],
    checklist_results_provider: Optional[Callable] = None,
    status_choice_callback: Optional[Callable[[List[StatusChoice]], str]] = None,
    history_root: Optional[Union[str, Path]] = None,
) -> SessionResult:
    """
    Photo-first wrapper:
      1) resolve fields from OCR/detection with confidence thresholds
      2) prompt only for missing/low-confidence values
      3) run the normal inspection session flow
    """
    defaults = session.defaults or {}

    def resolve(field_name: str) -> str:
        auto_value = get_best_extracted_value(session.extraction_result, field_name)
        if auto_value:
            return auto_value
        default_value = defaults.get(field_name, "").strip()
        if default_value:
            return default_value
        rule = PHOTO_EXTRACTION_RULES.get(field_name)
        prompt = rule.fallback_prompt if rule else f"Enter {field_name}"
        return resolve_missing_field_callback(field_name, prompt)

    class_name = session.class_name
    # Per your workflow:
    # - job_no and location are tech-provided
    # - capacity/client_reference should come from OCR if strong, else prompt
    job_no_default = (defaults.get("job_no", "") if defaults else "").strip()
    location_default = (defaults.get("location", "") if defaults else "").strip()
    job_no = job_no_default or resolve_missing_field_callback("job_no", "Enter Job Number")
    location = location_default or resolve_missing_field_callback("location", "Enter Location")
    province = resolve_missing_field_callback("province", "Enter 2-letter Province (e.g. AB)")
    lsd = resolve_missing_field_callback("lsd", "Enter LSD value")
    checklist_template = find_checklist_template(Path(templates_root) / class_name)
    needs_basket = _class_uses_basket_fields(checklist_template)

    basket_max_height = ""
    basket_max_reach = ""
    basket_length = ""
    basket_width = ""
    basket_height = ""
    if needs_basket:
        basket_max_height = resolve("basket_max_height")
        basket_max_reach = resolve("basket_max_reach")
        basket_length = resolve("basket_length")
        basket_width = resolve("basket_width")
        basket_height = resolve("basket_height")

    input_obj = SessionInput(
        technician_id=session.technician_id or "DEFAULT_TECH",
        class_name=class_name,
        client_name=resolve("client_name"),
        owner_name=resolve("owner_name"),
        client_unit_id=resolve("client_unit_id"),
        serial_no=resolve("serial_no"),
        manufacturer=resolve("manufacturer"),
        model=resolve("model"),
        inspection_date=session.inspection_date,
        expiry_date=session.expiry_date,
        equip_type=resolve("equip_type"),
        job_no=job_no,
        location=location,
        capacity=resolve("capacity"),
        client_reference="",
        lsd=lsd,
        photo_paths=session.photo_paths,
        province=province,
        basket_max_height=basket_max_height,
        basket_max_reach=basket_max_reach,
        basket_length=basket_length,
        basket_width=basket_width,
        basket_height=basket_height,
    )

    same_ref_ans = resolve_missing_field_callback(
        "client_reference_same_as_unit_id",
        "Is Client Reference same as Unit ID? (y/n)",
    )
    if _is_yes(same_ref_ans):
        input_obj.client_reference = input_obj.client_unit_id
    else:
        client_ref = resolve_missing_field_callback(
            "client_reference",
            "Enter Client Reference (press Enter for -)",
        ).strip()
        input_obj.client_reference = client_ref if client_ref else "-"

    return run_inspection_session(
        db_path=db_path,
        templates_root=templates_root,
        output_root=output_root,
        session=input_obj,
        confirm_existing_callback=confirm_existing_callback,
        resolve_missing_field_callback=resolve_missing_field_callback,
        checklist_results_provider=checklist_results_provider,
        status_choice_callback=status_choice_callback,
        history_root=history_root,
    )

