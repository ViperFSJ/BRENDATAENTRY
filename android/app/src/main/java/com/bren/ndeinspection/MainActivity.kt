package com.bren.ndeinspection

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color
import com.bren.ndeinspection.ui.IntakeApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(
                colorScheme = lightColorScheme(
                    primary = Color(0xFF145A8C),
                    secondary = Color(0xFF2F6F4E),
                    background = Color(0xFFF3F6F8),
                    surface = Color(0xFFFFFFFF),
                )
            ) {
                IntakeApp()
            }
        }
    }
}
