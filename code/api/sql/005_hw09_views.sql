-- HW9 Part 1: view count of each fixture, written by the Redis counter every 10 views
USE s3319_rel;
ALTER TABLE fixtures ADD COLUMN views INT NOT NULL DEFAULT 0 AFTER tickets_available;
