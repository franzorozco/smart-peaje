import {
  GoogleSignin,
  isCancelledResponse,
  isErrorWithCode,
  statusCodes,
} from '@react-native-google-signin/google-signin';
import { create as createAxios, isAxiosError, type InternalAxiosRequestConfig } from 'axios';

import { API_URL, GOOGLE_WEB_CLIENT_ID } from './config';
import {
  clearAuthStorage,
  getAccessToken,
  getRefreshToken,
  setStoredUsuario,
  setTokens,
} from './storage';
import type {
  AgenteChatResponse,
  ApiErrorBody,
  ArchivoCaptura,
  AuthGoogleResponse,
  AuthRefreshResponse,
  Caseta,
  PasoFrameResponse,
  Usuario,
} from './types';

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

export class ApiError extends Error {
  status: number;
  data?: ApiErrorBody;

  constructor(message: string, status: number, data?: ApiErrorBody) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export class AuthCancelledError extends Error {
  constructor() {
    super('Inicio de sesión cancelado');
    this.name = 'AuthCancelledError';
  }
}

let sessionExpiredHandler: (() => void) | null = null;

export function setOnSessionExpired(handler: (() => void) | null): void {
  sessionExpiredHandler = handler;
}

function extractErrorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === 'object') {
    const body = data as ApiErrorBody;
    if (typeof body.error === 'string' && body.error.trim().length > 0) {
      return body.error;
    }
    if (typeof body.detail === 'string' && body.detail.trim().length > 0) {
      return body.detail;
    }
  }
  return fallback;
}

export function toApiError(error: unknown, fallback = 'Error de conexión con el servidor'): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  if (isAxiosError(error)) {
    const status = error.response?.status ?? 0;
    const data = error.response?.data as ApiErrorBody | undefined;
    if (status === 503) {
      return new ApiError(
        extractErrorMessage(data, 'Servicio de inferencia no disponible'),
        503,
        data
      );
    }
    if (status === 0) {
      return new ApiError('No se pudo conectar con el servidor. Verifica la red.', 0);
    }
    return new ApiError(extractErrorMessage(data, fallback), status, data);
  }
  if (error instanceof Error) {
    return new ApiError(error.message || fallback, 0);
  }
  return new ApiError(fallback, 0);
}

export const api = createAxios({
  baseURL: API_URL,
  timeout: 20000,
  headers: {
    Accept: 'application/json',
  },
});

let refreshPromise: Promise<string | null> | null = null;

export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refresh = await getRefreshToken();
      if (!refresh) {
        await clearAuthStorage();
        sessionExpiredHandler?.();
        return null;
      }

      try {
        const response = await api.post<AuthRefreshResponse>(
          '/auth/refresh',
          { refresh },
          { timeout: 15000 }
        );
        const newAccess = response.data.access;
        const newRefresh = response.data.refresh ?? refresh;
        await setTokens(newAccess, newRefresh);
        return newAccess;
      } catch {
        await clearAuthStorage();
        sessionExpiredHandler?.();
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
  }

  return refreshPromise;
}

api.interceptors.request.use(async (config) => {
  const url = config.url ?? '';
  if (url.endsWith('auth/google') || url.endsWith('auth/refresh')) {
    return config;
  }

  const token = await getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!isAxiosError(error) || !error.config) {
      return Promise.reject(error);
    }

    const originalConfig = error.config as RetriableRequestConfig;
    const status = error.response?.status;
    const url = originalConfig.url ?? '';

    if (
      status === 401 &&
      !originalConfig._retry &&
      !url.endsWith('auth/google') &&
      !url.endsWith('auth/refresh')
    ) {
      originalConfig._retry = true;
      const newAccess = await refreshAccessToken();
      if (newAccess) {
        originalConfig.headers.Authorization = `Bearer ${newAccess}`;
        return api(originalConfig);
      }
    }

    return Promise.reject(error);
  }
);

export async function entrar(): Promise<Usuario> {
  if (!GOOGLE_WEB_CLIENT_ID) {
    throw new Error('Falta configurar EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID.');
  }

  GoogleSignin.configure({
    webClientId: GOOGLE_WEB_CLIENT_ID,
  });

  try {
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    const signInResult = await GoogleSignin.signIn();

    if (isCancelledResponse(signInResult)) {
      throw new AuthCancelledError();
    }

    const idToken = signInResult.data.idToken;
    if (!idToken) {
      throw new Error('Google no entregó el token de identidad (idToken).');
    }

    const response = await api.post<AuthGoogleResponse>('/auth/google', {
      id_token: idToken,
    });

    const { access, refresh, rol, usuario } = response.data;
    const usuarioNormalizado: Usuario = {
      ...usuario,
      rol: usuario.rol ?? rol,
    };

    await setTokens(access, refresh);
    await setStoredUsuario(usuarioNormalizado);
    return usuarioNormalizado;
  } catch (error) {
    if (error instanceof AuthCancelledError) {
      throw error;
    }

    if (isErrorWithCode(error)) {
      if (error.code === statusCodes.SIGN_IN_CANCELLED) {
        throw new AuthCancelledError();
      }
      if (error.code === statusCodes.IN_PROGRESS) {
        throw new Error('Ya hay un inicio de sesión en curso.');
      }
      if (error.code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) {
        throw new Error('Google Play Services no está disponible o requiere actualización.');
      }
      throw new Error(`Error de Google Sign-In (${error.code}): ${error.message}`);
    }

    if (isAxiosError(error)) {
      const apiErr = toApiError(error, 'No se pudo iniciar sesión');
      if (apiErr.status === 401 || apiErr.status === 403) {
        await GoogleSignin.signOut().catch(() => {});
      }
      throw apiErr;
    }

    throw error instanceof Error ? error : new Error('No se pudo iniciar sesión');
  }
}

export async function salir(): Promise<void> {
  await clearAuthStorage();
  await GoogleSignin.signOut().catch(() => {});
}

export async function obtenerMe(): Promise<Usuario> {
  const response = await api.get<Usuario>('/auth/me');
  await setStoredUsuario(response.data);
  return response.data;
}

export async function listarCasetas(): Promise<Caseta[]> {
  const response = await api.get<Caseta[]>('/casetas/');
  return response.data;
}

function normalizeUploadUri(uri: string): string {
  const trimmed = (uri || '').trim();
  if (!trimmed) return trimmed;
  if (/^(file|content|ph|assets-library|https?):\/\//i.test(trimmed)) {
    return trimmed;
  }
  return trimmed.startsWith('/') ? `file://${trimmed}` : trimmed;
}

interface XhrResult {
  status: number;
  text: string;
}

function sendMultipartXhr(
  url: string,
  formData: FormData,
  token: string | null,
  timeoutMs: number
): Promise<XhrResult> {
  return new Promise<XhrResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.timeout = timeoutMs;
    xhr.setRequestHeader('Accept', 'application/json');
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }

    xhr.onload = () => {
      resolve({
        status: xhr.status,
        text: typeof xhr.responseText === 'string' ? xhr.responseText : '',
      });
    };

    xhr.ontimeout = () => {
      reject(new ApiError('Tiempo de espera agotado al enviar la captura.', 0));
    };

    xhr.onerror = () => {
      const detalle =
        typeof xhr.responseText === 'string' && xhr.responseText.trim()
          ? ` (${xhr.responseText.trim().slice(0, 120)})`
          : '';
      reject(
        new ApiError(
          `Error de red al enviar archivo al servidor${detalle}. Verifica tu conexión.`,
          0
        )
      );
    };

    try {
      xhr.send(formData);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Fallo al preparar el envío';
      reject(new ApiError(`No se pudo enviar la captura: ${msg}`, 0));
    }
  });
}

function parseXhrJson<T>(res: XhrResult): T {
  let parsed: unknown = null;
  if (res.text) {
    try {
      parsed = JSON.parse(res.text);
    } catch {
      parsed = null;
    }
  }

  if (res.status < 200 || res.status >= 300) {
    const data = parsed && typeof parsed === 'object' ? (parsed as ApiErrorBody) : undefined;
    const fallback =
      res.status === 503
        ? 'Servicio de inferencia no disponible'
        : `Error del servidor (${res.status})`;
    throw new ApiError(extractErrorMessage(data, fallback), res.status, data);
  }

  return parsed as T;
}

async function fetchMultipartWithAuthRetry<T>(
  path: string,
  buildFormData: () => FormData,
  timeoutMs = 90000
): Promise<T> {
  const url = `${API_URL}${path}`;
  let token = await getAccessToken();
  let res = await sendMultipartXhr(url, buildFormData(), token, timeoutMs);

  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      token = refreshed;
      res = await sendMultipartXhr(url, buildFormData(), token, timeoutMs);
    }
  }

  return parseXhrJson<T>(res);
}

export async function enviarCapturaCaseta(params: {
  file: ArchivoCaptura;
  capturaId: string;
  casetaId: number;
}): Promise<PasoFrameResponse> {
  return fetchMultipartWithAuthRetry<PasoFrameResponse>(
    '/pasos/frame',
    () => {
      const formData = new FormData();
      formData.append('file', {
        uri: normalizeUploadUri(params.file.uri),
        name: params.file.name,
        type: params.file.type,
      } as unknown as Blob);
      formData.append('captura_id', params.capturaId);
      formData.append('caseta_id', String(params.casetaId));
      return formData;
    },
    90000
  );
}

export async function enviarConsultaTexto(mensaje: string): Promise<AgenteChatResponse> {
  try {
    const response = await api.post<AgenteChatResponse>('/agente/chat', { mensaje });
    return response.data;
  } catch (error) {
    throw toApiError(error, 'No se pudo procesar la consulta');
  }
}

export async function enviarConsultaImagen(
  file: ArchivoCaptura,
  mensaje?: string
): Promise<AgenteChatResponse> {
  return fetchMultipartWithAuthRetry<AgenteChatResponse>(
    '/agente/chat',
    () => {
      const formData = new FormData();
      formData.append('file', {
        uri: normalizeUploadUri(file.uri),
        name: file.name,
        type: file.type,
      } as unknown as Blob);
      if (mensaje && mensaje.trim().length > 0) {
        formData.append('mensaje', mensaje.trim());
      }
      return formData;
    },
    60000
  );
}
