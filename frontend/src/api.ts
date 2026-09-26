import axios from "axios";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const KEY = "smartfix_token";

export const api = axios.create({ baseURL: `${BASE}/api`, timeout: 20000 });

async function getToken() {
  if (Platform.OS === "web") {
    if (typeof localStorage === "undefined") return null;
    return localStorage.getItem(KEY);
  }
  return SecureStore.getItemAsync(KEY);
}
export async function saveToken(v: string | null) {
  if (Platform.OS === "web") {
    if (typeof localStorage === "undefined") return;
    if (v) localStorage.setItem(KEY, v); else localStorage.removeItem(KEY);
    return;
  }
  if (v) await SecureStore.setItemAsync(KEY, v);
  else await SecureStore.deleteItemAsync(KEY);
}

api.interceptors.request.use(async (c) => {
  const t = await getToken();
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});

export function errMsg(e: any): string {
  return e?.response?.data?.detail || e?.message || "Something went wrong";
}
