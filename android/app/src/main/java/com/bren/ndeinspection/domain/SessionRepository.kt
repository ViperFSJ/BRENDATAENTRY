package com.bren.ndeinspection.domain

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import com.bren.ndeinspection.data.AppDatabase
import com.bren.ndeinspection.data.ChecklistResultEntity
import com.bren.ndeinspection.ocr.PhotoOcr
import java.io.File
import java.io.FileOutputStream

class SessionRepository(
    private val context: Context,
    database: AppDatabase,
) {
    private val dao = database.dao()
    private val raeq = RaeqService(dao)
    private val ocr = PhotoOcr(context)

    fun listClasses(): List<String> = TemplateAssets.listClassNames(context.assets)

    suspend fun seedRaeqPool(
        technicianId: String = "DEFAULT_TECH",
        spec: String = "56400-56450",
    ) {
        raeq.addAvailableRaeqs(technicianId, "Mobile Technician", spec)
    }

    suspend fun extractFromPhotos(uris: List<Uri>): ExtractionResult = ocr.extractFromPhotos(uris)

    /** Copy picked/captured photos into app storage so URIs stay readable later. */
    fun persistPhotos(uris: List<Uri>): List<Uri> {
        if (uris.isEmpty()) return emptyList()
        val dir = File(context.filesDir, "persisted_photos").apply { mkdirs() }
        return uris.mapIndexedNotNull { index, uri ->
            try {
                val ext = guessExt(uri)
                val out = File(dir, "p_${System.currentTimeMillis()}_${index}.$ext")
                val ok = context.contentResolver.openInputStream(uri)?.use { input ->
                    FileOutputStream(out).use { output -> input.copyTo(output) }
                    true
                } ?: run {
                    val path = uri.path
                    if (!path.isNullOrBlank() && File(path).exists()) {
                        File(path).copyTo(out, overwrite = true)
                        true
                    } else false
                }
                if (ok && out.exists() && out.length() > 0) {
                    FileProvider.getUriForFile(
                        context,
                        "${context.packageName}.fileprovider",
                        out,
                    )
                } else null
            } catch (_: Exception) {
                null
            }
        }
    }

    fun checklistRows(className: String): List<ChecklistRow> =
        ChecklistXml.extractItemsForClass(context.assets, className)

    fun needsBasketFields(className: String): Boolean {
        val asset = TemplateAssets.findChecklistAsset(context.assets, className)
        val file = TemplateAssets.copyAssetToCache(context, asset, "probe_${className.replace(' ', '_')}.bin")
        return DocxFillers.templateHasBasketSection(file)
    }

    fun statusChoices(className: String): List<Pair<String, Boolean>> {
        val asset = TemplateAssets.findChecklistAsset(context.assets, className)
        val file = TemplateAssets.copyAssetToCache(context, asset, "status_${className.replace(' ', '_')}.bin")
        val choices = DocxFillers.readStatusChoices(file)
        return choices.ifEmpty {
            listOf("Requires review" to true, "Certification recommended" to false)
        }
    }

    suspend fun runSession(
        fields: SessionFields,
        checklistResults: Map<String, String>,
        photoUris: List<Uri>,
        forceNewEquipment: Boolean,
        fieldExtras: Map<String, String> = emptyMap(),
        confirmExisting: suspend (EquipmentCandidate) -> Boolean,
    ): SessionResult {
        seedRaeqPool(fields.technicianId)

        val (raeqId, decision) = raeq.identifyOrAssign(
            technicianId = fields.technicianId,
            className = fields.className,
            fields = fields,
            forceNew = forceNewEquipment,
            confirmExisting = confirmExisting,
        )

        var status = "Certification recommended"
        val hasRr = checklistResults.values.any { it.equals("RR", ignoreCase = true) }
        if (hasRr) {
            val choices = statusChoices(fields.className)
            status = choices.firstOrNull { it.second }?.first
                ?: choices.firstOrNull()?.first
                ?: "Requires review"
        }

        val outDir = File(context.filesDir, "outputs/${fields.className}/$raeqId").apply { mkdirs() }
        val checklistOut = File(outDir, "${raeqId}_checklist.docx")
        val certificateOut = File(outDir, "${raeqId}_certificate.docx")

        val checklistAsset = TemplateAssets.findChecklistAsset(context.assets, fields.className)
        val certAsset = TemplateAssets.findCertificateAsset(context.assets, fields.className)
        val checklistTemplate = TemplateAssets.copyAssetToCache(
            context,
            checklistAsset,
            "tpl_checklist_${fields.className.replace(' ', '_')}",
        )
        val certTemplate = TemplateAssets.copyAssetToCache(
            context,
            certAsset,
            "tpl_cert_${fields.className.replace(' ', '_')}",
        )

        val rows = checklistRows(fields.className)
        val finalStatus = if (hasRr) {
            // Prefer explicit UI-provided status stored in clientReference overflow? Use capacity unused — better: parameter
            status
        } else {
            "Certification recommended"
        }

        // Allow UI to override RR status by encoding in a dedicated map entry handled by overload below
        val resolvedStatus = checklistResults["__status__"]?.takeIf { it.isNotBlank() } ?: finalStatus
        val cleanResults = checklistResults.filterKeys { it != "__status__" }

        DocxFillers.fillChecklist(
            templateFile = checklistTemplate,
            outputFile = checklistOut,
            className = fields.className,
            rows = rows,
            resultsBySlug = cleanResults,
            fields = mapOf(
                "client_name" to fields.clientName,
                "owner_name" to fields.ownerName,
                "raeq" to raeqId,
                "job_no" to fields.jobNo,
                "equip_type" to fields.equipType,
                "location" to fields.location,
                "manufacturer" to fields.manufacturer,
                "model" to fields.model,
                "serial_no" to fields.serialNo,
                "client_unit_id" to fields.clientUnitId,
                "client_reference" to fields.clientReference,
                "capacity" to fields.capacity,
                "next_inspection_date" to fields.expiryDate,
                "status" to resolvedStatus,
                "inspection_date" to fields.inspectionDate,
                "inspection_type" to "Visual/MPI",
                "lsd" to fields.lsd,
                "province" to fields.province,
                "basket_max_height" to fields.basketMaxHeight,
                "basket_max_reach" to fields.basketMaxReach,
                "basket_length" to fields.basketLength,
                "basket_width" to fields.basketWidth,
                "basket_height" to fields.basketHeight,
            ) + fieldExtras,
        )

        val photoFiles = copyPhotosToCache(photoUris)
        if (photoUris.isNotEmpty() && photoFiles.isEmpty()) {
            // Keep going, but surface via inserted count 0 on result.
        }
        val inserted = if (photoFiles.isEmpty()) {
            0
        } else {
            PhotoEmbedder.insertPhotos(checklistOut, photoFiles)
        }

        DocxFillers.fillCertificate(
            templateFile = certTemplate,
            outputFile = certificateOut,
            fields = mapOf(
                "client_name" to fields.clientName,
                "raeq" to raeqId,
                "equip_type" to fields.equipType,
                "inspection_date" to fields.inspectionDate,
                "expiry_date" to fields.expiryDate,
                "manufacturer" to fields.manufacturer,
                "model" to fields.model,
                "serial_no" to fields.serialNo,
                "client_unit_id" to fields.clientUnitId,
                "inspector_name" to "Brennan Maier MT CGSB No.20220",
                "engineer_name" to "Shawn Santo, P.Eng.",
            ),
        )

        dao.upsertChecklistResults(
            cleanResults.map { (slug, result) ->
                ChecklistResultEntity(
                    raeq = raeqId,
                    className = fields.className,
                    labelSlug = slug,
                    result = result,
                )
            }
        )
        if (cleanResults.isNotEmpty()) {
            dao.deleteStaleChecklistResults(raeqId, fields.className, cleanResults.keys.toList())
        }

        raeq.markInspectionStarted(
            technicianId = fields.technicianId,
            raeq = raeqId,
            inspectionDate = fields.inspectionDate,
            className = fields.className,
        )

        return SessionResult(
            raeq = raeqId,
            decision = decision,
            checklistPath = checklistOut.absolutePath,
            certificatePath = certificateOut.absolutePath,
            checklistResults = cleanResults,
            insertedPhotoCount = inserted,
        )
    }

    private fun copyPhotosToCache(uris: List<Uri>): List<File> {
        val dir = File(context.filesDir, "session_photos_${System.currentTimeMillis()}").apply {
            mkdirs()
        }
        return uris.mapIndexedNotNull { index, uri ->
            try {
                val ext = guessExt(uri)
                val out = File(dir, "photo_${index + 1}.$ext")
                val copied = context.contentResolver.openInputStream(uri)?.use { input ->
                    FileOutputStream(out).use { output -> input.copyTo(output) }
                    true
                } ?: run {
                    // Fallback for file:// and some FileProvider edge cases
                    val path = uri.path
                    if (!path.isNullOrBlank()) {
                        val src = File(path)
                        if (src.exists()) {
                            src.copyTo(out, overwrite = true)
                            true
                        } else {
                            false
                        }
                    } else {
                        false
                    }
                }
                if (copied && out.exists() && out.length() > 0) out else null
            } catch (_: Exception) {
                null
            }
        }
    }

    private fun guessExt(uri: Uri): String {
        val name = (uri.lastPathSegment ?: uri.toString()).lowercase()
        val mime = runCatching { context.contentResolver.getType(uri) }.getOrNull().orEmpty().lowercase()
        return when {
            mime.contains("png") || name.endsWith(".png") -> "png"
            mime.contains("webp") || name.endsWith(".webp") -> "webp"
            mime.contains("gif") || name.endsWith(".gif") -> "gif"
            else -> "jpg"
        }
    }
}
