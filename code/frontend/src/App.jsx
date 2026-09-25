// Main app: login state, fixture list, routes, and the CRUD handlers passed as props
import React, { useEffect, useState } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import Navbar from "./components/Navbar.jsx";
import Login from "./components/Login.jsx";
import Home from "./pages/Home.jsx";
import CreateRecord from "./pages/CreateRecord.jsx";
import UpdateRecord from "./pages/UpdateRecord.jsx";
import DeleteRecord from "./pages/DeleteRecord.jsx";
import { fetchFixtures, createFixture, updateFixture, deleteFixture } from "./api/fixturesApi.js";
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
  const navigate = useNavigate();
  const [loggedIn, setLoggedIn] = useState(false); // true once the backend accepts our cookie
  const [fixtures, setFixtures] = useState([]); // records shown on Home
  // Load the list; 200 means the session cookie is valid, 401 means not logged in
  useEffect(() => {
    fetchFixtures()
      .then((data) => {
        setFixtures(data);
        setLoggedIn(true);
      })
      .catch(() => {
        setFixtures([]);
        setLoggedIn(false);
      });
  }, [loggedIn]);
  // Create, passed to CreateRecord as a prop
  async function onAdd(newFixture) {
    const created = await createFixture(newFixture); // MySQL assigns the auto-increment id
    setFixtures([...fixtures, created]);
    navigate("/");
  }
  // Update, passed to UpdateRecord as a prop
  async function onUpdate(id, changes) {
    const updated = await updateFixture(id, changes);
    setFixtures(fixtures.map((f) => (f.id === id ? updated : f)));
    navigate("/");
  }
  // Delete, passed to DeleteRecord as a prop
  async function onDelete(id) {
    await deleteFixture(id);
    setFixtures(fixtures.filter((f) => f.id !== id));
    navigate("/");
  }
  return (
    <>
      <Navbar loggedIn={loggedIn} />
      <main className="page">
        <Login loggedIn={loggedIn} setLoggedIn={setLoggedIn} />
        <Routes>
          <Route path="/" element={<Home fixtures={fixtures} loggedIn={loggedIn} />} />
          <Route path="/create" element={<Protected loggedIn={loggedIn}><CreateRecord onAdd={onAdd} /></Protected>} />
          <Route path="/update/:id" element={<Protected loggedIn={loggedIn}><UpdateRecord onUpdate={onUpdate} /></Protected>} />
          <Route path="/delete/:id" element={<Protected loggedIn={loggedIn}><DeleteRecord onDelete={onDelete} /></Protected>} />
        </Routes>
      </main>
    </>
  );
}