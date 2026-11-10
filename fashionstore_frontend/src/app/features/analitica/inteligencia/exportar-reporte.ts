import { ReporteInterpretadoResultadoDTO } from '../models/analitica-ia.models';
export type FormatoReporte = 'csv' | 'html' | 'xlsx' | 'pdf';
type Celda = string | number;
const texto = (v: unknown): string => v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v);
const escapar = (v: unknown): string => texto(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export function celdaSegura(v: unknown): Celda {
  if (typeof v === 'number') { if (!Number.isFinite(v)) throw new Error('Importe no válido.'); return v; }
  const s = texto(v);
  if (/^-?(0|[1-9]\d*)(\.\d+)?$/.test(s) && Number.isSafeInteger(Math.round(Number(s) * 100))) return Number(s);
  return /^[\s\u0000-\u001f]*[=+@-]/u.test(s) ? "'" + s : s;
}
function preparar(r: ReporteInterpretadoResultadoDTO, titulo: string) {
  if (!r || !r.consulta_id || !r.generado_en || !Array.isArray(r.columnas) || !r.columnas.length ||
      r.columnas.some(c => typeof c !== 'string' || !c) || new Set(r.columnas).size !== r.columnas.length ||
      !Array.isArray(r.filas) || r.filas.some(f => !f || r.columnas.some(c => !(c in f)))) throw new Error('No hay un resultado completo para exportar.');
  const metadata: [string, string][] = [ ['Título', titulo], ['Generado en', r.generado_en],
    ['Filtros efectivos', texto(r.filtros_efectivos)], ['Origen de datos', r.origen],
    ['Motor', r.proveedor || texto(r.filtros_efectivos?.['proveedor']) || 'DETERMINISTA'],
    ['Origen de explicación', texto(r.filtros_efectivos?.['narrativa_origen']) || 'DETERMINISTA'],
    ['Moneda', texto(r.filtros_efectivos?.['moneda']) || 'BOB (importes en Bs)'], ['Explicación', r.narrativa] ];
  const filas = r.filas.map(f => r.columnas.map(c => celdaSegura(f[c])));
  const totales = Object.entries(r.totales || {}).map(([k,v]) => [k, celdaSegura(v)] as [string, Celda]);
  return { metadata, filas, totales };
}
export async function archivoReporte(r: ReporteInterpretadoResultadoDTO, titulo: string, formato: FormatoReporte): Promise<Blob> {
  const { metadata, filas, totales } = preparar(r, titulo);
  if (formato === 'csv') {
    const citar = (v: unknown) => '"' + texto(celdaSegura(v)).replace(/"/g, '""') + '"';
    const lineas = [...metadata, [], r.columnas, ...filas, [], ['Totales'], ...totales];
    return new Blob(['\ufeff' + lineas.map(f => f.map(citar).join(',')).join('\r\n')], {type:'text/csv;charset=utf-8'});
  }
  if (formato === 'html') {
    return new Blob(['<!doctype html><html lang="es"><meta charset="utf-8"><title>' + escapar(titulo) +
      '</title><body><h1>' + escapar(titulo) + '</h1><dl>' + metadata.map(([k,v]) => '<dt>'+escapar(k)+'</dt><dd>'+escapar(v)+'</dd>').join('') +
      '</dl><table border="1"><thead><tr>' + r.columnas.map(c => '<th>'+escapar(c)+'</th>').join('') + '</tr></thead><tbody>' +
      filas.map(f => '<tr>'+f.map(v => '<td>'+escapar(v)+'</td>').join('')+'</tr>').join('') + '</tbody></table><h2>Totales</h2><dl>' +
      totales.map(([k,v]) => '<dt>'+escapar(k)+'</dt><dd>'+escapar(v)+'</dd>').join('') + '</dl></body></html>'], {type:'text/html;charset=utf-8'});
  }
  if (formato === 'xlsx') {
    const { Workbook } = await import('exceljs');
    const libro = new Workbook();
    libro.addWorksheet('Contexto').addRows(metadata.map(f => f.map(celdaSegura)));
    const hoja = libro.addWorksheet('Datos'); hoja.addRow(r.columnas.map(celdaSegura)); hoja.addRows(filas);
    hoja.views = [{state:'frozen', ySplit:1}]; hoja.columns.forEach(c => c.width = 24);
    libro.addWorksheet('Totales').addRows([['Concepto', 'Valor'], ...totales.map(([k,v]) => [celdaSegura(k),v])]);
    const bytes = await libro.xlsx.writeBuffer();
    return new Blob([new Uint8Array(bytes)], {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
  }
  const { jsPDF } = await import('jspdf');
  const doc = new jsPDF({orientation:'landscape', unit:'mm', format:'a4', compress:false});
  const ancho = doc.internal.pageSize.getWidth(), limite = doc.internal.pageSize.getHeight()-14;
  let y = 14;
  doc.setFontSize(9);
  const parrafo = (s: string) => {
    for (const linea of doc.splitTextToSize(s, ancho-24) as string[]) {
      if (y+5 > limite) { doc.addPage(); y=14; }
      doc.text(linea,12,y); y+=5;
    }
  };
  metadata.forEach(([k,v]) => parrafo(k+': '+v)); y+=4;
  const celdaAncho = (ancho-24)/r.columnas.length;
  const cabecera = () => { doc.setFont('helvetica','bold'); r.columnas.forEach((c,i) => doc.text(doc.splitTextToSize(c,celdaAncho-3),12+i*celdaAncho,y)); y += Math.max(...r.columnas.map(c => doc.splitTextToSize(c,celdaAncho-3).length))*4+4; doc.setFont('helvetica','normal'); };
  if (y > limite-20) { doc.addPage(); y=14; } cabecera();
  for (const fila of filas) {
    const lineas = fila.map(v => doc.splitTextToSize(texto(v), celdaAncho-3) as string[]);
    const alto = Math.max(...lineas.map(l => l.length));
    let inicio=0;
    while (inicio < alto) {
      if (y+6 > limite) { doc.addPage(); y=14; cabecera(); }
      const cantidad = Math.min(alto-inicio, Math.max(1,Math.floor((limite-y-2)/4)));
      lineas.forEach((l,i) => { const segmento=l.slice(inicio,inicio+cantidad); if (segmento.length) doc.text(segmento,12+i*celdaAncho,y); });
      y+=cantidad*4+2; inicio+=cantidad;
    }
  }
  y+=4; parrafo('Totales'); totales.forEach(([k,v]) => parrafo(k+': '+texto(v)));
  return new Blob([doc.output('arraybuffer')], {type:'application/pdf'});
}
export function descargarReporte(blob: Blob, nombre: string): void {
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  try { link.href=url; link.download=nombre; document.body.appendChild(link); link.click(); }
  finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
}
