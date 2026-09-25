// Home page at "/": the full fixture list for logged in users
import React from "react";
import { Link } from "react-router-dom";
export default function Home({ fixtures, loggedIn }) {
  if (!loggedIn) return null; // the Login panel above shows "Login required"
  return (
    <section className="panel">
      <h2>Fixtures ({fixtures.length})</h2>
      {fixtures.length === 0 ? (
        <p className="muted">No fixtures yet.</p>
      ) : (
        <table className="fixture-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Fixture</th>
              <th>Venue</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {fixtures.map((f) => (
              <tr key={f.id}>
                <td>{f.id}</td>
                <td>{f.fixture_title}</td>
                <td>{f.venue}</td>
                <td className="row-actions">
                  <Link to={`/update/${f.id}`} className="btn btn-outline">Update</Link>
                  <Link to={`/delete/${f.id}`} className="btn btn-red">Delete</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}