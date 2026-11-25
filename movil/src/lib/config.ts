const rawApiUrl = process.env.EXPO_PUBLIC_API_URL?.trim() || 'http://10.0.2.2:8000/api/v1';

export const API_URL = rawApiUrl.replace(/\/+$/, '');
export const GOOGLE_WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID?.trim() ?? '';
