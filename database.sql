-- ==========================================================
-- PARKVOICE AI: Smart Parking & Navigation Database Schema
-- Compatible with MySQL 5.7+ / 8.0+ and MariaDB 10.4+
-- ==========================================================

CREATE DATABASE IF NOT EXISTS `parkvoice_ai`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `parkvoice_ai`;

-- Drop existing tables if needed (in proper foreign key dependency order)
DROP TABLE IF EXISTS `parking_history`;
DROP TABLE IF EXISTS `bookings`;
DROP TABLE IF EXISTS `parking_slots`;
DROP TABLE IF EXISTS `vehicles`;
DROP TABLE IF EXISTS `users`;
DROP TABLE IF EXISTS `admins`;

-- ----------------------------------------------------------
-- 1. USERS TABLE
-- ----------------------------------------------------------
CREATE TABLE `users` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `full_name` VARCHAR(100) NOT NULL,
  `email` VARCHAR(120) NOT NULL UNIQUE,
  `password_hash` VARCHAR(255) NOT NULL,
  `phone` VARCHAR(20) DEFAULT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------
-- 2. VEHICLES TABLE
-- ----------------------------------------------------------
CREATE TABLE `vehicles` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `plate_number` VARCHAR(30) NOT NULL UNIQUE,
  `vehicle_type` ENUM('Car', 'SUV', 'Bike', 'EV') NOT NULL DEFAULT 'Car',
  `model` VARCHAR(100) NOT NULL,
  `is_default` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  INDEX `idx_vehicles_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------
-- 3. PARKING SLOTS TABLE (4x3 Grid P01 - P12)
-- ----------------------------------------------------------
CREATE TABLE `parking_slots` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `slot_number` VARCHAR(10) NOT NULL UNIQUE,
  `row_index` INT NOT NULL,
  `col_index` INT NOT NULL,
  `slot_type` ENUM('Standard', 'Compact', 'EV', 'Disabled') NOT NULL DEFAULT 'Standard',
  `has_ev_charger` TINYINT(1) NOT NULL DEFAULT 0,
  `status` ENUM('AVAILABLE', 'OCCUPIED', 'RESERVED') NOT NULL DEFAULT 'AVAILABLE',
  `price_per_hour` DECIMAL(6, 2) NOT NULL DEFAULT 5.00,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_slots_status` (`status`),
  INDEX `idx_slots_number` (`slot_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------
-- 4. BOOKINGS TABLE (Double-booking prevention at DB level)
-- ----------------------------------------------------------
CREATE TABLE `bookings` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `booking_code` VARCHAR(20) NOT NULL UNIQUE,
  `user_id` INT NOT NULL,
  `vehicle_id` INT NOT NULL,
  `slot_id` INT NOT NULL,
  `start_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `end_time` DATETIME DEFAULT NULL,
  `status` ENUM('ACTIVE', 'COMPLETED', 'CANCELLED') NOT NULL DEFAULT 'ACTIVE',
  `total_amount` DECIMAL(8, 2) NOT NULL DEFAULT 0.00,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`vehicle_id`) REFERENCES `vehicles`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`slot_id`) REFERENCES `parking_slots`(`id`) ON DELETE CASCADE,
  INDEX `idx_bookings_user_status` (`user_id`, `status`),
  INDEX `idx_bookings_slot_status` (`slot_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------
-- 5. PARKING HISTORY TABLE
-- ----------------------------------------------------------
CREATE TABLE `parking_history` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `booking_id` INT NOT NULL,
  `user_id` INT NOT NULL,
  `vehicle_id` INT NOT NULL,
  `slot_id` INT NOT NULL,
  `check_in` DATETIME NOT NULL,
  `check_out` DATETIME NOT NULL,
  `duration_minutes` INT NOT NULL DEFAULT 0,
  `fee_paid` DECIMAL(8, 2) NOT NULL DEFAULT 0.00,
  `status` VARCHAR(20) NOT NULL DEFAULT 'COMPLETED',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`booking_id`) REFERENCES `bookings`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`vehicle_id`) REFERENCES `vehicles`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`slot_id`) REFERENCES `parking_slots`(`id`) ON DELETE CASCADE,
  INDEX `idx_history_user_date` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------
-- 6. ADMINS TABLE
-- ----------------------------------------------------------
CREATE TABLE `admins` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `username` VARCHAR(60) NOT NULL UNIQUE,
  `email` VARCHAR(120) NOT NULL UNIQUE,
  `password_hash` VARCHAR(255) NOT NULL,
  `role` VARCHAR(30) NOT NULL DEFAULT 'superadmin',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_admins_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==========================================================
-- SEED DATA
-- ==========================================================

-- Seed Parking Slots (4 rows x 3 cols: P01 to P12)
-- Row 0
INSERT INTO `parking_slots` (`slot_number`, `row_index`, `col_index`, `slot_type`, `has_ev_charger`, `status`, `price_per_hour`) VALUES
('P01', 0, 0, 'EV', 1, 'AVAILABLE', 6.00),
('P02', 0, 1, 'EV', 1, 'AVAILABLE', 6.00),
('P03', 0, 2, 'Standard', 0, 'AVAILABLE', 5.00),
-- Row 1
('P04', 1, 0, 'Standard', 0, 'AVAILABLE', 5.00),
('P05', 1, 1, 'Compact', 0, 'AVAILABLE', 4.00),
('P06', 1, 2, 'Standard', 0, 'AVAILABLE', 5.00),
-- Row 2
('P07', 2, 0, 'Standard', 0, 'AVAILABLE', 5.00),
('P08', 2, 1, 'Compact', 0, 'AVAILABLE', 4.00),
('P09', 2, 2, 'EV', 1, 'AVAILABLE', 6.00),
-- Row 3
('P10', 3, 0, 'Standard', 0, 'AVAILABLE', 5.00),
('P11', 3, 1, 'Standard', 0, 'AVAILABLE', 5.00),
('P12', 3, 2, 'Standard', 0, 'AVAILABLE', 5.00);

-- Seed Default Admin: username 'admin', email 'admin@parkvoice.ai', password 'Admin@123'
INSERT INTO `admins` (`username`, `email`, `password_hash`, `role`) VALUES
('admin', 'admin@parkvoice.ai', 'scrypt:32768:8:1$y1VKQKjNJ7l4HTrg$f6dae97dd6f1d68f2ac9523504f9dd52f6accbe98608bf1bc3fd7d02c28206d2f69438cbafe4b576ae3d4d70b45e3a5a4fb317ee8601eb900fff7a007a80b7c5', 'superadmin');

-- Seed Demo User: email 'demo@parkvoice.ai', password 'User@123'
INSERT INTO `users` (`full_name`, `email`, `password_hash`, `phone`) VALUES
('Alex Rivers', 'demo@parkvoice.ai', 'scrypt:32768:8:1$3RVWBgEghWcgJZFs$c8aaa6d7e993325b31cd75996b05b48a3a69ded5729acb278154a015b9ea97f1eca51874c9f1a726ffc230242ce34fe40507471181af48350877aabb12974a60', '+1 (555) 019-2834');

-- Seed Demo User Vehicles
INSERT INTO `vehicles` (`user_id`, `plate_number`, `vehicle_type`, `model`, `is_default`) VALUES
(1, 'MH 12 AB 1234', 'Car', 'Honda Civic (Silver)', 1),
(1, 'MH 14 EV 9999', 'EV', 'Tesla Model 3 (Midnight Silver)', 0),
(1, 'MH 01 BK 5555', 'Bike', 'Royal Enfield Hunter 350', 0);

-- Seed Past Sample Bookings & History for Analytics
INSERT INTO `bookings` (`id`, `booking_code`, `user_id`, `vehicle_id`, `slot_id`, `start_time`, `end_time`, `status`, `total_amount`, `created_at`) VALUES
(1, 'PV-1001', 1, 1, 3, DATE_SUB(NOW(), INTERVAL 3 DAY), DATE_SUB(NOW(), INTERVAL 70 HOUR), 'COMPLETED', 10.00, DATE_SUB(NOW(), INTERVAL 3 DAY)),
(2, 'PV-1002', 1, 2, 1, DATE_SUB(NOW(), INTERVAL 2 DAY), DATE_SUB(NOW(), INTERVAL 46 HOUR), 'COMPLETED', 12.00, DATE_SUB(NOW(), INTERVAL 2 DAY)),
(3, 'PV-1003', 1, 1, 7, DATE_SUB(NOW(), INTERVAL 1 DAY), DATE_SUB(NOW(), INTERVAL 22 HOUR), 'COMPLETED', 10.00, DATE_SUB(NOW(), INTERVAL 1 DAY)),
(4, 'PV-1004', 1, 3, 5, DATE_SUB(NOW(), INTERVAL 5 HOUR), DATE_SUB(NOW(), INTERVAL 4 HOUR), 'COMPLETED', 4.00, DATE_SUB(NOW(), INTERVAL 5 HOUR));

INSERT INTO `parking_history` (`booking_id`, `user_id`, `vehicle_id`, `slot_id`, `check_in`, `check_out`, `duration_minutes`, `fee_paid`, `status`, `created_at`) VALUES
(1, 1, 1, 3, DATE_SUB(NOW(), INTERVAL 3 DAY), DATE_SUB(NOW(), INTERVAL 70 HOUR), 120, 10.00, 'COMPLETED', DATE_SUB(NOW(), INTERVAL 70 HOUR)),
(2, 1, 2, 1, DATE_SUB(NOW(), INTERVAL 2 DAY), DATE_SUB(NOW(), INTERVAL 46 HOUR), 120, 12.00, 'COMPLETED', DATE_SUB(NOW(), INTERVAL 46 HOUR)),
(3, 1, 1, 7, DATE_SUB(NOW(), INTERVAL 1 DAY), DATE_SUB(NOW(), INTERVAL 22 HOUR), 120, 10.00, 'COMPLETED', DATE_SUB(NOW(), INTERVAL 22 HOUR)),
(4, 1, 3, 5, DATE_SUB(NOW(), INTERVAL 5 HOUR), DATE_SUB(NOW(), INTERVAL 4 HOUR), 60, 4.00, 'COMPLETED', DATE_SUB(NOW(), INTERVAL 4 HOUR));
