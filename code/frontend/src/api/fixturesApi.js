// Axios client for the FastAPI backend on port 8619; HW7: JWT bearer token instead of the session cookie
import axios from "axios";
const TOKEN_KEY = "s3319_token";
export const api = axios.create({ baseURL: "http://localhost:8619" });
export function getToken() {
  try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function logout() {
  try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
}
// every request carries "Authorization: Bearer <token>" when we have one
api.interceptors.request.use((cfg) => {
  const token = getToken();
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});
export async function login(username, password) {
  const form = new URLSearchParams({ username, password }); // OAuth2 form fields
  const res = await api.post("/auth/login", form);
  try { sessionStorage.setItem(TOKEN_KEY, res.data.access_token); } catch { /* storage blocked */ }
  return res.data;
}
export async function fetchMe() {
  const res = await api.get("/auth/me");
  return res.data;
}
export async function fetchFixtureById(id) {
  const res = await api.get(`/fixtures/${id}`);
  return res.data;
}