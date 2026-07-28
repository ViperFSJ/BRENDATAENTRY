package com.bren.ndeinspection.domain

data class ChecklistRow(
    val index: Int,
    val itemLabel: String,
    val labelSlug: String,
)

data class ExtractedField(
    val value: String,
    val confidence: Float,
    val sourcePhotoType: String,
)

data class ExtractionResult(
    val fields: Map<String, ExtractedField> = emptyMap(),
)

data class SessionFields(
    val className: String,
    val clientName: String,
    val ownerName: String,
    val clientUnitId: String,
    val serialNo: String,
    val manufacturer: String,
    val model: String,
    val inspectionDate: String,
    val expiryDate: String,
    val equipType: String,
    val jobNo: String = "",
    val location: String = "",
    val capacity: String = "",
    val clientReference: String = "-",
    val lsd: String = "",
    val province: String = "",
    val basketMaxHeight: String = "",
    val basketMaxReach: String = "",
    val basketLength: String = "",
    val basketWidth: String = "",
    val basketHeight: String = "",
    val technicianId: String = "DEFAULT_TECH",
)

data class SessionResult(
    val raeq: String,
    val decision: String,
    val checklistPath: String,
    val certificatePath: String,
    val checklistResults: Map<String, String>,
    val insertedPhotoCount: Int = 0,
)

data class EquipmentCandidate(
    val raeq: String,
    val className: String,
    val clientUnitId: String,
    val serialNo: String,
    val matchStrength: String,
    val clientName: String = "",
    val manufacturer: String = "",
    val model: String = "",
)
