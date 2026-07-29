package com.bren.ndeinspection.domain

import com.bren.ndeinspection.data.EquipmentUnitEntity
import com.bren.ndeinspection.data.InspectionEntity
import com.bren.ndeinspection.data.NdeDao
import com.bren.ndeinspection.data.RaeqPoolEntity
import com.bren.ndeinspection.data.TechnicianEntity

class RaeqService(private val dao: NdeDao) {
    suspend fun ensureTechnician(technicianId: String, displayName: String) {
        dao.upsertTechnician(TechnicianEntity(technicianId, displayName))
    }

    suspend fun addAvailableRaeqs(technicianId: String, displayName: String, spec: String) {
        ensureTechnician(technicianId, displayName)
        val entries = expandRaeqSpec(spec).map { (raeq, num) ->
            RaeqPoolEntity(
                technicianId = technicianId,
                raeq = raeq,
                raeqNum = num,
                status = "available",
            )
        }
        if (entries.isNotEmpty()) dao.insertRaeqPoolIgnore(entries)
    }

    suspend fun findCandidate(unitId: String?, serialNo: String?): EquipmentCandidate? {
        val unit = unitId?.trim().orEmpty()
        val serial = serialNo?.trim().orEmpty()
        if (unit.isEmpty() && serial.isEmpty()) return null

        val matched: Pair<EquipmentUnitEntity, String>? = when {
            unit.isNotEmpty() && serial.isNotEmpty() -> {
                dao.findByUnitAndSerial(unit, serial)?.let { it to "unit+serial" }
                    ?: dao.findByUnit(unit)?.let { it to "unit_only" }
                    ?: dao.findBySerial(serial)?.let { it to "serial_only" }
            }
            unit.isNotEmpty() -> dao.findByUnit(unit)?.let { it to "unit_only" }
            else -> dao.findBySerial(serial)?.let { it to "serial_only" }
        }
        val (entity, strength) = matched ?: return null
        return EquipmentCandidate(
            raeq = entity.raeq,
            className = entity.className,
            clientUnitId = entity.clientUnitId.orEmpty(),
            serialNo = entity.serialNo.orEmpty(),
            matchStrength = strength,
            clientName = entity.clientName.orEmpty(),
            manufacturer = entity.manufacturer.orEmpty(),
            model = entity.model.orEmpty(),
        )
    }

    suspend fun assignNext(
        technicianId: String,
        className: String,
        fields: SessionFields,
    ): String {
        val next = dao.nextAvailableRaeq(technicianId)
            ?: error("No available RAEQ entries for technician=$technicianId")
        dao.upsertEquipment(
            EquipmentUnitEntity(
                raeq = next.raeq,
                raeqNum = next.raeqNum,
                className = className,
                clientName = fields.clientName,
                clientUnitId = fields.clientUnitId,
                ownerName = fields.ownerName,
                province = fields.province,
                manufacturer = fields.manufacturer,
                model = fields.model,
                serialNo = fields.serialNo,
            )
        )
        dao.markRaeqAssigned(
            technicianId = technicianId,
            raeqNum = next.raeqNum,
            raeq = next.raeq,
            updatedAt = System.currentTimeMillis().toString(),
        )
        return next.raeq
    }

    suspend fun identifyOrAssign(
        technicianId: String,
        className: String,
        fields: SessionFields,
        forceNew: Boolean,
        confirmExisting: suspend (EquipmentCandidate) -> Boolean,
    ): Pair<String, String> {
        if (!forceNew) {
            val candidate = findCandidate(fields.clientUnitId, fields.serialNo)
            if (candidate != null) {
                return if (confirmExisting(candidate)) {
                    candidate.raeq to "existing_confirmed"
                } else {
                    assignNext(technicianId, className, fields) to "existing_rejected_new_assigned"
                }
            }
        }
        return assignNext(technicianId, className, fields) to "new_assigned"
    }

    suspend fun markInspectionStarted(
        technicianId: String,
        raeq: String,
        inspectionDate: String,
        className: String,
    ) {
        dao.insertInspection(
            InspectionEntity(
                raeq = raeq,
                technicianId = technicianId,
                inspectionDate = inspectionDate,
                className = className,
            )
        )
    }

    companion object {
        fun extractRaeqNum(raw: String): Int {
            val m = Regex("(\\d+)").find(raw.trim())
                ?: error("Could not extract numeric RAEQ from: $raw")
            return m.groupValues[1].toInt()
        }

        fun normalizeRaeq(raw: String): Pair<String, Int> {
            val n = extractRaeqNum(raw)
            return "RAEQ$n" to n
        }

        fun expandRaeqSpec(spec: String): List<Pair<String, Int>> {
            val raw = spec.trim()
            if (raw.isEmpty()) return emptyList()
            val out = mutableListOf<Pair<String, Int>>()
            for (part in raw.split(",").map { it.trim() }.filter { it.isNotEmpty() }) {
                val range = Regex("^\\s*(.+?)-(.+?)\\s*$").matchEntire(part)
                if (range != null) {
                    val start = normalizeRaeq(range.groupValues[1]).second
                    val end = normalizeRaeq(range.groupValues[2]).second
                    require(end >= start) { "Invalid RAEQ range: $part" }
                    for (n in start..end) out += "RAEQ$n" to n
                } else {
                    out += normalizeRaeq(part)
                }
            }
            return out
        }
    }
}
