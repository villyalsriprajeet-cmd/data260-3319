// Header: league name, Home link, and Add Fixture only after login
import React from "react";
import { Link } from "react-router-dom";
export default function Navbar({ loggedIn }) {
  return (
    <header className="site-header">
      <Link to="/" className="site-title"> Community League Fixtures</Link>
      <nav className="site-nav">
        <Link to="/">Home</Link>
        {loggedIn && <Link to="/create">Add Fixture</Link>}
      </nav>
    </header>
  );
}