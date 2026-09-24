-- HW4 schema for Domain 7 (Community sports league fixtures)
CREATE DATABASE IF NOT EXISTS s3319_rel CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE s3319_rel;
-- login accounts, password stored only as a hash
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL
);
-- server side sessions, the cookie only holds this id
CREATE TABLE IF NOT EXISTS sessions (
  id VARCHAR(64) PRIMARY KEY,
  user_id INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME NOT NULL,
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
-- related table, filled with 200 seeded rows in Part 3
CREATE TABLE IF NOT EXISTS teams (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  city VARCHAR(100) NOT NULL
);
-- primary domain entity: id, primary field, secondary field
CREATE TABLE IF NOT EXISTS fixtures (
  id INT AUTO_INCREMENT PRIMARY KEY,
  fixture_title VARCHAR(200) NOT NULL,
  venue VARCHAR(200) NOT NULL,
  home_team_id INT NULL,
  CONSTRAINT fk_fixtures_team FOREIGN KEY (home_team_id) REFERENCES teams(id) ON DELETE SET NULL
);