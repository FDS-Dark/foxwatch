import axios from 'axios'

/**
 * Relative paths work in dev (Vite proxy) and can be overridden for split
 * api/client deployments via VITE_API_BASE_URL at build time.
 */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
})
