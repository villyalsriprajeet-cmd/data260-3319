// Create page at "/create": the form dispatches the create thunk, then goes back to Home
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { clearError, createFixture } from "../features/fixtures/fixturesSlice.js";
export default function CreateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const error = useSelector((state) => state.fixtures.error);
  const [form, setForm] = useState({ fixture_title: "", fixture_code: "", venue: "", tickets_available: 500, home_team_id: 1 });
  useEffect(() => { dispatch(clearError()); }, [dispatch]); // start without an old error
  function onChange(e) {
    const { name, value, type } = e.target;
    setForm({ ...form, [name]: type === "number" ? Number(value) : value }); // numbers stay numbers
  }
  async function handleSubmit(e) {
    e.preventDefault();
    try {
      await dispatch(createFixture(form)).unwrap(); // throws if the API rejected it
      navigate("/"); // Home already shows the new record from Redux
    } catch {
      // the error message is already in Redux state
    }
  }
  return (
    <section className="panel">
      <h2>New Fixture</h2>
      <form className="fixture-form" onSubmit={handleSubmit}>
        <label>Fixture title<input name="fixture_title" value={form.fixture_title} onChange={onChange} required /></label>
        <label>Fixture code (FX-12345)<input name="fixture_code" value={form.fixture_code} onChange={onChange} required /></label>
        <label>Venue<input name="venue" value={form.venue} onChange={onChange} required /></label>
        <label>Tickets available<input type="number" name="tickets_available" value={form.tickets_available} onChange={onChange} required /></label>
        <label>Home team ID<input type="number" name="home_team_id" value={form.home_team_id} onChange={onChange} required /></label>
        <button type="submit" className="btn btn-green">Add Fixture</button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  );
}