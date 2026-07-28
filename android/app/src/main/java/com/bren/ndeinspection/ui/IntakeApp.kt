package com.bren.ndeinspection.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun IntakeApp(vm: IntakeViewModel = viewModel()) {
    val state by vm.state.collectAsState()
    var showCamera by remember { mutableStateOf(false) }

    if (showCamera) {
        CameraCaptureScreen(
            onPhotoCaptured = { uri -> vm.addPhotos(listOf(uri)) },
            onClose = { showCamera = false },
        )
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("NDE Inspection") })
        }
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
        ) {
            when (state.step) {
                WizardStep.SETUP -> SetupStep(
                    state = state,
                    vm = vm,
                    onOpenCamera = { showCamera = true },
                )
                WizardStep.FIELDS -> FieldsStep(state, vm)
                WizardStep.CHECKLIST -> ChecklistStep(state, vm)
                WizardStep.CONFIRM_EXISTING -> ConfirmExistingStep(state, vm)
                WizardStep.RUNNING -> BusyStep(state.message.ifBlank { "Working…" })
                WizardStep.DONE -> DoneStep(state, vm)
                WizardStep.ERROR -> ErrorStep(state, vm)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SetupStep(
    state: UiState,
    vm: IntakeViewModel,
    onOpenCamera: () -> Unit,
) {
    val context = LocalContext.current
    var cameraDenied by remember { mutableStateOf(false) }

    val pickImages = rememberLauncherForActivityResult(
        ActivityResultContracts.GetMultipleContents()
    ) { uris -> if (uris.isNotEmpty()) vm.addPhotos(uris) }

    val requestCameraPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            cameraDenied = false
            onOpenCamera()
        } else {
            cameraDenied = true
        }
    }

    fun openCameraWithPermission() {
        val granted = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.CAMERA,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) onOpenCamera() else requestCameraPermission.launch(Manifest.permission.CAMERA)
    }

    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Start inspection", style = MaterialTheme.typography.headlineSmall)
        Text("Choose equipment class, dates, and optional photos. OCR runs on-device (ML Kit) — no Tesseract install.")

        ClassDropdown(state.classNames, state.className, onSelect = vm::setClass)

        OutlinedTextField(
            value = state.inspectionDate,
            onValueChange = vm::setInspectionDate,
            label = { Text("Inspection date") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = state.expiryDate,
            onValueChange = vm::setExpiryDate,
            label = { Text("Expiry date") },
            modifier = Modifier.fillMaxWidth(),
        )

        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Force new RAEQ (trial)", modifier = Modifier.weight(1f))
            Switch(checked = state.forceNewEquipment, onCheckedChange = vm::setForceNew)
        }

        Text("Photos: ${state.photoUris.size} selected")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { openCameraWithPermission() }) { Text("Take photo") }
            OutlinedButton(onClick = { pickImages.launch("image/*") }) { Text("From device") }
            OutlinedButton(onClick = vm::clearPhotos, enabled = state.photoUris.isNotEmpty()) {
                Text("Clear")
            }
        }
        if (cameraDenied) {
            Text(
                "Camera permission denied. You can still use From device, or enable Camera in system settings.",
                style = MaterialTheme.typography.bodySmall,
            )
        }

        if (state.message.isNotBlank()) Text(state.message)
        if (state.busy) {
            CircularProgressIndicator()
        } else {
            Button(onClick = vm::startFromSetup, modifier = Modifier.fillMaxWidth()) {
                Text("Continue")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ClassDropdown(options: List<String>, selected: String, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = selected,
            onValueChange = {},
            readOnly = true,
            label = { Text("Equipment class") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            modifier = Modifier
                .menuAnchor()
                .fillMaxWidth(),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { name ->
                DropdownMenuItem(
                    text = { Text(name) },
                    onClick = {
                        onSelect(name)
                        expanded = false
                    },
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FieldsStep(state: UiState, vm: IntakeViewModel) {
    val provinces = listOf(
        "AB", "BC", "SK", "MB", "ON", "QC", "NB", "NS", "PE", "NL", "YT", "NT", "NU",
    )
    val labels = mapOf(
        "client_name" to "Client name",
        "owner_name" to "Owner name",
        "job_no" to "Job number",
        "location" to "Location",
        "province" to "Province (required)",
        "lsd" to "LSD",
        "client_unit_id" to "Client unit ID",
        "serial_no" to "Serial number",
        "manufacturer" to "Manufacturer",
        "model" to "Model",
        "equip_type" to "Equipment type",
        "capacity" to "Capacity",
        "client_reference" to "Client reference (blank = unit ID)",
        "basket_max_height" to "Basket max height",
        "basket_max_reach" to "Basket max reach",
        "basket_length" to "Basket length",
        "basket_width" to "Basket width",
        "basket_height" to "Basket height",
    )
    val fieldOrder = state.fieldValues.keys.toList()
    Column {
        Text("Review fields", style = MaterialTheme.typography.headlineSmall)
        if (state.message.isNotBlank()) {
            Text(state.message, modifier = Modifier.padding(vertical = 8.dp))
        }
        LazyColumn(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(fieldOrder) { key ->
                if (key == "province") {
                    ProvinceDropdown(
                        options = provinces,
                        selected = state.fieldValues["province"].orEmpty(),
                        onSelect = { vm.updateField("province", it) },
                    )
                } else {
                    OutlinedTextField(
                        value = state.fieldValues[key].orEmpty(),
                        onValueChange = { vm.updateField(key, it) },
                        label = { Text(labels[key] ?: key) },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                    )
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        Button(onClick = vm::continueToChecklist, modifier = Modifier.fillMaxWidth()) {
            Text("Continue to checklist")
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ProvinceDropdown(
    options: List<String>,
    selected: String,
    onSelect: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = selected,
            onValueChange = {},
            readOnly = true,
            label = { Text("Province (required)") },
            placeholder = { Text("Select province") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            modifier = Modifier
                .menuAnchor()
                .fillMaxWidth(),
            isError = selected.isBlank(),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { code ->
                DropdownMenuItem(
                    text = { Text(code) },
                    onClick = {
                        onSelect(code)
                        expanded = false
                    },
                )
            }
        }
    }
}

@Composable
private fun ChecklistStep(state: UiState, vm: IntakeViewModel) {
    val hasRr = state.checklistResults.values.any { it.equals("RR", true) }
    Column {
        Text("Checklist", style = MaterialTheme.typography.headlineSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 8.dp)) {
            Button(onClick = vm::markAllOk) { Text("Mark all OK") }
        }
        LazyColumn(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(state.checklistRows, key = { it.labelSlug }) { row ->
                Column(Modifier.fillMaxWidth()) {
                    Text("${row.index}. ${row.itemLabel}", style = MaterialTheme.typography.bodyMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf("OK", "RR", "N/A").forEach { choice ->
                            FilterChip(
                                selected = state.checklistResults[row.labelSlug] == choice,
                                onClick = { vm.setChecklistResult(row.labelSlug, choice) },
                                label = { Text(choice) },
                            )
                        }
                    }
                }
            }
        }
        if (hasRr && state.statusChoices.isNotEmpty()) {
            Text("Status (RR found)", modifier = Modifier.padding(top = 8.dp))
            state.statusChoices.forEach { (label, _) ->
                FilterChip(
                    selected = state.selectedStatus == label,
                    onClick = { vm.setStatus(label) },
                    label = { Text(label) },
                    modifier = Modifier.padding(end = 6.dp, top = 4.dp),
                )
            }
        }
        Spacer(Modifier.height(8.dp))
        Button(onClick = vm::runInspection, modifier = Modifier.fillMaxWidth()) {
            Text("Generate documents")
        }
    }
}

@Composable
private fun ConfirmExistingStep(state: UiState, vm: IntakeViewModel) {
    val c = state.pendingCandidate
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Possible existing equipment", style = MaterialTheme.typography.headlineSmall)
        if (c != null) {
            Text("RAEQ: ${c.raeq}")
            Text("Match: ${c.matchStrength}")
            Text("Unit ID: ${c.clientUnitId}")
            Text("Serial: ${c.serialNo}")
            Text("Class: ${c.className}")
        }
        Text("Is this the same equipment?")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { vm.answerExisting(true) }) { Text("Yes") }
            OutlinedButton(onClick = { vm.answerExisting(false) }) { Text("No — assign new") }
        }
    }
}

@Composable
private fun BusyStep(message: String) {
    Column(
        Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator()
        Spacer(Modifier.height(16.dp))
        Text(message)
    }
}

@Composable
private fun DoneStep(state: UiState, vm: IntakeViewModel) {
    val context = LocalContext.current
    val result = state.result
    Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.verticalScroll(rememberScrollState())) {
        Text("Complete", style = MaterialTheme.typography.headlineSmall)
        if (result != null) {
            Text("RAEQ: ${result.raeq}")
            Text("Decision: ${result.decision}")
            Text("Photos embedded: ${result.insertedPhotoCount}")
            if (state.photoUris.isNotEmpty() && result.insertedPhotoCount == 0) {
                Text(
                    "Warning: photos were selected but none were embedded in the checklist. Share the checklist and confirm figures, or re-run with Take photo / From device.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Text("Checklist:\n${result.checklistPath}")
            Text("Certificate:\n${result.certificatePath}")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { shareFile(context, result.checklistPath) }) { Text("Share checklist") }
                Button(onClick = { shareFile(context, result.certificatePath) }) { Text("Share certificate") }
            }
        }
        OutlinedButton(onClick = vm::reset, modifier = Modifier.fillMaxWidth()) {
            Text("New inspection")
        }
    }
}

@Composable
private fun ErrorStep(state: UiState, vm: IntakeViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Something went wrong", style = MaterialTheme.typography.headlineSmall)
        Text(state.error ?: "Unknown error")
        Button(onClick = vm::reset) { Text("Start over") }
    }
}

private fun shareFile(context: android.content.Context, path: String) {
    val file = File(path)
    if (!file.exists()) return
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "Share document"))
}
