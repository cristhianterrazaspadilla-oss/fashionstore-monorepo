import { HttpHeaders, HttpParams } from '@angular/common/http';

export function cabeceraIdempotencia(clave?: string): HttpHeaders {
  return new HttpHeaders({ 'Idempotency-Key': clave || crypto.randomUUID() });
}

export function parametrosHttp(valores: Record<string, unknown>): HttpParams {
  let parametros = new HttpParams();
  Object.entries(valores).forEach(([clave, valor]) => {
    if (valor !== undefined && valor !== null && valor !== '') {
      parametros = parametros.set(clave, String(valor));
    }
  });
  return parametros;
}
