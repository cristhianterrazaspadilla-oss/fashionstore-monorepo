package com.example.fashionstore_movil

import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterFragmentActivity() {
    private var bridge: DecartTryOnBridge? = null
    private var eventSink: EventChannel.EventSink? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        EventChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "fashionstore/decart_try_on/events",
        ).setStreamHandler(
            object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    eventSink = events
                    ensureBridge()
                }

                override fun onCancel(arguments: Any?) {
                    eventSink = null
                }
            },
        )

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "fashionstore/decart_try_on",
        ).setMethodCallHandler { call, result ->
            ensureBridge()?.onMethodCall(call, result)
                ?: result.error("NO_BRIDGE", "Puente no disponible", null)
        }

        flutterEngine.platformViewsController.registry.registerViewFactory(
            "fashionstore/decart_video",
            // La PlatformView puede crearse antes de que Flutter escuche el
            // EventChannel. Garantizar el bridge aquí evita perder para
            // siempre el renderer por una carrera de inicialización.
            DecartVideoViewFactory { ensureBridge() },
        )
    }

    private fun ensureBridge(): DecartTryOnBridge? {
        val b = bridge
        if (b != null) return b
        val created = DecartTryOnBridge(
            context = this,
            events = eventSink,
            emit = { mapa -> eventSink?.success(mapa) },
        )
        bridge = created
        return created
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        try {
            bridge?.destruir()
        } catch (_: Exception) {}
        bridge = null
        super.cleanUpFlutterEngine(flutterEngine)
    }
}
