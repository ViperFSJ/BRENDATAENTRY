package com.bren.ndeinspection.domain

import java.util.Locale
import java.util.regex.Pattern

object LabelSlug {
    private val nonAlnum = Pattern.compile("[^a-z0-9]+")

    fun slugifyBase(label: String): String {
        val lower = label.lowercase(Locale.US).trim()
        val replaced = nonAlnum.matcher(lower).replaceAll("_")
        return replaced.trim('_')
    }

    fun makeLabelSlugs(labels: List<String>): Pair<List<String>, Map<String, String>> {
        val counts = mutableMapOf<String, Int>()
        val slugs = mutableListOf<String>()
        val map = linkedMapOf<String, String>()
        for (label in labels) {
            val base = slugifyBase(label).ifEmpty { "item" }
            val n = (counts[base] ?: 0) + 1
            counts[base] = n
            val slug = if (n == 1) base else "${base}_$n"
            slugs += slug
            map[slug] = label
        }
        return slugs to map
    }
}
