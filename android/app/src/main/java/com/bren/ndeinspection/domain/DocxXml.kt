package com.bren.ndeinspection.domain

import org.w3c.dom.Document
import org.w3c.dom.Element
import org.w3c.dom.Node
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.LinkedHashMap
import java.util.Locale
import java.util.TimeZone
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream
import javax.xml.XMLConstants
import javax.xml.parsers.DocumentBuilderFactory
import javax.xml.transform.OutputKeys
import javax.xml.transform.TransformerFactory
import javax.xml.transform.dom.DOMSource
import javax.xml.transform.stream.StreamResult

object DocxXml {
    const val WORD_NAMESPACE =
        "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    private const val ACCESS_EXTERNAL_DTD =
        "http://javax.xml.XMLConstants/property/accessExternalDTD"
    private const val ACCESS_EXTERNAL_SCHEMA =
        "http://javax.xml.XMLConstants/property/accessExternalSchema"
    private const val ACCESS_EXTERNAL_STYLESHEET =
        "http://javax.xml.XMLConstants/property/accessExternalStylesheet"
    private const val TEMPLATE_CONTENT_TYPE =
        "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
    private const val DOCUMENT_CONTENT_TYPE =
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"

    fun localName(node: Node): String {
        val local = node.localName
        return if (!local.isNullOrBlank()) local else node.nodeName.substringAfter(':')
    }

    fun cellText(element: Element): String {
        val text = StringBuilder()
        if (localName(element) == "t") {
            text.append(element.textContent.orEmpty())
        }
        val descendants = element.getElementsByTagName("*")
        for (i in 0 until descendants.length) {
            val child = descendants.item(i)
            if (localName(child) == "t") {
                text.append(child.textContent.orEmpty())
            }
        }
        return text.toString().replace(Regex("\\s+"), " ").trim()
    }

    /**
     * Reuses the first Word text run so the template's formatting is retained.
     * Remaining text nodes are cleared because Word often splits placeholders across runs.
     */
    fun setContainerText(element: Element, value: String) {
        val textNodes = descendantElements(element, "t")
        if (textNodes.isNotEmpty()) {
            textNodes.first().textContent = value
            setPreserveSpace(textNodes.first(), value)
            setTextRunBlack(textNodes.first())
            for (i in 1 until textNodes.size) {
                textNodes[i].textContent = ""
            }
            return
        }

        val document = element.ownerDocument
        val content = if (localName(element) == "sdt") {
            descendantElements(element, "sdtContent").firstOrNull() ?: element
        } else {
            element
        }
        val paragraph = descendantElements(content, "p").firstOrNull()
            ?: document.createElementNS(WORD_NAMESPACE, "w:p").also(content::appendChild)
        val run = document.createElementNS(WORD_NAMESPACE, "w:r")
        val runProperties = document.createElementNS(WORD_NAMESPACE, "w:rPr")
        val color = document.createElementNS(WORD_NAMESPACE, "w:color")
        color.setAttributeNS(WORD_NAMESPACE, "w:val", "000000")
        runProperties.appendChild(color)
        run.appendChild(runProperties)
        val text = document.createElementNS(WORD_NAMESPACE, "w:t")
        text.textContent = value
        setPreserveSpace(text, value)
        run.appendChild(text)
        paragraph.appendChild(run)
    }

    fun parseFlexibleDate(value: String): Date? {
        val input = value.trim()
        if (input.isEmpty()) return null
        val formats = listOf(
            "MMMM d, yyyy",
            "MMM d, yyyy",
            "yyyy-MM-dd",
            "MM/dd/yyyy",
            "yyyy/MM/dd",
            "MMMM d yyyy",
            "MMM d yyyy",
        )
        for (pattern in formats) {
            val parser = SimpleDateFormat(pattern, Locale.US).apply {
                isLenient = false
                timeZone = TimeZone.getTimeZone("UTC")
            }
            val parsed = runCatching { parser.parse(input) }.getOrNull()
            if (parsed != null) return parsed
        }
        return null
    }

    fun formatDateForPlaceholder(date: Date, placeholder: String): String {
        val isoPlaceholder = Regex(
            """(?i)\b(?:yyyy|\d{4})\s*-\s*(?:mm|\d{2})\s*-\s*(?:dd|\d{2})\b"""
        ).containsMatchIn(placeholder)
        val pattern = if (isoPlaceholder) "yyyy-MM-dd" else "MMMM d, yyyy"
        return SimpleDateFormat(pattern, Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }.format(date)
    }

    fun namespaceAwareDocumentBuilderFactory(): DocumentBuilderFactory {
        return DocumentBuilderFactory.newInstance().apply {
            isNamespaceAware = true
            isExpandEntityReferences = false
            runCatching { isXIncludeAware = false }
            runCatching {
                setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
            }
            runCatching {
                setFeature("http://xml.org/sax/features/external-general-entities", false)
            }
            runCatching {
                setFeature("http://xml.org/sax/features/external-parameter-entities", false)
            }
            runCatching { setAttribute(ACCESS_EXTERNAL_DTD, "") }
            runCatching { setAttribute(ACCESS_EXTERNAL_SCHEMA, "") }
        }
    }

    fun parseDocument(bytes: ByteArray): Document =
        namespaceAwareDocumentBuilderFactory()
            .newDocumentBuilder()
            .parse(ByteArrayInputStream(bytes))

    fun documentBytes(document: Document): ByteArray {
        val output = ByteArrayOutputStream()
        val transformerFactory = TransformerFactory.newInstance().apply {
            runCatching { setAttribute(ACCESS_EXTERNAL_DTD, "") }
            runCatching { setAttribute(ACCESS_EXTERNAL_STYLESHEET, "") }
        }
        transformerFactory.newTransformer().apply {
            setOutputProperty(OutputKeys.ENCODING, "UTF-8")
            setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "no")
            setOutputProperty(OutputKeys.INDENT, "no")
        }.transform(DOMSource(document), StreamResult(output))
        return output.toByteArray()
    }

    fun readZipEntries(file: File): MutableMap<String, ByteArray> {
        val entries = LinkedHashMap<String, ByteArray>()
        ZipInputStream(FileInputStream(file).buffered()).use { input ->
            var entry = input.nextEntry
            while (entry != null) {
                if (!entry.isDirectory) {
                    entries[entry.name] = input.readBytes()
                }
                input.closeEntry()
                entry = input.nextEntry
            }
        }
        return entries
    }

    fun writeZipEntries(file: File, entries: Map<String, ByteArray>) {
        file.parentFile?.mkdirs()
        ZipOutputStream(FileOutputStream(file).buffered()).use { output ->
            for ((name, bytes) in entries) {
                output.putNextEntry(ZipEntry(name))
                output.write(bytes)
                output.closeEntry()
            }
        }
    }

    fun convertTemplateContentType(bytes: ByteArray): ByteArray {
        return bytes.toString(Charsets.UTF_8)
            .replace(TEMPLATE_CONTENT_TYPE, DOCUMENT_CONTENT_TYPE)
            .toByteArray(Charsets.UTF_8)
    }

    fun descendantElements(element: Element, wantedLocalName: String): List<Element> {
        val matches = mutableListOf<Element>()
        if (localName(element) == wantedLocalName) matches += element
        val descendants = element.getElementsByTagName("*")
        for (i in 0 until descendants.length) {
            val child = descendants.item(i) as? Element ?: continue
            if (localName(child) == wantedLocalName) matches += child
        }
        return matches
    }

    private fun setPreserveSpace(text: Element, value: String) {
        if (value.startsWith(" ") || value.endsWith(" ")) {
            text.setAttributeNS(XMLConstants.XML_NS_URI, "xml:space", "preserve")
        }
    }

    private fun setTextRunBlack(text: Element) {
        val run = text.parentNode as? Element ?: return
        if (localName(run) != "r") return
        var runProperties: Element? = null
        val children = run.childNodes
        for (i in 0 until children.length) {
            val child = children.item(i) as? Element ?: continue
            if (localName(child) == "rPr") {
                runProperties = child
                break
            }
        }
        if (runProperties == null) {
            runProperties = run.ownerDocument.createElementNS(WORD_NAMESPACE, "w:rPr")
            run.insertBefore(runProperties, run.firstChild)
        }
        val effectiveRunProperties = runProperties ?: return
        var color: Element? = null
        val properties = effectiveRunProperties.childNodes
        for (i in 0 until properties.length) {
            val child = properties.item(i) as? Element ?: continue
            if (localName(child) == "color") {
                color = child
                break
            }
        }
        if (color == null) {
            color = run.ownerDocument.createElementNS(WORD_NAMESPACE, "w:color")
            effectiveRunProperties.appendChild(color)
        }
        val effectiveColor = color ?: return
        effectiveColor.setAttributeNS(WORD_NAMESPACE, "w:val", "000000")
    }
}
