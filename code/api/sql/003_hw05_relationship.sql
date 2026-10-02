-- HW5 Part 1: teams become the related entity, fixtures get a code, ticket count, timestamps and a RESTRICT foreign key
USE s3319_rel;
-- teams: add the unique contact email and timestamps
ALTER TABLE teams
  ADD COLUMN contact_email VARCHAR(255) NULL AFTER city,
  ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
-- give the 200 seeded teams an email built from their unique name
UPDATE teams SET contact_email = CONCAT(LOWER(REPLACE(name, ' ', '.')), '@s3319league.org') WHERE id > 0;
-- now every team has one, so make it required and unique
ALTER TABLE teams
  MODIFY contact_email VARCHAR(255) NOT NULL,
  ADD CONSTRAINT uq_teams_contact_email UNIQUE (contact_email);
-- fixtures: add the unique code, the ticket count with a default, and timestamps
ALTER TABLE fixtures
  ADD COLUMN fixture_code VARCHAR(20) NULL AFTER fixture_title,
  ADD COLUMN tickets_available INT NOT NULL DEFAULT 500 AFTER venue,
  ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
-- give the 5,000 seeded fixtures a code like FX-00001 and a repeatable ticket count between 0 and 500
UPDATE fixtures SET fixture_code = CONCAT('FX-', LPAD(id, 5, '0')), tickets_available = MOD(id * 37, 501) WHERE id > 0;
-- drop the old SET NULL foreign key so it can be recreated as RESTRICT
ALTER TABLE fixtures DROP FOREIGN KEY fk_fixtures_team;
--  every fixture must have a home team, tickets never negative
ALTER TABLE fixtures
  MODIFY fixture_code VARCHAR(20) NOT NULL,
  MODIFY home_team_id INT NOT NULL,
  ADD CONSTRAINT uq_fixtures_code UNIQUE (fixture_code),
  ADD CONSTRAINT chk_fixtures_tickets CHECK (tickets_available >= 0),
  ADD CONSTRAINT fk_fixtures_team FOREIGN KEY (home_team_id) REFERENCES teams(id) ON DELETE RESTRICT;