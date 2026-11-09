package com.example.fashionstore_movil

import ai.decart.sdk.ConnectionState
import ai.decart.sdk.DecartClient
import ai.decart.sdk.DecartClientConfig
import ai.decart.sdk.RealtimeModels
import ai.decart.sdk.realtime.ConnectOptions
import ai.decart.sdk.realtime.DiagnosticEvent
import ai.decart.sdk.realtime.FacingMode
import ai.decart.sdk.realtime.InitialPrompt
import ai.decart.sdk.realtime.MirrorMode
import ai.decart.sdk.realtime.RealtimeMediaStream
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.livekit.android.renderer.TextureViewRenderer
import io.livekit.android.room.track.VideoTrack
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import livekit.org.webrtc.EglRenderer
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * Puente nativo del probador virtual (CU17).
 *
 * - SDK Android oficial Decart 0.7.10 con modelo fijo lucy-2.5.
 * - Recibe solo el token cliente temporal (memoria); nunca la API key.
 * - Sin ML Kit, MediaPipe, TFLite, pose, segmentación ni overlays locales.
 * - Cleanup idempotente y thread-safe: listeners + disconnect + desvincular
 *   renderer + release + borrado.
 *
 * Confirmación de transformación (corrección final):
 * - `ConnectionState.GENERATING` significa únicamente "Decart procesando";
 *   nunca confirma visibilidad ni retira la cubierta.
 * - El SDK Decart 0.7.10 no expone un callback específico de
 *   "transformación visible". El único callback que confirma un frame
 *   realmente renderizado es [EglRenderer.FrameListener.onFrame] (Bitmap)
 *   registrado en el [SurfaceViewRenderer] del track remoto (LiveKit envuelve
 *   a `livekit.org.webrtc.SurfaceViewRenderer`, que hereda
 *   `addFrameListener` / `removeFrameListener` de `EglRenderer`).
 * - Por eso `primeraTransformacion` se emite solo con el primer frame remoto
 *   posterior a haber visto GENERATING (nunca con frames crudos previos), y
 *   `prendaAplicada` solo con el primer frame posterior al `setImage` de la
 *   secuencia vigente. Listeners de un solo uso con referencia explícita.
 * - Tokens fake/test limitados estrictamente a BuildConfig.DEBUG.
 */
class DecartTryOnBridge(
    private val context: Context,
    private val events: EventChannel.EventSink?,
    private val emit: (Map<String, String>) -> Unit,
) : MethodChannel.MethodCallHandler {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var client: DecartClient? = null
    private var localStream: RealtimeMediaStream? = null
    private var localTrack: VideoTrack? = null
    private var currentTrack: VideoTrack? = null
    private var conectando = false
    private var renderer: TextureViewRenderer? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private val rendererInicializado = AtomicBoolean(false)

    private val cerrando = AtomicBoolean(false)
    private val secuenciaPrenda = AtomicInteger(0)
    // Confirmación atómica de un solo uso: evita emisiones repetidas de
    // primeraTransformacion / prendaAplicada / live ante frames consecutivos.
    private val primeraTransformacionConfirmada = AtomicBoolean(false)
    // GENERATING visto: solo los frames posteriores confirman visibilidad.
    // Los frames previos son cámara cruda y deben ignorarse.
    private val generandoVisto = AtomicBoolean(false)
    // connectionState es StateFlow y entrega DISCONNECTED inmediatamente al
    // suscribirse. Solo una transición posterior a CONNECTED es una caída.
    private val conectadoAlgunaVez = AtomicBoolean(false)
    private val cerrado = AtomicBoolean(false)
    // Referencias explícitas a cada listener registrado (un solo uso).
    // Sin referencia no se puede eliminar y el listener fuga / duplica eventos.
    private var listenerInicial: EglRenderer.FrameListener? = null
    private var listenerPrenda: EglRenderer.FrameListener? = null
    private var secuenciaListenerPrenda: Int = -1

    fun setRenderer(r: TextureViewRenderer?) {
        renderer = r
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "initialize" -> {
                result.success(null)
            }
            "connect" -> {
                val token = call.argument<String>("token").orEmpty()
                val imagenUrl = call.argument<String>("imagenPrendaUrl").orEmpty()
                val prompt = call.argument<String>("promptPrenda").orEmpty()
                if (conectando) {
                    result.error("EN_CURSO", "Conexión ya en curso", null)
                    return
                }
                conectando = true
                scope.launch {
                    try {
                        conectar(token, imagenUrl, prompt)
                        result.success(null)
                    } catch (e: Exception) {
                        conectando = false
                        emit(mapOf("tipo" to "error", "codigo" to clasificar(e), "mensaje" to (e.message ?: "")))
                        result.error(clasificar(e), e.message, null)
                    }
                }
            }
            "setGarment" -> {
                val imagenUrl = call.argument<String>("imagenPrendaUrl").orEmpty()
                val prompt = call.argument<String>("promptPrenda").orEmpty()
                scope.launch {
                    try {
                        cambiarPrenda(imagenUrl, prompt)
                        result.success(null)
                    } catch (e: Exception) {
                        emit(mapOf("tipo" to "error", "codigo" to clasificar(e), "mensaje" to (e.message ?: "")))
                        result.error(clasificar(e), e.message, null)
                    }
                }
            }
            "disconnect" -> {
                scope.launch {
                    cerrarNativo()
                    result.success(null)
                }
            }
            "release" -> {
                scope.launch {
                    cerrarNativo()
                    result.success(null)
                }
            }
            else -> result.notImplemented()
        }
    }

    private suspend fun conectar(token: String, imagenUrl: String, prompt: String) {
        if (token.isEmpty()) throw IllegalArgumentException("Token vacío")

        // Protección de seguridad obligatoria: Tokens fake_ o test_ NO permitidos en producción.
        if (token.startsWith("fake_") || token.startsWith("test_")) {
            if (!BuildConfig.DEBUG) {
                throw SecurityException("Tokens simulados no están permitidos en compilaciones release.")
            }
            // Modo simulado exclusivo de DEBUG / tests controlados
            withContext(Dispatchers.Main) {
                emit(mapOf("tipo" to "camaraLista"))
                emit(mapOf("tipo" to "streamRemoto"))
                emit(mapOf("tipo" to "primeraTransformacion"))
                emit(mapOf("tipo" to "live"))
            }
            conectando = false
            return
        }

        // Limpiar una conexión anterior sin liberar el renderer que acaba de
        // crear la PlatformView. Liberarlo aquí dejaba la cámara activa unos
        // segundos, pero sin superficie válida para el stream remoto.
        cerrarConexionPreviaConservandoRenderer()
        primeraTransformacionConfirmada.set(false)
        generandoVisto.set(false)
        conectadoAlgunaVez.set(false)
        cerrado.set(false)
        eliminarListeners()
        emit(mapOf("tipo" to "conectando"))

        val c = DecartClient(
            context.applicationContext,
            DecartClientConfig(
                apiKey = token,
                baseUrl = "wss://api.decart.ai",
            ),
        )
        client = c
        observar(c)

        // Crear primero la captura local y renderizarla inmediatamente. Es el
        // equivalente oficial de la vista previa que usa la app de referencia:
        // el mismo stream se entrega luego a connect(), por lo que no se abre
        // una segunda cámara ni se implementa WebRTC manual.
        val streamLocal = c.realtime.createLocalVideoStream(
            model = RealtimeModels.LUCY_2_5,
            facing = FacingMode.FRONT,
            mirror = MirrorMode.AUTO,
        )
        localStream = streamLocal
        vincularStreamLocal(streamLocal)

        val base64 = withContext(Dispatchers.IO) { descargarBase64(imagenUrl) }
        val promptInicial = prompt.ifEmpty { "Replace only the current top with the referenced garment" }

        c.realtime.connect(
            ConnectOptions(
                model = RealtimeModels.LUCY_2_5,
                initialPrompt = InitialPrompt(promptInicial, enhance = true),
                initialImage = base64,
                facing = FacingMode.FRONT,
                mirror = MirrorMode.AUTO,
                publishCamera = true,
                onRemoteStream = { stream ->
                    vincularStreamRemoto(stream)
                },
            ),
            localStream = streamLocal,
        )
        conectando = false
    }

    private suspend fun cambiarPrenda(imagenUrl: String, prompt: String) {
        val c = client ?: throw IllegalStateException("Sin conexión activa")
        // Eliminar cualquier listener pendiente anterior: un listener viejo
        // jamás debe confirmar una prenda nueva (callbacks atrasados).
        eliminarListenerPrenda()
        val seq = secuenciaPrenda.incrementAndGet()
        emit(mapOf("tipo" to "cambiandoPrenda", "seq" to seq.toString()))

        val base64 = withContext(Dispatchers.IO) { descargarBase64(imagenUrl) }
        // setImage es suspendible: espera confirmación del servidor y puede
        // fallar por moderación, timeout o desconexión (se propaga a Flutter).
        c.realtime.setImage(
            imageBase64 = base64,
            prompt = prompt.ifEmpty { "Replace only the current top with the referenced garment" },
            enhance = true,
        )

        // Verificar que no haya llegado una solicitud posterior mientras se procesaba
        if (secuenciaPrenda.get() == seq && !cerrado.get()) {
            val r = renderer
            if (r != null) {
                // Esperar un frame remoto posterior a esta solicitud y confirmar
                // solamente la secuencia vigente; la cubierta de transición se
                // mantiene hasta esa confirmación.
                registrarListenerPrenda(r, seq)
            } else {
                emit(
                    mapOf(
                        "tipo" to "error",
                        "codigo" to "RENDERER_NO_DISPONIBLE",
                        "mensaje" to "No hay una superficie de video para confirmar la prenda.",
                    ),
                )
            }
        }
    }

    /**
     * Registra el listener inicial de un solo uso sobre el renderer remoto.
     *
     * Firma real del SDK instalado (WebRTC sombreado por LiveKit):
     * `addFrameListener(EglRenderer.FrameListener, Float)` y
     * `removeFrameListener(EglRenderer.FrameListener)`, donde
     * `FrameListener.onFrame(Bitmap)` confirma el frame renderizado.
     */
    private fun registrarListenerInicial(r: TextureViewRenderer) {
        eliminarListenerInicial()
        val listener = EglRenderer.FrameListener { _ ->
            // Ignorar frames crudos previos a GENERATING y callbacks tardíos
            // posteriores al cierre; confirmar una sola vez de forma atómica.
            if (cerrado.get() || !generandoVisto.get()) return@FrameListener
            if (!primeraTransformacionConfirmada.compareAndSet(false, true)) return@FrameListener
            mainHandler.post {
                if (cerrado.get()) return@post
                eliminarListenerInicial()
                emit(mapOf("tipo" to "primeraTransformacion"))
                emit(mapOf("tipo" to "live"))
            }
        }
        listenerInicial = listener
        try {
            r.addFrameListener(listener, 1f)
        } catch (_: Exception) {
            listenerInicial = null
        }
    }

    /**
     * Registra el listener de cambio de prenda para la secuencia [seq].
     * Solo un frame posterior a su `setImage` confirma esa secuencia;
     * callbacks atrasados de prendas anteriores se ignoran por secuencia.
     */
    private fun registrarListenerPrenda(r: TextureViewRenderer, seq: Int) {
        val listener = EglRenderer.FrameListener { _ ->
            if (cerrado.get()) return@FrameListener
            if (secuenciaPrenda.get() != seq) return@FrameListener
            if (secuenciaListenerPrenda != seq) return@FrameListener
            mainHandler.post {
                if (cerrado.get()) return@post
                if (secuenciaPrenda.get() != seq) return@post
                // Un solo uso: marcar, eliminar y limpiar referencia.
                secuenciaListenerPrenda = -1
                eliminarListenerPrenda()
                emit(mapOf("tipo" to "prendaAplicada", "seq" to seq.toString()))
                emit(mapOf("tipo" to "live"))
            }
        }
        listenerPrenda = listener
        secuenciaListenerPrenda = seq
        try {
            r.addFrameListener(listener, 1f)
        } catch (e: Exception) {
            listenerPrenda = null
            secuenciaListenerPrenda = -1
            emit(
                mapOf(
                    "tipo" to "error",
                    "codigo" to "RENDERER_NO_DISPONIBLE",
                    "mensaje" to "No se pudo confirmar el frame transformado.",
                ),
            )
            Log.w("DecartBridge", "No se pudo registrar el listener de cambio", e)
        }
    }

    private fun eliminarListenerInicial() {
        try {
            val r = renderer
            val l = listenerInicial
            if (r != null && l != null) {
                try {
                    r.removeFrameListener(l)
                } catch (_: Exception) {}
            }
        } catch (_: Exception) {
        } finally {
            listenerInicial = null
        }
    }

    private fun eliminarListenerPrenda() {
        try {
            val r = renderer
            val l = listenerPrenda
            if (r != null && l != null) {
                try {
                    r.removeFrameListener(l)
                } catch (_: Exception) {}
            }
        } catch (_: Exception) {
        } finally {
            listenerPrenda = null
            secuenciaListenerPrenda = -1
        }
    }

    private fun eliminarListeners() {
        eliminarListenerInicial()
        eliminarListenerPrenda()
    }

    private fun observar(c: DecartClient) {
        scope.launch {
            c.realtime.connectionState.collect { state ->
                when (state) {
                    ConnectionState.CONNECTED -> {
                        conectadoAlgunaVez.set(true)
                        // Conectado a la sala: NO implica resultado visible.
                        // La cubierta se conserva hasta primeraTransformacion.
                        emit(mapOf("tipo" to "conectado"))
                    }
                    ConnectionState.GENERATING -> {
                        // GENERATING = Decart procesando, NO frame visible.
                        // No activa primeraTransformacion ni retira cubierta:
                        // solo marca que los próximos frames ya son
                        // transformación y habilita su confirmación.
                        generandoVisto.set(true)
                        mainHandler.post {
                            emit(mapOf("tipo" to "generando"))
                        }
                    }
                    ConnectionState.DISCONNECTED -> {
                        if (!cerrado.get() && conectadoAlgunaVez.get()) {
                            emit(mapOf(
                                "tipo" to "disconnected",
                                "codigo" to "DECART_DESCONECTADO",
                                "mensaje" to "Decart cerró WebSocket/LiveKit antes de entregar la transformación.",
                            ))
                        }
                    }
                    else -> {}
                }
            }
        }
        scope.launch {
            c.realtime.errors.collect { e ->
                emit(mapOf("tipo" to "error", "codigo" to (e.code ?: "ERROR"), "mensaje" to (e.message ?: "")))
            }
        }
        // Confirmación oficial del SDK: evita depender exclusivamente del
        // callback bitmap del SurfaceViewRenderer, que algunos fabricantes
        // no ejecutan cuando la vista está cubierta por Flutter.
        scope.launch {
            c.realtime.diagnostics.collect { event ->
                if (event is DiagnosticEvent.FirstFrame &&
                    !cerrado.get() &&
                    primeraTransformacionConfirmada.compareAndSet(false, true)
                ) {
                    mainHandler.post {
                        if (!cerrado.get()) {
                            eliminarListenerInicial()
                            emit(mapOf("tipo" to "primeraTransformacion"))
                            emit(mapOf("tipo" to "live"))
                        }
                    }
                }
            }
        }
        scope.launch {
            c.realtime.remoteStreamUpdates.collect { stream ->
                vincularStreamRemoto(stream)
            }
        }
    }

    private fun vincularStreamLocal(stream: RealtimeMediaStream) {
        mainHandler.post {
            try {
                val r = renderer
                val track = stream.videoTrack
                val room = stream.room
                localTrack = track
                currentTrack = track
                if (r != null && track != null && room != null) {
                    inicializarRendererSiHaceFalta(r, stream)
                    track.addRenderer(r)
                    emit(mapOf("tipo" to "camaraLista"))
                    emit(mapOf("tipo" to "vistaLocal"))
                } else {
                    emit(
                        mapOf(
                            "tipo" to "error",
                            "codigo" to "CAMARA_SIN_RENDERER",
                            "mensaje" to "La cámara se abrió sin una superficie de video disponible.",
                        ),
                    )
                }
            } catch (e: Exception) {
                emit(mapOf("tipo" to "error", "codigo" to "CAMARA_NO_VISIBLE", "mensaje" to (e.message ?: "")))
            }
        }
    }

    private fun vincularStreamRemoto(stream: RealtimeMediaStream) {
        mainHandler.post {
            try {
                val r = renderer
                val track = stream.videoTrack
                if (r != null && track != null && stream.room != null) {
                    // Un renderer solo puede mostrar una fuente a la vez. Al
                    // llegar Decart, retirar la vista local y sustituirla por
                    // el track remoto transformado sobre la misma superficie.
                    localTrack?.let { local ->
                        try {
                            local.removeRenderer(r)
                        } catch (_: Exception) {}
                    }
                    currentTrack?.takeIf { it !== localTrack && it !== track }?.let { anterior ->
                        try {
                            anterior.removeRenderer(r)
                        } catch (_: Exception) {}
                    }
                    inicializarRendererSiHaceFalta(r, stream)
                    currentTrack = track
                    track.addRenderer(r)
                    registrarListenerInicial(r)
                }
            } catch (e: Exception) {
                Log.w("DecartBridge", "No se pudo vincular el stream remoto", e)
            }
            emit(mapOf("tipo" to "streamRemoto"))
        }
    }

    private fun inicializarRendererSiHaceFalta(
        r: TextureViewRenderer,
        stream: RealtimeMediaStream,
    ) {
        if (rendererInicializado.compareAndSet(false, true)) {
            try {
                r.init(stream.room!!.lkObjects.eglBase.eglBaseContext, null)
            } catch (e: Exception) {
                rendererInicializado.set(false)
                throw e
            }
        }
    }

    private fun descargarBase64(url: String): String? {
        if (url.isEmpty() || !url.startsWith("https://", ignoreCase = true)) return null
        return try {
            val con = URL(url).openConnection() as? HttpURLConnection ?: return null
            con.instanceFollowRedirects = false // No seguir redirecciones automáticas a HTTP
            con.connectTimeout = 15000
            con.readTimeout = 15000
            con.requestMethod = "GET"
            con.connect()

            val code = con.responseCode
            if (code !in 200..299) {
                con.disconnect()
                return null
            }

            con.inputStream.use { input ->
                val bytes = input.readBytes()
                con.disconnect()
                if (bytes.isEmpty() || bytes.size > 8 * 1024 * 1024) return null
                Base64.encodeToString(bytes, Base64.NO_WRAP)
            }
        } catch (e: Exception) {
            Log.w("DecartBridge", "descarga prenda fallida")
            null
        }
    }

    private fun clasificar(e: Exception): String {
        val t = (e.message ?: "").uppercase()
        if (t.contains("ICE")) return "ERROR_RED_ICE"
        if (t.contains("TIMEOUT")) return "TIMEOUT"
        if (t.contains("MODERAT")) return "MODERACION"
        if (t.contains("API KEY") || t.contains("APIKEY") || t.contains("TOKEN")) return "AUTORIZACION_FALLIDA"
        if (t.contains("SECURITY")) return "TOKEN_INVALIDO"
        return "ERROR_CONEXION"
    }

    /**
     * Cierre nativo real, seguro e idempotente.
     * Puede llamarse desde cualquier hilo y múltiples veces sin excepción ni carrera.
     * Elimina todos los listeners pendientes, quita el renderer del track,
     * libera el renderer, desconecta, libera el cliente y borra referencias.
     * Los callbacks tardíos posteriores al cierre son ignorados vía [cerrado].
     */
    fun cerrarNativo() {
        if (!cerrando.compareAndSet(false, true)) {
            return
        }
        // Marcar cierre primero: cualquier frame tardío se ignora.
        cerrado.set(true)
        try {
            val c = client
            val track = currentTrack
            val captureTrack = localTrack
            val captureStream = localStream
            val r = renderer

            // 1. Eliminar todos los listeners pendientes (evita fugas y
            // emisiones repetidas de primeraTransformacion / prendaAplicada).
            eliminarListeners()

            // 2. Quitar el renderer del video track
            if (track != null && r != null) {
                try {
                    track.removeRenderer(r)
                } catch (_: Exception) {}
            }
            currentTrack = null
            if (captureTrack != null && captureTrack !== track && r != null) {
                try {
                    captureTrack.removeRenderer(r)
                } catch (_: Exception) {}
            }
            localTrack = null

            // 3. Desconectar realtime
            try {
                c?.realtime?.disconnect()
            } catch (_: Exception) {}
            try {
                captureStream?.dispose()
            } catch (_: Exception) {}
            localStream = null

            // 4. Liberar SurfaceViewRenderer en el hilo principal
            if (r != null) {
                mainHandler.post {
                    try {
                        r.release()
                    } catch (_: Exception) {}
                }
            }
            renderer = null
            rendererInicializado.set(false)

            // 5. Liberar cliente Decart
            try {
                c?.release()
            } catch (_: Exception) {}
            client = null

            conectando = false
            primeraTransformacionConfirmada.set(false)
            generandoVisto.set(false)
            conectadoAlgunaVez.set(false)

            // 6. Emitir desconexión
            mainHandler.post {
                try {
                    emit(mapOf("tipo" to "disconnected"))
                } catch (_: Exception) {}
            }
        } finally {
            cerrando.set(false)
        }
    }

    private fun cerrarConexionPreviaConservandoRenderer() {
        cerrado.set(true)
        eliminarListeners()
        val track = currentTrack
        val captureTrack = localTrack
        val captureStream = localStream
        val r = renderer
        if (track != null && r != null) {
            try {
                track.removeRenderer(r)
            } catch (_: Exception) {}
        }
        currentTrack = null
        if (captureTrack != null && captureTrack !== track && r != null) {
            try {
                captureTrack.removeRenderer(r)
            } catch (_: Exception) {}
        }
        localTrack = null
        try {
            client?.realtime?.disconnect()
        } catch (_: Exception) {}
        try {
            captureStream?.dispose()
        } catch (_: Exception) {}
        localStream = null
        try {
            client?.release()
        } catch (_: Exception) {}
        client = null
        conectando = false
        primeraTransformacionConfirmada.set(false)
        generandoVisto.set(false)
        conectadoAlgunaVez.set(false)
    }

    fun destruir() {
        cerrarNativo()
        scope.cancel()
    }
}
