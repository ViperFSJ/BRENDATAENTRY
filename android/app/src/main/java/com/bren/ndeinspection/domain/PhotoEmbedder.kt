package com.bren.ndeinspection.domain

import org.w3c.dom.Element
import java.io.File

/**
 * Inserts session photos into checklist drawing placeholders by rewriting
 * a:blip relationships and media parts.
 *
 * Important: never overwrite an existing media part with bytes of a different
 * image type (e.g. JPEG into image1.png) — Word will show a blank figure.
 */
object PhotoEmbedder {
    fun insertPhotos(checklistDocx: File, photos: List<File>): Int {
        val usable = photos.filter { it.exists() && it.length() > 0 }
        if (usable.isEmpty()) return 0

        val entries = DocxXml.readZipEntries(checklistDocx)
        val docName = entries.keys.firstOrNull { it.endsWith("word/document.xml") } ?: return 0
        val relsName = entries.keys.firstOrNull { it.endsWith("word/_rels/document.xml.rels") } ?: return 0

        val document = DocxXml.parseDocument(entries.getValue(docName))
        val rels = DocxXml.parseDocument(entries.getValue(relsName))
        val blips = DocxXml.descendantElements(document.documentElement, "blip")
        if (blips.isEmpty()) return 0

        val existingIds = DocxXml.descendantElements(rels.documentElement, "Relationship")
            .mapNotNull { it.getAttribute("Id")?.takeIf { id -> id.isNotBlank() } }
            .toMutableSet()

        var inserted = 0
        val nFill = minOf(blips.size, usable.size)
        for (i in 0 until nFill) {
            val photo = usable[i]
            val ext = normalizeExt(photo)
            val mediaPart = "word/media/inspection_photo_${i + 1}.$ext"
            entries[mediaPart] = photo.readBytes()

            val rid = nextRid(existingIds, "rIdInspectionPhoto${i + 1}")
            appendRelationship(rels, rid, "media/${File(mediaPart).name}")

            val blip = blips[i]
            setEmbed(blip, rid)
            inserted++
        }

        // Ensure Content_Types declares image defaults used by inserted media.
        val ctName = "[Content_Types].xml"
        if (ctName in entries) {
            entries[ctName] = ensureImageContentTypes(entries.getValue(ctName))
        }

        entries[docName] = DocxXml.documentBytes(document)
        entries[relsName] = DocxXml.documentBytes(rels)
        DocxXml.writeZipEntries(checklistDocx, entries)
        return inserted
    }

    private fun normalizeExt(photo: File): String {
        val ext = photo.extension.lowercase().ifBlank { "jpg" }
        return when (ext) {
            "jpeg" -> "jpg"
            "png", "jpg", "webp", "gif" -> ext
            else -> "jpg"
        }
    }

    private fun setEmbed(blip: Element, rid: String) {
        val relNs = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        val attrs = blip.attributes
        var embedName: String? = null
        if (attrs != null) {
            for (i in 0 until attrs.length) {
                val attr = attrs.item(i)
                if (attr.localName == "embed" || attr.nodeName.endsWith(":embed") || attr.nodeName == "embed") {
                    embedName = attr.nodeName
                    break
                }
            }
        }
        if (embedName != null) {
            blip.setAttribute(embedName, rid)
        } else {
            blip.setAttributeNS(relNs, "r:embed", rid)
        }
    }

    private fun ensureImageContentTypes(bytes: ByteArray): ByteArray {
        var xml = bytes.toString(Charsets.UTF_8)
        fun ensure(ext: String, mime: String) {
            if (!xml.contains("Extension=\"$ext\"", ignoreCase = true)) {
                xml = xml.replace(
                    "<Types",
                    "<Types",
                )
                // Insert defaults after opening Types tag.
                val marker = Regex("<Types[^>]*>").find(xml)?.value ?: return
                xml = xml.replace(
                    marker,
                    "$marker\n  <Default Extension=\"$ext\" ContentType=\"$mime\"/>",
                )
            }
        }
        ensure("jpg", "image/jpeg")
        ensure("jpeg", "image/jpeg")
        ensure("png", "image/png")
        ensure("webp", "image/webp")
        ensure("gif", "image/gif")
        return xml.toByteArray(Charsets.UTF_8)
    }

    private fun nextRid(existing: MutableSet<String>, base: String): String {
        var rid = base
        var k = 1
        while (rid in existing) {
            k++
            rid = "${base}_$k"
        }
        existing += rid
        return rid
    }

    private fun appendRelationship(relsDoc: org.w3c.dom.Document, rid: String, target: String) {
        val root = relsDoc.documentElement
        val ns = root.namespaceURI
        val rel: Element = if (ns.isNullOrBlank()) {
            relsDoc.createElement("Relationship")
        } else {
            relsDoc.createElementNS(ns, "Relationship")
        }
        rel.setAttribute("Id", rid)
        rel.setAttribute(
            "Type",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
        )
        rel.setAttribute("Target", target)
        root.appendChild(rel)
    }
}
