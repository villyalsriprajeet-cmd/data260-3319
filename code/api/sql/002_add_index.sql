-- HW4 Part 3: index on venue so fixtures at one venue are found without a full table scan
USE s3319_rel;
CREATE INDEX idx_fixtures_venue ON fixtures (venue);