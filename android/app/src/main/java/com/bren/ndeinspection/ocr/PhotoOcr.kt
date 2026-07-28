package com.bren.ndeinspection.ocr

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import com.bren.ndeinspection.domain.ExtractedField
import com.bren.ndeinspection.domain.ExtractionResult
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.tasks.await
import java.io.File
import java.util.Locale

class PhotoOcr(private val context: Context) {
    private val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    suspend fun extractFromPhotos(uris: List<Uri>): ExtractionResult {
        if (uris.isEmpty()) return ExtractionResult()
        val snippets = mutableListOf<Pair<String, String>>()
        for (uri in uris) {
            val type = guessPhotoType(uri)
            val text = runOcr(uri)
            if (text.isNotBlank()) snippets += text to type
        }
        if (snippets.isEmpty()) return ExtractionResult()
        return parseFields(snippets)
    }

    suspend fun extractFromFiles(files: List<File>): ExtractionResult {
        val uris = files.map { Uri.fromFile(it) }
        return extractFromPhotos(uris)
    }

    private suspend fun runOcr(uri: Uri): String {
        return try {
            val image = InputImage.fromFilePath(context, uri)
            val result = recognizer.process(image).await()
            result.text.orEmpty()
        } catch (_: Exception) {
            // Fallback decode path
            try {
                context.contentResolver.openInputStream(uri)?.use { stream ->
                    val bmp = BitmapFactory.decodeStream(stream) ?: return ""
                    val image = InputImage.fromBitmap(bmp, 0)
                    recognizer.process(image).await().text.orEmpty()
                } ?: ""
            } catch (_: Exception) {
                ""
            }
        }
    }

    private fun guessPhotoType(uri: Uri): String {
        val name = (uri.lastPathSegment ?: uri.toString()).lowercase(Locale.US)
        return when {
            listOf("plate", "nameplate", "data_plate").any { it in name } -> "data_plate"
            listOf("unit", "decal", "id").any { it in name } -> "unit_id_decal"
            listOf("owner", "client").any { it in name } -> "owner_label"
            listOf("brand", "logo").any { it in name } -> "branding_sticker"
            else -> "unknown"
        }
    }

    private fun parseFields(snippets: List<Pair<String, String>>): ExtractionResult {
        val hits = mutableMapOf<String, MutableList<Pair<String, String>>>()
        fun add(field: String, value: String?, src: String) {
            val v = value?.trim().orEmpty()
            if (v.isEmpty()) return
            hits.getOrPut(field) { mutableListOf() }.add(v to src)
        }

        for ((text, src) in snippets) {
            add("serial_no", firstMatch(text, listOf(
                Regex("""\bserial\s*(?:no|number|#)?\s*[:\-]?\s*([A-Z0-9\-/]{4,})""", RegexOption.IGNORE_CASE),
                Regex("""\bS\/N\s*[:\-]?\s*([A-Z0-9\-/]{4,})""", RegexOption.IGNORE_CASE),
            )), src)
            add("client_unit_id", firstMatch(text, listOf(
                Regex("""\bunit\s*(?:id|no|number|#)?\s*[:\-]?\s*([A-Z0-9\-/]{3,})""", RegexOption.IGNORE_CASE),
                Regex("""\basset\s*(?:id|no|number|#)?\s*[:\-]?\s*([A-Z0-9\-/]{3,})""", RegexOption.IGNORE_CASE),
            )), src)
            add("manufacturer", firstMatch(text, listOf(
                Regex("""\bmanufacturer\s*[:\-]?\s*([A-Za-z0-9 \-]{2,})""", RegexOption.IGNORE_CASE),
            ))?.lineSequence()?.firstOrNull(), src)
            add("model", firstMatch(text, listOf(
                Regex("""\bmodel\s*(?:no|number|#)?\s*[:\-]?\s*([A-Za-z0-9 \-/]{2,})""", RegexOption.IGNORE_CASE),
            ))?.lineSequence()?.firstOrNull(), src)
            add("owner_name", firstMatch(text, listOf(
                Regex("""\bowner\s*[:\-]?\s*([A-Za-z0-9 &\-.,]{3,})""", RegexOption.IGNORE_CASE),
            ))?.lineSequence()?.firstOrNull(), src)
            add("client_name", firstMatch(text, listOf(
                Regex("""\bclient\s*[:\-]?\s*([A-Za-z0-9 &\-.,]{3,})""", RegexOption.IGNORE_CASE),
            ))?.lineSequence()?.firstOrNull(), src)
            add("capacity", firstMatch(text, listOf(
                Regex("""\bcapacity\s*[:\-]?\s*([A-Za-z0-9 \-/.]{2,})""", RegexOption.IGNORE_CASE),
            ))?.lineSequence()?.firstOrNull(), src)
        }

        val combined = snippets.joinToString("\n") { it.first }
        val equip = Regex(
            """\b(telescopic boom lift|scissor lift|bucket truck|manbasket|mobile crane|overhead crane|jib crane|forklift)\b""",
            RegexOption.IGNORE_CASE,
        ).find(combined)?.groupValues?.getOrNull(1)
        if (!equip.isNullOrBlank()) {
            hits.getOrPut("equip_type") { mutableListOf() }
                .add(equip.replaceFirstChar { if (it.isLowerCase()) it.titlecase(Locale.US) else it.toString() } to "unknown")
        }

        fun pick(field: String, preferred: String): ExtractedField? {
            val list = hits[field] ?: return null
            val preferredHit = list.firstOrNull { it.second == preferred } ?: list.firstOrNull() ?: return null
            return ExtractedField(preferredHit.first.trim(), 0.75f, preferredHit.second)
        }

        val fields = listOfNotNull(
            pick("serial_no", "data_plate")?.let { "serial_no" to it },
            pick("client_unit_id", "unit_id_decal")?.let { "client_unit_id" to it },
            pick("manufacturer", "data_plate")?.let { "manufacturer" to it },
            pick("model", "data_plate")?.let { "model" to it },
            pick("owner_name", "owner_label")?.let { "owner_name" to it },
            pick("client_name", "owner_label")?.let { "client_name" to it },
            pick("equip_type", "unknown")?.let { "equip_type" to it },
            pick("capacity", "data_plate")?.let { "capacity" to it },
        ).toMap()

        return ExtractionResult(fields)
    }

    private fun firstMatch(text: String, patterns: List<Regex>): String? {
        for (p in patterns) {
            val m = p.find(text) ?: continue
            val g = m.groupValues.getOrNull(1)?.trim()
            if (!g.isNullOrEmpty()) return g
        }
        return null
    }
}
