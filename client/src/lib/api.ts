import axios from "axios";
import { useAuthStore } from "@/stores/auth";

/** Axios instance. Vite proxies /api -> FastAPI (see vite.config.ts). */
export const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  // Keep an explicit header: sign-in calls /auth/me with the new token before it's stored.
  if (token && !config.headers.Authorization) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
    }
    return Promise.reject(error);
  },
);
