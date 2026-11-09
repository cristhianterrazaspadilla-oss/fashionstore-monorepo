package com.example.fashionstore_movil

import android.content.Context
import android.view.View
import android.widget.FrameLayout
import io.flutter.plugin.platform.PlatformView
import io.livekit.android.renderer.TextureViewRenderer

/** PlatformView del video remoto Decart ("fashionstore/decart_video"). */
class DecartVideoView(
    context: Context,
    private val bridgeProvider: () -> DecartTryOnBridge?,
) : PlatformView {
    private val layout = FrameLayout(context)
    private var renderer: TextureViewRenderer? = null

    init {
        try {
            // TextureView compone correctamente dentro de AndroidView/Flutter.
            // SurfaceView puede quedar detrás de la capa de Flutter y verse
            // negro aun cuando el track remoto recibe frames.
            val r = TextureViewRenderer(context)
            layout.addView(
                r,
                FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT,
                ),
            )
            renderer = r
            bridgeProvider()?.setRenderer(r)
        } catch (_: Exception) {
            // Emulador sin WebRTC: la vista queda como superficie vacía.
        }
    }

    override fun getView(): View = layout

    override fun dispose() {
        try {
            renderer?.release()
        } catch (_: Exception) {}
        renderer = null
        try {
            bridgeProvider()?.setRenderer(null)
        } catch (_: Exception) {}
    }
}

class DecartVideoViewFactory(
    private val bridgeProvider: () -> DecartTryOnBridge?,
) : io.flutter.plugin.platform.PlatformViewFactory(
    io.flutter.plugin.common.StandardMessageCodec.INSTANCE,
) {
    override fun create(context: Context, viewId: Int, args: Any?): PlatformView {
        return DecartVideoView(context, bridgeProvider)
    }
}
