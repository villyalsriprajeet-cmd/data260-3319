// Axios client for the FastAPI backend on port 8619
import axios from "axios";
export const api = axios.create({
  baseURL: "http://localhost:8619",
  withCredentials: true, // send and receive the HttpOnly session cookie
});
export async function login(email, password) {
  const res = await api.post("/login", { email, password });
  return res.data;
}
export async function fetchFixtureById(id) {
  const res = await api.get(`/fixtures/${id}`);
  return res.data;
}