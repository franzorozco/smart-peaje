export type Rol = 'administrador' | 'operador';

export interface Usuario {
  id: number;
  email: string;
  nombre: string;
  rol: Rol;
}

export interface AuthGoogleResponse {
  access: string;
  refresh: string;
  rol: Rol;
  usuario: Usuario;
}

export interface AuthRefreshResponse {
  access: string;
  refresh?: string;
}

export type EstadoPaso = 'pagado' | 'sin_saldo' | 'no_registrado' | 'inactivo' | 'revision';

export type CategoriaVehiculo = 'moto' | 'auto' | 'minibus' | 'camion' | 'bus';

export interface Caseta {
  id: number;
  nombre: string;
  ubicacion: string;
}

export interface Paso {
  id: number;
  captura_id: string;
  placa_leida: string;
  placa_normalizada: string;
  confianza_ocr: number | null;
  categoria_detectada: string;
  ejes_detectados: number;
  pasajeros: number | null;
  monto: string;
  caseta: number;
  caseta_nombre: string;
  usuario_email: string;
  imagen: string | null;
  estado: EstadoPaso;
  latencia_ms: number;
  created_at: string;
}

export interface PasoFrameResponse {
  nuevo: boolean;
  paso: Paso;
  saldo_restante: string | null;
}

export interface UltimoPasoResumen {
  fecha: string;
  caseta: string;
  categoria: string;
  monto: string;
  estado_pago: EstadoPaso | string;
}

export interface VehiculoConsulta {
  placa: string;
  categoria: string;
  ejes: number;
  activo: boolean;
}

export interface LecturaImagen {
  placa: string;
  placa_cruda: string;
  confianza: number;
}

export type EstadoConsultaPlaca =
  | 'Registrada y con paso'
  | 'Registrada sin paso'
  | 'Identificada no registrada'
  | 'No existe';

export interface ConsultaPlacaPayload {
  placa?: string;
  formato_valido?: boolean;
  estado?: EstadoConsultaPlaca | string | null;
  vehiculo?: VehiculoConsulta | null;
  ultimo_paso?: UltimoPasoResumen | null;
  total_pasos?: number;
  sugerencias?: string[];
  mensaje?: string;
  lectura?: LecturaImagen;
  total?: number;
  pasos?: Paso[];
}

export type AgenteChatTool = 'consultar_placa' | 'consultar_imagen' | 'historial' | 'aclaracion';

export interface AgenteChatResponse {
  respuesta: string;
  tool: AgenteChatTool;
  estado: string | null;
  datos: ConsultaPlacaPayload | null;
  sugerencias: string[];
  requiere: null | 'placa' | 'imagen';
}

export interface ApiErrorBody {
  error?: string;
  detail?: string;
  requiere_nueva_captura?: boolean;
  legible?: boolean;
}

export interface ArchivoCaptura {
  uri: string;
  name: string;
  type: string;
}
