-- Authentik Database Setup for MariaDB
-- Run this script on your MariaDB instance to create the necessary database and user

-- Create the authentik database
CREATE DATABASE IF NOT EXISTS authentik CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create authentik user (replace 'your-strong-password' with the password from your secret)
CREATE USER IF NOT EXISTS 'authentik'@'%' IDENTIFIED BY 'your-strong-password';

-- Grant permissions to authentik user
GRANT ALL PRIVILEGES ON authentik.* TO 'authentik'@'%';

-- Flush privileges
FLUSH PRIVILEGES;

-- Verify the setup
SELECT 'Database created successfully' AS status;
SHOW DATABASES LIKE 'authentik';
SELECT User, Host FROM mysql.user WHERE User = 'authentik';