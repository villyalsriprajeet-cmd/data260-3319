-- HW7 Part 1: users get a unique username and a role for JWT login
USE s3319_rel;
-- new columns; username starts NULL so existing HW4 rows can be filled first
ALTER TABLE users
  ADD COLUMN username VARCHAR(50) NULL AFTER id,
  ADD COLUMN role ENUM('reader', 'writer', 'moderator') NOT NULL DEFAULT 'reader' AFTER password_hash;
UPDATE users SET username = CONCAT(SUBSTRING_INDEX(email, '@', 1), '_', id) WHERE username IS NULL AND id > 0;
-- now every row has one, so make it required and unique
ALTER TABLE users
  MODIFY username VARCHAR(50) NOT NULL,
  ADD CONSTRAINT uq_users_username UNIQUE (username);