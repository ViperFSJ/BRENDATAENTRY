package com.bren.ndeinspection.domain

import org.w3c.dom.Document
import org.w3c.dom.Element
import org.w3c.dom.Node
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

object DocxFillers {
    private data class ChecklistTable(
        val table: Element,
        val rows: List<Element>,
        val headerIndex: Int,
        val itemColumn: Int,
        val resultsColumn: Int,
    )

    private data class StatusDropdown(
        val choices: List<Pair<String, Boolean>>,
        val mentionsStatus: Boolean,
        val hasKnownStatusChoice: Boolean,
    )

    fun fillChecklist(
        templateFile: File,
        outputFile: File,
        className: String,
        rows: List<ChecklistRow>,
        resultsBySlug: Map<String, String>,
        fields: Map<String, String>,
    ) {
        val entries = DocxXml.readZipEntries(templateFile)
        val documentEntry = findDocumentEntry(entries)
        val document = DocxXml.parseDocument(entries.getValue(documentEntry))
        val root = document.documentElement
        val checklist = findChecklistTable(root)

        replaceFieldTokens(document, fields)
        fillReportDetails(root, fields, checklist.table)
        fillProvinceCheckboxes(root, fields)
        fillChecklistResults(checklist, className, rows, resultsBySlug)
        entries[documentEntry] = DocxXml.documentBytes(document)

        // RAEQ placeholders commonly live in a header rather than document.xml.
        for (entryName in entries.keys.toList()) {
            if (!entryName.startsWith("word/header") || !entryName.endsWith(".xml")) continue
            val header = runCatching { DocxXml.parseDocument(entries.getValue(entryName)) }.getOrNull()
                ?: continue
            replaceFieldTokens(header, fields)
            entries[entryName] = DocxXml.documentBytes(header)
        }

        convertPackageToDocument(entries)
        DocxXml.writeZipEntries(outputFile, entries)
    }

    fun fillCertificate(
        templateFile: File,
        outputFile: File,
        fields: Map<String, String>,
    ) {
        val entries = DocxXml.readZipEntries(templateFile)
        val documentEntry = findDocumentEntry(entries)
        val document = DocxXml.parseDocument(entries.getValue(documentEntry))
        val root = document.documentElement

        val labelsByField = linkedMapOf(
            "client_name" to setOf("client"),
            "raeq" to setOf("raeq", "rae no", "rae number"),
            "equip_type" to setOf("equipment type", "equip type", "type"),
            "inspection_date" to setOf("inspection date"),
            "expiry_date" to setOf("expiry date", "expiry"),
            "manufacturer" to setOf("manufacturer"),
            "model" to setOf("model"),
            "serial_no" to setOf("serial number", "serial no", "serial"),
            "client_unit_id" to setOf("unit id", "unit no", "client unit"),
            "inspector_name" to setOf("inspector"),
            "engineer_name" to setOf("engineer", "engineers", "engineer s"),
        )

        replaceFieldTokens(document, fields)
        for ((fieldKey, aliases) in labelsByField) {
            if (!fields.containsKey(fieldKey)) continue
            val target = findValueContainerForLabel(root, aliases) ?: continue
            val rawValue = fields[fieldKey].orEmpty().trim()
            if (fieldKey == "inspection_date" || fieldKey == "expiry_date") {
                if (rawValue.isBlank()) continue
                val parsed = DocxXml.parseFlexibleDate(rawValue)
                if (parsed != null) {
                    val placeholder = DocxXml.cellText(target)
                    setContentControlDate(target, parsed)
                    DocxXml.setContainerText(
                        target,
                        DocxXml.formatDateForPlaceholder(parsed, placeholder),
                    )
                } else {
                    DocxXml.setContainerText(target, rawValue)
                }
            } else {
                DocxXml.setContainerText(target, rawValue.ifBlank { "-" })
            }
        }

        entries[documentEntry] = DocxXml.documentBytes(document)
        convertPackageToDocument(entries)
        DocxXml.writeZipEntries(outputFile, entries)
    }

    fun templateHasBasketSection(templateFile: File): Boolean {
        val entries = DocxXml.readZipEntries(templateFile)
        val document = DocxXml.parseDocument(entries.getValue(findDocumentEntry(entries)))
        val text = textElements(document.documentElement)
            .joinToString(" ") { it.textContent.orEmpty().trim().lowercase(Locale.US) }
        if (!text.contains("basket information")) return false
        val dimensions = listOf("maximum height", "maximum reach", "length", "width", "height")
        return dimensions.count(text::contains) >= 2
    }

    fun readStatusChoices(templateFile: File): List<Pair<String, Boolean>> {
        val entries = DocxXml.readZipEntries(templateFile)
        val document = DocxXml.parseDocument(entries.getValue(findDocumentEntry(entries)))
        val dropdowns = mutableListOf<StatusDropdown>()

        for (sdt in elements(document.documentElement, "sdt")) {
            val properties = elements(sdt, "sdtPr").firstOrNull() ?: continue
            val dropdown = elements(properties, "dropDownList").firstOrNull() ?: continue
            val labels = elements(dropdown, "listItem").mapNotNull { item ->
                (attribute(item, "displayText").ifBlank { attribute(item, "value") })
                    .trim()
                    .takeIf(String::isNotEmpty)
            }
            if (labels.isEmpty()) continue

            val defaultIndex = labels.indexOfFirst {
                val normalized = normalizeLabel(it)
                normalized != "choose an item" && normalized != "choose item"
            }.takeIf { it >= 0 } ?: 0
            val descriptor = DocxXml.cellText(properties).lowercase(Locale.US) + " " +
                elements(properties, "tag").joinToString(" ") { attribute(it, "val") } + " " +
                elements(properties, "alias").joinToString(" ") { attribute(it, "val") }
            val normalizedLabels = labels.map(::normalizeLabel)
            dropdowns += StatusDropdown(
                choices = labels.mapIndexed { index, label -> label to (index == defaultIndex) },
                mentionsStatus = descriptor.contains("status", ignoreCase = true),
                hasKnownStatusChoice = normalizedLabels.any {
                    it == "requires review" || it == "certification recommended"
                },
            )
        }

        return dropdowns.firstOrNull { it.mentionsStatus }?.choices
            ?: dropdowns.firstOrNull { it.hasKnownStatusChoice }?.choices
            ?: dropdowns.singleOrNull()?.choices
            ?: emptyList()
    }

    private fun fillChecklistResults(
        checklist: ChecklistTable,
        className: String,
        expectedRows: List<ChecklistRow>,
        resultsBySlug: Map<String, String>,
    ) {
        val dataRows = checklist.rows.drop(checklist.headerIndex + 1)
        if (className.equals("General", ignoreCase = true)) {
            var expectedIndex = 0
            for (tableRow in dataRows) {
                if (expectedIndex >= expectedRows.size) break
                val containers = rowValueContainers(tableRow)
                if (maxOf(checklist.itemColumn, checklist.resultsColumn) >= containers.size) continue
                if (DocxXml.cellText(containers[checklist.itemColumn])
                        .equals("Item", ignoreCase = true)
                ) {
                    continue
                }
                val slug = expectedRows[expectedIndex++].labelSlug
                val result = resultsBySlug[slug] ?: continue
                DocxXml.setContainerText(containers[checklist.resultsColumn], result)
            }
            return
        }

        val slugsByLabel = linkedMapOf<String, MutableList<String>>()
        for (row in expectedRows) {
            val label = normalizeWhitespace(row.itemLabel)
            slugsByLabel.getOrPut(label) { mutableListOf() }.add(row.labelSlug)
        }
        val consumedByLabel = mutableMapOf<String, Int>()
        for (tableRow in dataRows) {
            val containers = rowValueContainers(tableRow)
            if (maxOf(checklist.itemColumn, checklist.resultsColumn) >= containers.size) continue
            val itemText = normalizeWhitespace(DocxXml.cellText(containers[checklist.itemColumn]))
            if (itemText.isBlank() || itemText.equals("Item", ignoreCase = true)) continue
            val slugs = slugsByLabel[itemText] ?: continue
            val consumed = consumedByLabel[itemText] ?: 0
            if (consumed >= slugs.size) continue
            consumedByLabel[itemText] = consumed + 1
            val result = resultsBySlug[slugs[consumed]] ?: continue
            DocxXml.setContainerText(containers[checklist.resultsColumn], result)
        }
    }

    private fun fillProvinceCheckboxes(root: Element, fields: Map<String, String>) {
        val selected = parseProvinceSelections(fields)
        if (selected.boxes.isEmpty() && selected.otherText.isBlank()) return

        val parentMap = HashMap<Node, Node>()
        fun indexParents(node: Node) {
            val children = node.childNodes
            for (i in 0 until children.length) {
                val child = children.item(i)
                parentMap[child] = node
                indexParents(child)
            }
        }
        indexParents(root)

        val w14 = "http://schemas.microsoft.com/office/word/2010/wordml"
        val wNs = DocxXml.WORD_NAMESPACE

        for (sdt in elements(root, "sdt")) {
            if (elements(sdt, "checkbox").isEmpty()) continue
            val label = checkboxLabel(sdt, parentMap).trim()
            val key = normalizeProvinceCheckboxLabel(label) ?: continue
            val shouldCheck = when (key) {
                "OTHER" -> selected.otherText.isNotBlank() || "OTHER" in selected.boxes
                else -> key in selected.boxes
            }
            setWordCheckbox(sdt, checked = shouldCheck, w14 = w14, wNs = wNs)
            if (key == "OTHER" && selected.otherText.isNotBlank()) {
                fillOtherProvincePlaceholder(sdt, parentMap, selected.otherText)
            }
        }
    }

    private data class ProvinceSelection(
        val boxes: Set<String>,
        val otherText: String,
    )

    private fun parseProvinceSelections(fields: Map<String, String>): ProvinceSelection {
        val raw = fields["provinces"].orEmpty()
        val tokens = raw.split(',', ';', ' ')
            .map { it.trim().uppercase(Locale.US) }
            .filter { it.isNotEmpty() }
            .toMutableList()
        // Back-compat: single province field
        val single = fields["province"].orEmpty().trim().uppercase(Locale.US)
        if (single.isNotEmpty() && single !in tokens) tokens += single

        val boxes = linkedSetOf<String>()
        val otherParts = mutableListOf<String>()
        for (token in tokens) {
            when (token) {
                "BC" -> boxes += "BC"
                "AB" -> boxes += "AB"
                "SK" -> boxes += "SK"
                "NU", "NT", "NU/NT", "NT/NU" -> boxes += "NU/NT"
                "OTHER" -> boxes += "OTHER"
                else -> {
                    boxes += "OTHER"
                    otherParts += token
                }
            }
        }
        val explicitOther = fields["province_other"].orEmpty().trim().uppercase(Locale.US)
        if (explicitOther.isNotEmpty()) {
            boxes += "OTHER"
            otherParts += explicitOther.split(',', ';', ' ').map { it.trim() }.filter { it.isNotEmpty() }
        }
        return ProvinceSelection(
            boxes = boxes,
            otherText = otherParts.distinct().joinToString(", "),
        )
    }

    private fun normalizeProvinceCheckboxLabel(label: String): String? {
        val n = label.replace(Regex("\\s+"), " ").trim().uppercase(Locale.US)
        return when {
            n == "BC" -> "BC"
            n == "AB" -> "AB"
            n == "SK" -> "SK"
            n == "NU/NT" || n == "NU/N T" || n.startsWith("NU/") -> "NU/NT"
            n.startsWith("OTHER") -> "OTHER"
            else -> null
        }
    }

    private fun checkboxLabel(sdt: Element, parentMap: Map<Node, Node>): String {
        var para: Node? = sdt
        while (para != null && (para !is Element || DocxXml.localName(para) != "p")) {
            para = parentMap[para]
        }
        if (para !is Element) return ""
        var after = false
        val parts = mutableListOf<String>()
        val children = para.childNodes
        for (i in 0 until children.length) {
            val child = children.item(i)
            if (child === sdt) {
                after = true
                continue
            }
            if (!after || child !is Element) continue
            for (t in elements(child, "t")) {
                val text = t.textContent.orEmpty()
                if (text.isNotEmpty()) parts += text
            }
        }
        return parts.joinToString("")
    }

    private fun setWordCheckbox(sdt: Element, checked: Boolean, w14: String, wNs: String) {
        val checkbox = elements(sdt, "checkbox").firstOrNull() ?: return
        val checkedNode = elements(checkbox, "checked").firstOrNull()
            ?: sdt.ownerDocument.createElementNS(w14, "w14:checked").also { created ->
                checkbox.insertBefore(created, checkbox.firstChild)
            }
        checkedNode.setAttributeNS(w14, "w14:val", if (checked) "1" else "0")

        val stateNode = elements(checkbox, if (checked) "checkedState" else "uncheckedState").firstOrNull()
        val stateVal = stateNode?.getAttributeNS(w14, "val")
            ?.takeIf { it.isNotBlank() }
            ?: if (checked) "00FE" else "006F"
        val font = stateNode?.getAttributeNS(w14, "font")?.takeIf { it.isNotBlank() } ?: "Wingdings"
        val symChar = if (stateVal.length == 4) "F$stateVal" else stateVal

        // Update visible Wingdings symbol inside sdtContent.
        for (sym in elements(sdt, "sym")) {
            sym.setAttributeNS(wNs, "w:font", font)
            sym.setAttributeNS(wNs, "w:char", symChar)
        }
    }

    private fun fillOtherProvincePlaceholder(
        otherSdt: Element,
        parentMap: Map<Node, Node>,
        otherText: String,
    ) {
        var tr: Node? = otherSdt
        while (tr != null && (tr !is Element || DocxXml.localName(tr) != "tr")) {
            tr = parentMap[tr]
        }
        if (tr !is Element) return
        for (t in elements(tr, "t")) {
            val cur = t.textContent.orEmpty().trim()
            if (cur.equals("XX", ignoreCase = true) || cur == "xx") {
                t.textContent = otherText
                return
            }
        }
    }

    private fun fillReportDetails(
        root: Element,
        fields: Map<String, String>,
        checklistTable: Element,
    ) {
        val labelsToFields = mutableMapOf(
            "client" to "client_name",
            "client name" to "client_name",
            "owner" to "owner_name",
            "owner name" to "owner_name",
            "raeq" to "raeq",
            "rae no" to "raeq",
            "rae number" to "raeq",
            "job" to "job_no",
            "job no" to "job_no",
            "job number" to "job_no",
            "equipment type" to "equip_type",
            "equip type" to "equip_type",
            "location" to "location",
            "manufacturer" to "manufacturer",
            "model" to "model",
            "serial" to "serial_no",
            "serial no" to "serial_no",
            "serial number" to "serial_no",
            "unit" to "client_unit_id",
            "unit id" to "client_unit_id",
            "unit no" to "client_unit_id",
            "client unit" to "client_unit_id",
            "client reference" to "client_reference",
            "capacity" to "capacity",
            "province" to "province",
            "lsd" to "lsd",
            "status" to "status",
            "inspection date" to "inspection_date",
            "next inspection" to "next_inspection_date",
            "next inspection date" to "next_inspection_date",
            "inspection type" to "inspection_type",
            "maximum height" to "basket_max_height",
            "maximum reach" to "basket_max_reach",
            "length" to "basket_length",
            "width" to "basket_width",
            "height" to "basket_height",
        )
        for (key in fields.keys.filter { it.startsWith("basket_") }) {
            labelsToFields.putIfAbsent(normalizeLabel(key.removePrefix("basket_")), key)
            labelsToFields.putIfAbsent(normalizeLabel(key), key)
        }

        for (row in elements(root, "tr")) {
            if (isInside(row, checklistTable)) continue
            val containers = rowValueContainers(row)
            if (containers.isEmpty()) continue
            val labels = containers.map { normalizeLabel(DocxXml.cellText(it)) }
            for (index in labels.indices) {
                val label = labels[index]
                // Template uses "LSD:" as the row label; also accept plain "lsd".
                val isLsdRow = label == "lsd" || label == "lsd:" || label.startsWith("lsd")
                if (isLsdRow) {
                    val lsdValue = fields["lsd"]?.trim().orEmpty()
                    // Province marks go on the BC/AB/SK/... checkbox row, not this LSD: cell.
                    if (lsdValue.isNotEmpty() && index + 2 < containers.size) {
                        DocxXml.setContainerText(containers[index + 2], lsdValue)
                    } else if (lsdValue.isNotEmpty() && index + 1 < containers.size) {
                        DocxXml.setContainerText(containers[index + 1], lsdValue)
                    }
                    continue
                }

                val fieldKey = labelsToFields[label] ?: continue
                val rawValue = fields[fieldKey]?.trim().orEmpty()
                if (rawValue.isBlank()) continue
                if (index + 1 >= containers.size) continue
                val target = containers[index + 1]
                val value = if (fieldKey == "inspection_date" ||
                    fieldKey == "next_inspection_date"
                ) {
                    DocxXml.parseFlexibleDate(rawValue)?.let {
                        DocxXml.formatDateForPlaceholder(it, DocxXml.cellText(target))
                    } ?: rawValue
                } else {
                    rawValue
                }
                DocxXml.setContainerText(target, value)
            }
        }
    }

    private fun findChecklistTable(root: Element): ChecklistTable {
        for (table in elements(root, "tbl")) {
            val rows = tableRows(table)
            for ((headerIndex, row) in rows.withIndex()) {
                val cells = rowValueContainers(row).map { DocxXml.cellText(it) }
                val normalized = cells.map(::normalizeLabel)
                val itemColumn = normalized.indexOfFirst { it == "item" }
                val typeFound = normalized.any { it.contains("type of inspection") }
                val resultsColumn = normalized.indexOfFirst {
                    it == "results" || it == "inspection results" || it.contains("result")
                }
                val commentsFound = normalized.any { it.contains("comments") }
                if (itemColumn >= 0 && typeFound && resultsColumn >= 0 && commentsFound) {
                    return ChecklistTable(
                        table = table,
                        rows = rows,
                        headerIndex = headerIndex,
                        itemColumn = itemColumn,
                        resultsColumn = resultsColumn,
                    )
                }
            }
        }
        error("Could not locate checklist table header in word/document.xml")
    }

    private fun findValueContainerForLabel(
        root: Element,
        aliases: Set<String>,
    ): Element? {
        val normalizedAliases = aliases.map(::normalizeLabel).toSet()
        for (row in elements(root, "tr")) {
            val containers = rowValueContainers(row)
            for (index in containers.indices) {
                if (normalizeLabel(DocxXml.cellText(containers[index])) !in normalizedAliases) {
                    continue
                }
                var blankCell: Element? = null
                for (nextIndex in index + 1 until containers.size) {
                    val candidate = containers[nextIndex]
                    if (DocxXml.localName(candidate) == "sdt") return candidate
                    if (DocxXml.localName(candidate) == "tc") {
                        if (blankCell == null) blankCell = candidate
                        if (elements(candidate, "sdt").isNotEmpty() ||
                            DocxXml.cellText(candidate).isNotBlank()
                        ) {
                            return candidate
                        }
                    }
                }
                if (blankCell != null) return blankCell
            }
        }
        return null
    }

    private fun replaceFieldTokens(document: Document, fields: Map<String, String>) {
        if (fields.isEmpty()) return
        val normalizedFields = fields.entries.associate { normalizeFieldKey(it.key) to it.value }
        // Use [{]/[}] — Android ICU rejects \{ / \} escapes ("Syntax error in regexp pattern").
        val tokenPattern = Regex("""[{][{]\s*([A-Za-z0-9_.\- ]+)\s*[}][}]""")
        val textNodes = textElements(document.documentElement)
        for (textNode in textNodes) {
            var text = textNode.textContent.orEmpty()
            text = tokenPattern.replace(text) { match ->
                normalizedFields[normalizeFieldKey(match.groupValues[1])] ?: match.value
            }
            val raeq = fields["raeq"].orEmpty().trim()
            if (raeq.isNotEmpty()) {
                text = text.replace("RAEQ######", raeq)
            }
            textNode.textContent = text
        }

        // Some Word versions split RAEQ###### into "RAEQ#" and a run of hashes.
        val raeq = fields["raeq"].orEmpty().trim()
        if (raeq.isNotEmpty()) {
            for (index in textNodes.indices) {
                val text = textNodes[index].textContent.orEmpty()
                if (!text.contains("RAEQ#")) continue
                textNodes[index].textContent = text.replace("RAEQ#", raeq)
                if (index + 1 < textNodes.size) {
                    val next = textNodes[index + 1].textContent.orEmpty()
                    if (next.isNotBlank() && next.all { it == '#' || it.isWhitespace() }) {
                        textNodes[index + 1].textContent = ""
                    }
                }
            }
        }
    }

    private fun setContentControlDate(container: Element, date: Date) {
        val fullDate = SimpleDateFormat("yyyy-MM-dd'T'00:00:00'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }.format(date)
        for (dateElement in elements(container, "date")) {
            dateElement.setAttributeNS(DocxXml.WORD_NAMESPACE, "w:fullDate", fullDate)
        }
    }

    private fun convertPackageToDocument(entries: MutableMap<String, ByteArray>) {
        val contentTypes = entries.keys.firstOrNull {
            it == "[Content_Types].xml" || it.endsWith("/[Content_Types].xml")
        } ?: return
        entries[contentTypes] = DocxXml.convertTemplateContentType(entries.getValue(contentTypes))
    }

    private fun findDocumentEntry(entries: Map<String, ByteArray>): String {
        return entries.keys.firstOrNull {
            it == "word/document.xml" || it.endsWith("/word/document.xml")
        } ?: error("word/document.xml not found in template")
    }

    private fun rowValueContainers(row: Element): List<Element> {
        val containers = mutableListOf<Element>()
        val children = row.childNodes
        for (i in 0 until children.length) {
            val child = children.item(i) as? Element ?: continue
            if (DocxXml.localName(child) == "tc" || DocxXml.localName(child) == "sdt") {
                containers += child
            }
        }
        return containers
    }

    /** Returns rows in this table without including rows from a nested table. */
    private fun tableRows(table: Element): List<Element> {
        val rows = mutableListOf<Element>()
        fun walk(node: Node) {
            if (node is Element) {
                if (node !== table && DocxXml.localName(node) == "tbl") return
                if (DocxXml.localName(node) == "tr") {
                    rows += node
                    return
                }
            }
            val children = node.childNodes
            for (i in 0 until children.length) walk(children.item(i))
        }
        walk(table)
        return rows
    }

    private fun elements(root: Element, wantedLocalName: String): List<Element> {
        val matches = mutableListOf<Element>()
        if (DocxXml.localName(root) == wantedLocalName) matches += root
        val descendants = root.getElementsByTagName("*")
        for (i in 0 until descendants.length) {
            val element = descendants.item(i) as? Element ?: continue
            if (DocxXml.localName(element) == wantedLocalName) matches += element
        }
        return matches
    }

    private fun textElements(root: Element): List<Element> = elements(root, "t")

    private fun attribute(element: Element, wantedLocalName: String): String {
        val namespaced = element.getAttributeNS(DocxXml.WORD_NAMESPACE, wantedLocalName)
        if (namespaced.isNotBlank()) return namespaced
        val attributes = element.attributes
        for (i in 0 until attributes.length) {
            val item = attributes.item(i)
            if (DocxXml.localName(item) == wantedLocalName) return item.nodeValue.orEmpty()
        }
        return ""
    }

    private fun isInside(element: Element, ancestor: Element): Boolean {
        var current: Node? = element
        while (current != null) {
            if (current === ancestor) return true
            current = current.parentNode
        }
        return false
    }

    private fun normalizeLabel(value: String): String {
        return value.lowercase(Locale.US)
            .replace("&", " and ")
            .replace(Regex("[^a-z0-9]+"), " ")
            .trim()
            .replace(Regex("\\s+"), " ")
    }

    private fun normalizeFieldKey(value: String): String {
        return value.trim().lowercase(Locale.US)
            .replace(Regex("[^a-z0-9]+"), "_")
            .trim('_')
    }

    private fun normalizeWhitespace(value: String): String =
        value.replace(Regex("\\s+"), " ").trim()
}
