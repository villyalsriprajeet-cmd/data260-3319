// Delete page at "/delete/:id": shows the fixture, deleting goes through the onDelete prop
import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { fetchFixtureById } from "../api/fixturesApi.js";
export default function DeleteRecord({ onDelete }) {
  const fixtureId = Number(useParams().id); // id from the URL
  const [fixture, setFixture] = useState(null);
  // Load the fixture so the user sees what will be removed
  useEffect(() => {
    fetchFixtureById(fixtureId).then(setFixture).catch(() => setFixture(null));
  }, [fixtureId]);
  if (!fixture) {
    return <section className="panel"><p className="muted">Fixture not found.</p></section>;
  }
  return (
    <section className="panel danger-panel">
      <h2>Delete Fixture #{fixtureId}</h2>
      <p>{fixture.fixture_title} at {fixture.venue}</p>
      <button className="btn btn-red" onClick={() => onDelete(fixtureId)}>Delete Fixture</button>
    </section>
  );
}