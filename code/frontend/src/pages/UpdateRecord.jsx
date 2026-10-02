// Update page at "/update" or "/update/:id": pick a fixture by ID, edit it, dispatch the update thunk
import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { fetchFixtureById } from "../api/fixturesApi.js";
import { clearError, updateFixture } from "../features/fixtures/fixturesSlice.js";
const EMPTY = { fixture_title: "", fixture_code: "", venue: "", tickets_available: 0, home_team_id: 1 };
export default function UpdateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const params = useParams();
  const error = useSelector((state) => state.fixtures.error);
  const [id, setId] = useState(params.id || ""); // the ID the user selects
  const [form, setForm] = useState(EMPTY);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  useEffect(() => { dispatch(clearError()); }, [dispatch]); // start without an old error
  async function loadFixture(fixtureId) {
    try {
      const f = await fetchFixtureById(fixtureId); // fill the form with the saved values
      setForm({ fixture_title: f.fixture_title, fixture_code: f.fixture_code, venue: f.venue,
                tickets_available: f.tickets_available, home_team_id: f.home_team_id });
      setLoaded(true);
      setLoadError("");
    } catch {
      setLoaded(false);
      setLoadError(`Fixture ${fixtureId} not found`);
    }
  }
  useEffect(() => { if (params.id) { setId(params.id); loadFixture(params.id); } }, [params.id]); // came from a Home row
  function onChange(e) {
    const { name, value, type } = e.target;
    setForm({ ...form, [name]: type === "number" ? Number(value) : value });
  }
  async function handleSubmit(e) {
    e.preventDefault();
    try {
      await dispatch(updateFixture({ id: Number(id), changes: form })).unwrap(); // PUT through Redux
      navigate("/"); // Home shows the updated row from Redux
    } catch {
      // the error message is already in Redux state
    }
  }
  return (
    <section className="panel">
      <h2>Update Fixture</h2>
      <div className="login-form">
        <input type="number" placeholder="Fixture ID" value={id} onChange={(e) => { setId(e.target.value); setLoaded(false); }} />
        <button type="button" className="btn btn-outline" onClick={() => loadFixture(id)} disabled={!id}>Load</button>
      </div>
      {loadError && <p className="error">{loadError}</p>}
      {loaded && (
        <form className="fixture-form form-gap" onSubmit={handleSubmit}>
          <label>Fixture title<input name="fixture_title" value={form.fixture_title} onChange={onChange} required /></label>
          <label>Fixture code<input name="fixture_code" value={form.fixture_code} onChange={onChange} required /></label>
          <label>Venue<input name="venue" value={form.venue} onChange={onChange} required /></label>
          <label>Tickets available<input type="number" name="tickets_available" value={form.tickets_available} onChange={onChange} required /></label>
          <label>Home team ID<input type="number" name="home_team_id" value={form.home_team_id} onChange={onChange} required /></label>
          <button type="submit" className="btn btn-green">Update Fixture #{id}</button>
        </form>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}