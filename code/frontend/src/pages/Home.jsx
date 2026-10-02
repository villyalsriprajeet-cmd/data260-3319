// Home page: reads the fixture list from Redux, delete button dispatches the delete thunk
import React from "react";
import { Link } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { deleteFixture, fetchFixtures, PAGE_SIZE } from "../features/fixtures/fixturesSlice.js";
export default function Home({ loggedIn }) {
  const dispatch = useDispatch();
  const { items, skip, loading, error } = useSelector((state) => state.fixtures); // data comes from the store
  if (!loggedIn) return null; // the Login panel above shows "Login required"
  return (
    <section className="panel">
      <h2>Fixtures (newest first, rows {skip + 1}–{skip + items.length})</h2>
      {loading && <p className="muted">Loading...</p>}
      {error && <p className="error">{error}</p>}
      <table className="fixture-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Code</th>
            <th>Fixture</th>
            <th>Venue</th>
            <th>Tickets</th>
            <th>Team</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((f) => (
            <tr key={f.id}>
              <td>{f.id}</td>
              <td className="nowrap">{f.fixture_code}</td>
              <td>{f.fixture_title}</td>
              <td>{f.venue}</td>
              <td>{f.tickets_available}</td>
              <td>{f.home_team_id}</td>
              <td>
                <div className="row-actions">
                  <Link to={`/update/${f.id}`} className="btn btn-outline">Update</Link>
                  <button className="btn btn-red" onClick={() => dispatch(deleteFixture(f.id))}>Delete</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pager">
        <button className="btn btn-outline" disabled={skip === 0}
          onClick={() => dispatch(fetchFixtures(Math.max(skip - PAGE_SIZE, 0)))}>Previous</button>
        <button className="btn btn-outline" disabled={items.length < PAGE_SIZE}
          onClick={() => dispatch(fetchFixtures(skip + PAGE_SIZE))}>Next</button>
      </div>
    </section>
  );
}