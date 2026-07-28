package com.bren.ndeinspection.ui

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.bren.ndeinspection.NdeApp
import com.bren.ndeinspection.domain.ChecklistRow
import com.bren.ndeinspection.domain.EquipmentCandidate
import com.bren.ndeinspection.domain.ExtractionResult
import com.bren.ndeinspection.domain.SessionFields
import com.bren.ndeinspection.domain.SessionResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.coroutines.resume

enum class WizardStep {
    SETUP,
    FIELDS,
    CHECKLIST,
    CONFIRM_EXISTING,
    RUNNING,
    DONE,
    ERROR,
}

data class UiState(
    val step: WizardStep = WizardStep.SETUP,
    val classNames: List<String> = emptyList(),
    val className: String = "",
    val inspectionDate: String = defaultDate(0),
    val expiryDate: String = defaultDate(365),
    val photoUris: List<Uri> = emptyList(),
    val forceNewEquipment: Boolean = true,
    val extraction: ExtractionResult = ExtractionResult(),
    val fieldValues: Map<String, String> = emptyMap(),
    val checklistRows: List<ChecklistRow> = emptyList(),
    val checklistResults: Map<String, String> = emptyMap(),
    val statusChoices: List<Pair<String, Boolean>> = emptyList(),
    val selectedStatus: String = "Certification recommended",
    val pendingCandidate: EquipmentCandidate? = null,
    val result: SessionResult? = null,
    val busy: Boolean = false,
    val message: String = "",
    val error: String? = null,
)

private fun defaultDate(plusDays: Long): String {
    val d = LocalDate.now().plusDays(plusDays)
    return d.format(DateTimeFormatter.ofPattern("MMMM d, yyyy", Locale.US))
}

class IntakeViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = (app as NdeApp).repository
    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state

    private var confirmContinuation: ((Boolean) -> Unit)? = null

    init {
        val classes = repo.listClasses()
        _state.update {
            it.copy(
                classNames = classes,
                className = classes.firstOrNull().orEmpty(),
            )
        }
        viewModelScope.launch { repo.seedRaeqPool() }
    }

    fun setClass(name: String) = _state.update { it.copy(className = name) }
    fun setInspectionDate(v: String) = _state.update { it.copy(inspectionDate = v) }
    fun setExpiryDate(v: String) = _state.update { it.copy(expiryDate = v) }
    fun setForceNew(v: Boolean) = _state.update { it.copy(forceNewEquipment = v) }

    fun addPhotos(uris: List<Uri>) {
        if (uris.isEmpty()) return
        val persisted = repo.persistPhotos(uris)
        _state.update {
            it.copy(photoUris = (it.photoUris + persisted.ifEmpty { uris }).distinct())
        }
    }

    fun clearPhotos() = _state.update { it.copy(photoUris = emptyList()) }

    fun updateField(key: String, value: String) = _state.update {
        it.copy(fieldValues = it.fieldValues + (key to value), message = "")
    }

    fun setChecklistResult(slug: String, result: String) = _state.update {
        it.copy(checklistResults = it.checklistResults + (slug to result))
    }

    fun markAllOk() = _state.update { st ->
        st.copy(checklistResults = st.checklistRows.associate { it.labelSlug to "OK" })
    }

    fun setStatus(status: String) = _state.update { it.copy(selectedStatus = status) }

    fun answerExisting(yes: Boolean) {
        confirmContinuation?.invoke(yes)
        confirmContinuation = null
        _state.update { it.copy(pendingCandidate = null, step = WizardStep.RUNNING) }
    }

    fun reset() {
        val classes = _state.value.classNames
        _state.value = UiState(
            classNames = classes,
            className = classes.firstOrNull().orEmpty(),
        )
    }

    fun startFromSetup() {
        val st = _state.value
        if (st.className.isBlank()) {
            _state.update { it.copy(error = "Pick an equipment class", step = WizardStep.ERROR) }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(busy = true, message = "Running OCR…", error = null) }
            val extraction = try {
                if (st.photoUris.isEmpty()) ExtractionResult()
                else repo.extractFromPhotos(st.photoUris)
            } catch (e: Exception) {
                ExtractionResult()
            }
            // Put province/job/location near the top so they aren't missed.
            val defaults = linkedMapOf(
                "client_name" to "",
                "owner_name" to "",
                "job_no" to "",
                "location" to "",
                "province" to "",
                "lsd" to "",
                "client_unit_id" to "",
                "serial_no" to "",
                "manufacturer" to "",
                "model" to "",
                "equip_type" to st.className,
                "capacity" to "",
                "client_reference" to "",
            )
            val merged = defaults.mapValues { (k, def) ->
                extraction.fields[k]?.value?.takeIf { it.isNotBlank() } ?: def
            }.toMutableMap()
            // Never auto-fill province from OCR — always confirm inspection province.
            merged["province"] = ""
            if (repo.needsBasketFields(st.className)) {
                listOf(
                    "basket_max_height",
                    "basket_max_reach",
                    "basket_length",
                    "basket_width",
                    "basket_height",
                ).forEach { merged.putIfAbsent(it, "") }
            }
            val rows = repo.checklistRows(st.className)
            val statusChoices = repo.statusChoices(st.className)
            _state.update {
                it.copy(
                    busy = false,
                    extraction = extraction,
                    fieldValues = merged,
                    checklistRows = rows,
                    checklistResults = rows.associate { r -> r.labelSlug to "OK" },
                    statusChoices = statusChoices,
                    selectedStatus = statusChoices.firstOrNull { c -> c.second }?.first
                        ?: statusChoices.firstOrNull()?.first
                        ?: "Certification recommended",
                    step = WizardStep.FIELDS,
                    message = if (extraction.fields.isEmpty()) {
                        "No OCR fields found — enter values manually. Province is required."
                    } else {
                        "OCR filled ${extraction.fields.size} field(s). Confirm province (required), then continue."
                    },
                )
            }
        }
    }

    fun continueToChecklist() {
        val province = _state.value.fieldValues["province"].orEmpty().trim()
        if (province.length != 2) {
            _state.update {
                it.copy(message = "Select the 2-letter province where the inspection is taking place (e.g. AB).")
            }
            return
        }
        _state.update { it.copy(step = WizardStep.CHECKLIST, message = "") }
    }

    fun runInspection() {
        val st = _state.value
        viewModelScope.launch {
            _state.update { it.copy(busy = true, step = WizardStep.RUNNING, message = "Generating documents…") }
            try {
                val fv = st.fieldValues
                val clientRef = fv["client_reference"].orEmpty().trim().ifEmpty {
                    fv["client_unit_id"].orEmpty().ifEmpty { "-" }
                }
                val fields = SessionFields(
                    className = st.className,
                    clientName = fv["client_name"].orEmpty(),
                    ownerName = fv["owner_name"].orEmpty().ifBlank { fv["client_name"].orEmpty() },
                    clientUnitId = fv["client_unit_id"].orEmpty(),
                    serialNo = fv["serial_no"].orEmpty(),
                    manufacturer = fv["manufacturer"].orEmpty(),
                    model = fv["model"].orEmpty(),
                    inspectionDate = st.inspectionDate,
                    expiryDate = st.expiryDate,
                    equipType = fv["equip_type"].orEmpty().ifBlank { st.className },
                    jobNo = fv["job_no"].orEmpty(),
                    location = fv["location"].orEmpty(),
                    capacity = fv["capacity"].orEmpty(),
                    clientReference = clientRef,
                    lsd = fv["lsd"].orEmpty(),
                    province = fv["province"].orEmpty(),
                    basketMaxHeight = fv["basket_max_height"].orEmpty(),
                    basketMaxReach = fv["basket_max_reach"].orEmpty(),
                    basketLength = fv["basket_length"].orEmpty(),
                    basketWidth = fv["basket_width"].orEmpty(),
                    basketHeight = fv["basket_height"].orEmpty(),
                )
                val results = st.checklistResults.toMutableMap()
                if (results.values.any { it.equals("RR", true) }) {
                    results["__status__"] = st.selectedStatus
                }
                val result = repo.runSession(
                    fields = fields,
                    checklistResults = results,
                    photoUris = st.photoUris,
                    forceNewEquipment = st.forceNewEquipment,
                    confirmExisting = { candidate ->
                        suspendCancellableCoroutine { cont ->
                            confirmContinuation = { yes -> cont.resume(yes) }
                            _state.update {
                                it.copy(
                                    pendingCandidate = candidate,
                                    step = WizardStep.CONFIRM_EXISTING,
                                    busy = false,
                                )
                            }
                        }
                    },
                )
                _state.update {
                    it.copy(
                        busy = false,
                        result = result,
                        step = WizardStep.DONE,
                        message = "Session complete: ${result.raeq}",
                    )
                }
            } catch (e: Exception) {
                _state.update {
                    it.copy(
                        busy = false,
                        step = WizardStep.ERROR,
                        error = e.message ?: e.toString(),
                    )
                }
            }
        }
    }
}
