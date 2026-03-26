from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from .photo_extraction import ExtractionResult
from .session_pipeline import (
    PhotoFirstSessionInput,
    SessionResult,
    StatusChoice,
    run_photo_first_session,
)


ConfirmExistingCallback = Callable[[Dict[str, str]], bool]
ResolveMissingFieldCallback = Callable[[str, str], str]
ChecklistResultsProvider = Callable
StatusChoiceCallback = Callable[[List["UIStatusChoice"]], str]


@dataclass(frozen=True)
class UIStatusChoice:
    label: str
    is_default: bool = False


@dataclass
class UIInspectionRequest:
    class_name: str
    inspection_date: str
    expiry_date: str
    extraction_result: ExtractionResult
    technician_id: str = "DEFAULT_TECH"
    defaults: Optional[Dict[str, str]] = None
    photo_paths: Optional[list] = None


@dataclass(frozen=True)
class SessionService:
    """
    Thin wrapper intended for desktop/offline UI layers.

    It keeps the current pipeline untouched and simply translates
    UI request/callback wiring into run_photo_first_session calls.
    """

    db_path: Union[str, Path]
    templates_root: Union[str, Path]
    output_root: Union[str, Path]
    history_root: Optional[Union[str, Path]] = None

    def run_with_callbacks(
        self,
        *,
        request: UIInspectionRequest,
        confirm_existing_callback: ConfirmExistingCallback,
        resolve_missing_field_callback: ResolveMissingFieldCallback,
        checklist_results_provider: Optional[ChecklistResultsProvider] = None,
        status_choice_callback: Optional[StatusChoiceCallback] = None,
    ) -> SessionResult:
        pipeline_status_callback = None
        if status_choice_callback is not None:
            def pipeline_status_callback(choices: List[StatusChoice]) -> str:
                return status_choice_callback(
                    [UIStatusChoice(label=c.label, is_default=c.is_default) for c in choices]
                )

        return run_photo_first_session(
            db_path=self.db_path,
            templates_root=self.templates_root,
            output_root=self.output_root,
            session=PhotoFirstSessionInput(
                class_name=request.class_name,
                inspection_date=request.inspection_date,
                expiry_date=request.expiry_date,
                extraction_result=request.extraction_result,
                defaults=request.defaults or {},
                technician_id=request.technician_id,
                photo_paths=request.photo_paths,
            ),
            confirm_existing_callback=confirm_existing_callback,
            resolve_missing_field_callback=resolve_missing_field_callback,
            checklist_results_provider=checklist_results_provider,
            status_choice_callback=pipeline_status_callback,
            history_root=self.history_root,
        )
