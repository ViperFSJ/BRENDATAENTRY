package com.bren.ndeinspection.domain

import android.content.Context
import android.content.res.AssetManager
import java.io.File
import java.io.FileOutputStream

object TemplateAssets {
    private const val ROOT = "Templates"

    fun listClassNames(assets: AssetManager): List<String> {
        val dirs = assets.list(ROOT)?.sorted().orEmpty()
        return dirs.filter { className ->
            val files = assets.list("$ROOT/$className")?.toList().orEmpty()
            val hasChecklist = files.any { it.startsWith("Checklist") && (it.endsWith(".dotx") || it.endsWith(".docx")) }
            val hasCert = files.any { it.startsWith("EC-1210D") && it.endsWith(".dotx") }
            hasChecklist && hasCert
        }
    }

    fun findChecklistAsset(assets: AssetManager, className: String): String {
        val files = assets.list("$ROOT/$className")?.sorted().orEmpty()
        val dotx = files.firstOrNull { it.startsWith("Checklist") && it.endsWith(".dotx") }
        val docx = files.firstOrNull { it.startsWith("Checklist") && it.endsWith(".docx") }
        val name = dotx ?: docx ?: error("No checklist template in Templates/$className")
        return "$ROOT/$className/$name"
    }

    fun findCertificateAsset(assets: AssetManager, className: String): String {
        val files = assets.list("$ROOT/$className")?.sorted().orEmpty()
        val name = files.firstOrNull { it.startsWith("EC-1210D") && it.endsWith(".dotx") }
            ?: error("No certificate template in Templates/$className")
        return "$ROOT/$className/$name"
    }

    fun findChecklistXmlAsset(assets: AssetManager, className: String): String? {
        val files = assets.list("$ROOT/$className")?.sorted().orEmpty()
        val name = files.firstOrNull { it.startsWith("Checklist") && it.endsWith(".xml") } ?: return null
        return "$ROOT/$className/$name"
    }

    fun generalManifestAsset(): String = "$ROOT/General/checklist_manifest.json"

    fun copyAssetToCache(context: Context, assetPath: String, outName: String? = null): File {
        val name = outName ?: assetPath.substringAfterLast('/')
        val out = File(context.cacheDir, "templates/$name")
        out.parentFile?.mkdirs()
        context.assets.open(assetPath).use { input ->
            FileOutputStream(out).use { output -> input.copyTo(output) }
        }
        return out
    }
}
