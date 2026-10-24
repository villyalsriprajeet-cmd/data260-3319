// Login: username + password; HW7 backend answers with a JWT kept in sessionStorage
import React, { useState } from "react";
import { login } from "../api/fixturesApi.js";
export default function Login({ loggedIn, setLoggedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  async function handleSubmit(e) {
    e.preventDefault();
    try {
      await login(username, password); // token saved, sent as a Bearer header from now on
      setError("");
      setLoggedIn(true);
    } catch {
      setError("Invalid username or password");
    }
  }
  if (loggedIn) {
    return <p className="status">Logged in</p>;
  }
  return (
    <section className="panel login-panel">
      <h2>Login required</h2>
      <form className="login-form" onSubmit={handleSubmit}>
        <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <button type="submit" className="btn btn-green">Login</button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  );
}