package com.bren.ndeinspection.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase

@Entity(tableName = "technicians")
data class TechnicianEntity(
    @PrimaryKey val technicianId: String,
    val displayName: String,
)

@Entity(tableName = "equipment_units")
data class EquipmentUnitEntity(
    @PrimaryKey val raeq: String,
    val raeqNum: Int,
    val className: String,
    val clientName: String? = null,
    val clientUnitId: String? = null,
    val ownerName: String? = null,
    val province: String? = null,
    val manufacturer: String? = null,
    val model: String? = null,
    val serialNo: String? = null,
    val createdAt: String = System.currentTimeMillis().toString(),
)

@Entity(tableName = "raeq_pool", primaryKeys = ["technicianId", "raeqNum"])
data class RaeqPoolEntity(
    val technicianId: String,
    val raeq: String,
    val raeqNum: Int,
    val status: String, // available | assigned | consumed
    val assignedEquipmentRaeq: String? = null,
    val updatedAt: String = System.currentTimeMillis().toString(),
)

@Entity(tableName = "inspections", primaryKeys = ["raeq", "technicianId", "inspectionDate"])
data class InspectionEntity(
    val raeq: String,
    val technicianId: String,
    val inspectionDate: String,
    val className: String,
    val createdAt: String = System.currentTimeMillis().toString(),
)

@Entity(tableName = "checklist_results", primaryKeys = ["raeq", "className", "labelSlug"])
data class ChecklistResultEntity(
    val raeq: String,
    val className: String,
    val labelSlug: String,
    val result: String, // OK | RR | N/A
    val updatedAt: String = System.currentTimeMillis().toString(),
)

@Dao
interface NdeDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertTechnician(tech: TechnicianEntity)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertRaeqPoolIgnore(entries: List<RaeqPoolEntity>)

    @Query(
        """
        SELECT * FROM raeq_pool
        WHERE technicianId = :technicianId AND status = 'available'
        ORDER BY raeqNum ASC LIMIT 1
        """
    )
    suspend fun nextAvailableRaeq(technicianId: String): RaeqPoolEntity?

    @Query(
        """
        UPDATE raeq_pool SET status = 'assigned', assignedEquipmentRaeq = :raeq,
        updatedAt = :updatedAt
        WHERE technicianId = :technicianId AND raeqNum = :raeqNum
        """
    )
    suspend fun markRaeqAssigned(technicianId: String, raeqNum: Int, raeq: String, updatedAt: String)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertEquipment(unit: EquipmentUnitEntity)

    @Query(
        """
        SELECT * FROM equipment_units
        WHERE clientUnitId = :unitId AND serialNo = :serial
        ORDER BY createdAt DESC LIMIT 1
        """
    )
    suspend fun findByUnitAndSerial(unitId: String, serial: String): EquipmentUnitEntity?

    @Query(
        """
        SELECT * FROM equipment_units
        WHERE clientUnitId = :unitId
        ORDER BY createdAt DESC LIMIT 1
        """
    )
    suspend fun findByUnit(unitId: String): EquipmentUnitEntity?

    @Query(
        """
        SELECT * FROM equipment_units
        WHERE serialNo = :serial
        ORDER BY createdAt DESC LIMIT 1
        """
    )
    suspend fun findBySerial(serial: String): EquipmentUnitEntity?

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertInspection(inspection: InspectionEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertChecklistResults(results: List<ChecklistResultEntity>)

    @Query("DELETE FROM checklist_results WHERE raeq = :raeq AND className = :className AND labelSlug NOT IN (:keep)")
    suspend fun deleteStaleChecklistResults(raeq: String, className: String, keep: List<String>)
}

@Database(
    entities = [
        TechnicianEntity::class,
        EquipmentUnitEntity::class,
        RaeqPoolEntity::class,
        InspectionEntity::class,
        ChecklistResultEntity::class,
    ],
    version = 1,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun dao(): NdeDao

    companion object {
        @Volatile private var instance: AppDatabase? = null

        fun getInstance(context: Context): AppDatabase {
            return instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "nde_inspection.db",
                ).build().also { instance = it }
            }
        }
    }
}
