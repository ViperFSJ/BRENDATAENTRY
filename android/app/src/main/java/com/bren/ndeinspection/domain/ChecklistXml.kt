package com.bren.ndeinspection.domain

import android.content.res.AssetManager
import org.json.JSONArray
import org.w3c.dom.Element
import org.w3c.dom.Node
import java.io.InputStream
import javax.xml.parsers.DocumentBuilderFactory

object ChecklistXml {
    private const val GENERAL = "General"

    fun extractItemsForClass(assets: AssetManager, className: String): List<ChecklistRow> {
        if (className == GENERAL) {
            val labels = loadGeneralManifest(assets)
            val (slugs, _) = LabelSlug.makeLabelSlugs(labels)
            return labels.mapIndexed { i, label -> ChecklistRow(i, label, slugs[i]) }
        }
        val xmlAsset = TemplateAssets.findChecklistXmlAsset(assets, className)
            ?: error("No Checklist*.xml for $className")
        assets.open(xmlAsset).use { return extractFromXml(it) }
    }

    private fun loadGeneralManifest(assets: AssetManager): List<String> {
        val text = assets.open(TemplateAssets.generalManifestAsset()).bufferedReader().readText()
        val arr = JSONArray(text)
        return (0 until arr.length()).map { arr.getString(it) }
    }

    fun extractFromXml(input: InputStream): List<ChecklistRow> {
        val factory = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
        val doc = factory.newDocumentBuilder().parse(input)
        val root = doc.documentElement

        var checklistTable: Element? = null
        var headerRow: Element? = null
        for (tbl in descendants(root, "tbl")) {
            for (tr in tableRows(tbl)) {
                val cells = directChildren(tr, "tc").map { cellText(it) }
                val joined = cells.joinToString(" | ").lowercase()
                if ("item" in joined && "type of inspection" in joined &&
                    "comments" in joined && "result" in joined
                ) {
                    checklistTable = tbl
                    headerRow = tr
                    break
                }
            }
            if (checklistTable != null) break
        }
        requireNotNull(checklistTable) { "Checklist table not found" }
        requireNotNull(headerRow)

        val headerText = directChildren(headerRow, "tc").map { cellText(it) }
        val itemCol = headerText.indexOfFirst { it.equals("Item", ignoreCase = true) }
            .takeIf { it >= 0 } ?: error("Item column missing: $headerText")

        val labels = mutableListOf<String>()
        var pastHeader = false
        for (tr in tableRows(checklistTable)) {
            if (!pastHeader) {
                if (tr === headerRow) pastHeader = true
                continue
            }
            val tcs = directChildren(tr, "tc")
            if (itemCol >= tcs.size) continue
            val item = cellText(tcs[itemCol])
            if (item.isBlank() || item.equals("Item", ignoreCase = true)) continue
            labels += item
        }

        val (slugs, _) = LabelSlug.makeLabelSlugs(labels)
        return labels.mapIndexed { i, label -> ChecklistRow(i, label, slugs[i]) }
    }

    private fun localName(node: Node): String {
        val n = node.localName
        if (!n.isNullOrBlank()) return n
        val name = node.nodeName
        return name.substringAfter(':', name)
    }

    private fun descendants(root: Element, local: String): List<Element> {
        val out = mutableListOf<Element>()
        val all = root.getElementsByTagName("*")
        for (i in 0 until all.length) {
            val el = all.item(i) as? Element ?: continue
            if (localName(el) == local) out += el
        }
        return out
    }

    private fun directChildren(parent: Element, local: String): List<Element> {
        val out = mutableListOf<Element>()
        val children = parent.childNodes
        for (i in 0 until children.length) {
            val n = children.item(i)
            if (n is Element && localName(n) == local) out += n
        }
        return out
    }

    /** Rows belonging to this table, excluding nested tables. */
    private fun tableRows(tbl: Element): List<Element> {
        val out = mutableListOf<Element>()
        fun walk(node: Node) {
            if (node is Element) {
                if (localName(node) == "tr") {
                    out += node
                    return
                }
                if (node !== tbl && localName(node) == "tbl") return
            }
            val children = node.childNodes
            for (i in 0 until children.length) walk(children.item(i))
        }
        walk(tbl)
        return out
    }

    private fun cellText(tc: Element): String {
        val parts = mutableListOf<String>()
        val all = tc.getElementsByTagName("*")
        for (i in 0 until all.length) {
            val el = all.item(i) as? Element ?: continue
            if (localName(el) == "t") {
                el.textContent?.let { parts += it }
            }
        }
        return parts.joinToString("").replace(Regex("\\s+"), " ").trim()
    }
}
