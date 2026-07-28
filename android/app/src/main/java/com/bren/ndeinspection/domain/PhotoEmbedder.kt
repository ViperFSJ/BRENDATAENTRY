package com.bren.ndeinspection.domain

import org.w3c.dom.Element
import java.io.File

/**
 * Inserts session photos into checklist drawing placeholders by rewriting
 * a:blip r:embed relationships and media parts (ported from Python embedder).
 */
object PhotoEmbedder {
    fun insertPhotos(checklistDocx: File, photos: List<File>): Int {
        if (photos.isEmpty()) return 0
        val entries = DocxXml.readZipEntries(checklistDocx)
        val docName = entries.keys.firstOrNull { it.endsWith("word/document.xml") } ?: return 0
        val relsName = entries.keys.firstOrNull { it.endsWith("word/_rels/document.xml.rels") } ?: return 0

        val document = DocxXml.parseDocument(entries.getValue(docName))
        val rels = DocxXml.parseDocument(entries.getValue(relsName))
        val blips = DocxXml.descendantElements(document.documentElement, "blip")
        if (blips.isEmpty()) return 0

        val nFill = minOf(blips.size, photos.size)
        val existingIds = DocxXml.descendantElements(rels.documentElement, "Relationship")
            .mapNotNull { it.getAttribute("Id")?.takeIf { id -> id.isNotBlank() } }
            .toMutableSet()

        var inserted = 0
        for (i in 0 until nFill) {
            val photo = photos[i]
            if (!photo.exists()) continue
            val blip = blips[i]
            val embedKey = blip.attributes?.let { attrs ->
                (0 until attrs.length).map { attrs.item(it) }
                    .firstOrNull { it.nodeName.endsWith("embed") || it.localName == "embed" }
                    ?.nodeName
            } ?: "r:embed"
            val oldRid = blip.getAttribute(embedKey).ifBlank {
                blip.getAttributeNS(
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
                    "embed",
                )
            }

            if (i == 0 && oldRid.isNotBlank()) {
                val target = DocxXml.descendantElements(rels.documentElement, "Relationship")
                    .firstOrNull { it.getAttribute("Id") == oldRid }
                    ?.getAttribute("Target")
                if (!target.isNullOrBlank()) {
                    val mediaName = "word/" + target.replace('\\', '/').trimStart('/')
                    entries[mediaName] = photo.readBytes()
                    inserted++
                    continue
                }
            }

            val ext = photo.extension.ifBlank { "jpg" }
            val mediaName = "word/media/figure_auto_${i + 1}.$ext"
            entries[mediaName] = photo.readBytes()
            val rid = nextRid(existingIds, "rIdAutoPhoto${i + 1}")
            appendRelationship(rels, rid, "media/${File(mediaName).name}")
            if (blip.hasAttribute(embedKey)) {
                blip.setAttribute(embedKey, rid)
            } else {
                blip.setAttributeNS(
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
                    "r:embed",
                    rid,
                )
            }
            inserted++
        }

        entries[docName] = DocxXml.documentBytes(document)
        entries[relsName] = DocxXml.documentBytes(rels)
        DocxXml.writeZipEntries(checklistDocx, entries)
        return inserted
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
