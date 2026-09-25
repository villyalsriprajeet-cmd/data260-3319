// Login: email + password; the backend answers with an HttpOnly session cookie
import React, { useState } from "react";
import { login } from "../api/fixturesApi.js";
export default function Login({ loggedIn, setLoggedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  async function handleSubmit(e) {
    e.preventDefault();
    try {
      await login(email, password); // the browser keeps the cookie, our code never reads it
      setError("");
      setLoggedIn(true);
    } catch {
      setError("Invalid email or password");
    }
  }
  if (loggedIn) {
    return <p className="status">Logged in</p>;
  }
  return (
    <section className="panel login-panel">
      <h2>Login required</h2>
      <form className="login-form" onSubmit={handleSubmit}>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <button type="submit" className="btn btn-green">Login</button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  );
}