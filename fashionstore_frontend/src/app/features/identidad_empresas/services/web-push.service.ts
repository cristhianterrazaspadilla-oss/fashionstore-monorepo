import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, from, of, catchError, switchMap } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { obtenerDispositivoId } from '../../../core/utils/bolivia-time.util';

export interface RegistroDispositivoDTO {
  dispositivo_id: string;
  canal: 'PWA' | 'FLUTTER';
  push_token?: string;
  sucursal_id?: string | null;
}

export interface DispositivoDTO {
  id: string;
  dispositivo_id: string;
  canal: string;
  estado: string;
  creado_en: string;
}

export interface WebPushConfigDTO {
  public_key: string;
}

export interface WebPushKeysDTO {
  p256dh: string;
  auth: string;
}

export interface WebPushSubscriptionDTO {
  endpoint: string;
  keys: WebPushKeysDTO;
  dispositivo_id?: string;
}

export interface WebPushSubscriptionResponseDTO {
  id?: string;
  dispositivo_id?: string;
  canal?: string;
  endpoint?: string;
  estado?: string;
  mensaje?: string;
  creado_en?: string;
}

@Injectable({
  providedIn: 'root'
})
export class WebPushService {
  private readonly apiUrl = `${environment.apiUrl}/notificaciones/dispositivos`;
  private readonly configUrl = `${environment.apiUrl}/notificaciones/web-push/config`;
  private readonly subscripcionUrl = `${environment.apiUrl}/notificaciones/web-push/subscripcion`;

  constructor(private http: HttpClient) {}

  /**
   * Consulta la clave pública VAPID configurada en el servidor central.
   */
  obtenerConfigWebPush(): Observable<WebPushConfigDTO> {
    return this.http.get<WebPushConfigDTO>(this.configUrl);
  }

  /**
   * Registra la suscripción Web Push completa (endpoint, p256dh, auth y dispositivo_id)
   * en un único registro ante el servidor.
   */
  registrarSuscripcionWebPush(dto: WebPushSubscriptionDTO): Observable<DispositivoDTO> {
    return this.http.post<DispositivoDTO>(this.subscripcionUrl, dto);
  }

  /**
   * Registra el Service Worker real en el navegador si está disponible.
   */
  async registrarServiceWorker(scriptUrl = '/custom-sw.js'): Promise<ServiceWorkerRegistration | null> {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
      return null;
    }
    try {
      const reg = await navigator.serviceWorker.register(scriptUrl);
      return reg;
    } catch (err) {
      console.warn('No se pudo registrar el service worker:', err);
      return null;
    }
  }

  /**
   * Verifica si el navegador soporta Service Worker, PushManager y Notification.
   */
  estaSoportado(): boolean {
    return (
      typeof window !== 'undefined' &&
      'serviceWorker' in navigator &&
      'PushManager' in window &&
      'Notification' in window
    );
  }

  /**
   * Obtiene el estado actual del permiso de notificaciones del navegador.
   */
  obtenerPermiso(): NotificationPermission | 'unsupported' {
    if (!this.estaSoportado()) {
      return 'unsupported';
    }
    return Notification.permission;
  }

  /**
   * Solicita permiso al usuario para enviar notificaciones web.
   */
  async solicitarPermiso(): Promise<NotificationPermission | 'unsupported'> {
    if (!this.estaSoportado()) {
      return 'unsupported';
    }
    try {
      return await Notification.requestPermission();
    } catch {
      return 'denied';
    }
  }

  /**
   * Registra o actualiza el dispositivo ante el backend en /api/v1/notificaciones/dispositivos.
   */
  registrarDispositivo(dto: RegistroDispositivoDTO): Observable<DispositivoDTO> {
    return this.http.post<DispositivoDTO>(this.apiUrl, dto);
  }

  /**
   * Revoca el registro del dispositivo ante el backend en /api/v1/notificaciones/dispositivos/{id}.
   */
  revocarDispositivo(dispositivoId?: string): Observable<void> {
    const id = dispositivoId || obtenerDispositivoId();
    return this.http.delete<void>(`${this.apiUrl}/${id}`);
  }

  /**
   * Revoca la suscripción Web Push asociada al dispositivo_id estable.
   */
  revocarSuscripcion(dispositivoId?: string): Observable<void> {
    return this.revocarDispositivo(dispositivoId);
  }

  /**
   * Configura o suscribe al Push API (Web Push) en el navegador si está soportado,
   * y envía la suscripción resultante al backend en un ÚNICO registro ante /notificaciones/web-push/subscripcion.
   * Propaga errores hacia el suscriptor en caso de fallas de suscripción.
   */
  suscribirWebPush(opciones?: {
    applicationServerKey?: string;
    sucursalId?: string | null;
  }): Observable<DispositivoDTO | null> {
    if (!this.estaSoportado()) {
      return of(null);
    }

    const obtenerClave$: Observable<string> = opciones?.applicationServerKey
      ? of(opciones.applicationServerKey)
      : this.obtenerConfigWebPush().pipe(
          switchMap(cfg => of(cfg.public_key))
        );

    return obtenerClave$.pipe(
      switchMap((key) => from(this.obtenerOSuscribirPush(key))),
      switchMap((suscripcion) => {
        if (!suscripcion) {
          return of(null);
        }

        const jsonSub = suscripcion.toJSON ? suscripcion.toJSON() : ({} as any);
        const p256dh = jsonSub.keys?.p256dh || '';
        const auth = jsonSub.keys?.auth || '';

        const webPushDto: WebPushSubscriptionDTO = {
          endpoint: suscripcion.endpoint,
          keys: {
            p256dh,
            auth
          },
          dispositivo_id: obtenerDispositivoId()
        };

        // Único registro llamando a registrarSuscripcionWebPush enviando el dispositivo_id estable
        return this.registrarSuscripcionWebPush(webPushDto);
      })
    );
  }

  /**
   * Lógica interna para registrar SW y obtener una suscripción activa o crear una nueva con el PushManager.
   */
  async obtenerOSuscribirPush(applicationServerKey?: string): Promise<PushSubscription | null> {
    if (!this.estaSoportado()) return null;

    let permiso = Notification.permission;
    if (permiso === 'default') {
      permiso = await Notification.requestPermission();
    }
    if (permiso !== 'granted') {
      return null;
    }

    try {
      let reg: ServiceWorkerRegistration | undefined = await navigator.serviceWorker.getRegistration();
      if (!reg) {
        reg = (await this.registrarServiceWorker()) || undefined;
      }
      if (!reg) {
        reg = await navigator.serviceWorker.ready;
      }
      if (!reg || !reg.pushManager) return null;

      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        const subOptions: PushSubscriptionOptionsInit = {
          userVisibleOnly: true
        };
        if (applicationServerKey) {
          subOptions.applicationServerKey = this.urlBase64ToUint8Array(applicationServerKey);
        }
        sub = await reg.pushManager.subscribe(subOptions);
      }
      return sub;
    } catch {
      return null;
    }
  }

  /**
   * Convierte clave pública VAPID en base64 URL-safe a Uint8Array.
   */
  urlBase64ToUint8Array(base64String: string): Uint8Array {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }
}
