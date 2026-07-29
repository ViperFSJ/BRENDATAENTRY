package com.bren.ndeinspection

import android.app.Application
import com.bren.ndeinspection.data.AppDatabase
import com.bren.ndeinspection.domain.SessionRepository

class NdeApp : Application() {
    lateinit var database: AppDatabase
        private set
    lateinit var repository: SessionRepository
        private set

    override fun onCreate() {
        super.onCreate()
        database = AppDatabase.getInstance(this)
        repository = SessionRepository(this, database)
    }
}
