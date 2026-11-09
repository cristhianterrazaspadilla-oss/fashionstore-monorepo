export type DecimalApi = string | number;

// Literales cerrados

export interface Pagina<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}
