// Calls to the FastAPI backend on port 8619
import axios from "axios";
const api = axios.create({
  baseURL: "http://localhost:8619",
  withCredentials: true, // send and receive the HttpOnly session cookie
});
export async function login(email, password) {
  const res = await api.post("/login", { email, password });
  return res.data;
}
export async function fetchFixtures() {
  const res = await api.get("/fixtures");
  return res.data;
}
export async function fetchFixtureById(id) {
  const res = await api.get(`/fixtures/${id}`);
  return res.data;
}
export async function createFixture(payload) {
  const res = await api.post("/fixtures", payload);
  return res.data;
}
export async function updateFixture(id, payload) {
  const res = await api.put(`/fixtures/${id}`, payload);
  return res.data;
}
export async function deleteFixture(id) {
  const res = await api.delete(`/fixtures/${id}`);
  return res.data;
}
