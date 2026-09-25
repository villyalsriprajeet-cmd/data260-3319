// Create page at "/create": title and venue inputs, saving goes through the onAdd prop
import React, { useState } from "react";
export default function CreateRecord({ onAdd }) {
  const [fixtureTitle, setFixtureTitle] = useState("");
  const [venue, setVenue] = useState("");
  function handleSubmit(e) {
    e.preventDefault();
    onAdd({ fixture_title: fixtureTitle, venue: venue }); // parent POSTs and redirects home
  }
  return (
    <section className="panel">
      <h2>New Fixture</h2>
      <form className="fixture-form" onSubmit={handleSubmit}>
        <label>Fixture title<input value={fixtureTitle} onChange={(e) => setFixtureTitle(e.target.value)} required /></label>
        <label>Venue<input value={venue} onChange={(e) => setVenue(e.target.value)} required /></label>
        <button type="submit" className="btn btn-green">Add Fixture</button>
      </form>
    </section>
  );
}