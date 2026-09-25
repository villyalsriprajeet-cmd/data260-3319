// Update page at "/update/:id": loads the fixture, saving goes through the onUpdate prop
import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { fetchFixtureById } from "../api/fixturesApi.js";
export default function UpdateRecord({ onUpdate }) {
  const fixtureId = Number(useParams().id); // id from the URL
  const [fixtureTitle, setFixtureTitle] = useState("");
  const [venue, setVenue] = useState("");
  // Fill the inputs with the saved values
  useEffect(() => {
    fetchFixtureById(fixtureId).then((f) => {
      setFixtureTitle(f.fixture_title);
      setVenue(f.venue);
    });
  }, [fixtureId]);
  function handleSubmit(e) {
    e.preventDefault();
    onUpdate(fixtureId, { fixture_title: fixtureTitle, venue: venue }); // parent PUTs and redirects home
  }
  return (
    <section className="panel">
      <h2>Update Fixture #{fixtureId}</h2>
      <form className="fixture-form" onSubmit={handleSubmit}>
        <label>Fixture title<input value={fixtureTitle} onChange={(e) => setFixtureTitle(e.target.value)} required /></label>
        <label>Venue<input value={venue} onChange={(e) => setVenue(e.target.value)} required /></label>
        <button type="submit" className="btn btn-green">Update Fixture</button>
      </form>
    </section>
  );
}