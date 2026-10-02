// Main app: login state and routes, fixture data lives in the Redux store
import React, { useEffect, useState } from "react";
import { Routes, Route } from "react-router-dom";
import { useDispatch } from "react-redux";
import Navbar from "./components/Navbar.jsx";
import Login from "./components/Login.jsx";
import Home from "./pages/Home.jsx";
import CreateRecord from "./pages/CreateRecord.jsx";
import UpdateRecord from "./pages/UpdateRecord.jsx";
import { fetchFixtures } from "./features/fixtures/fixturesSlice.js";
// Shows the page only when logged in
function Protected({ loggedIn, children }) {
  if (!loggedIn) {
    return (
      <section className="panel">
        <h2>Login required</h2>
        <p className="muted">Log in above to manage fixtures.</p>
      </section>
    );
  }
  return children;
}
export default function App() {
  const dispatch = useDispatch();
  const [loggedIn, setLoggedIn] = useState(false); // true once the backend accepts our cookie
  // Load the first page into Redux; success means the session cookie is valid
  useEffect(() => {
    dispatch(fetchFixtures(0))
      .unwrap()
      .then(() => setLoggedIn(true))
      .catch(() => setLoggedIn(false));
  }, [dispatch, loggedIn]);
  return (
    <>
      <Navbar loggedIn={loggedIn} />
      <main className="page">
        <Login loggedIn={loggedIn} setLoggedIn={setLoggedIn} />
        <Routes>
          <Route path="/" element={<Home loggedIn={loggedIn} />} />
          <Route path="/create" element={<Protected loggedIn={loggedIn}><CreateRecord /></Protected>} />
          <Route path="/update" element={<Protected loggedIn={loggedIn}><UpdateRecord /></Protected>} />
          <Route path="/update/:id" element={<Protected loggedIn={loggedIn}><UpdateRecord /></Protected>} />
        </Routes>
      </main>
    </>
  );
}