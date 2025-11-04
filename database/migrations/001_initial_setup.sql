-- ==========================================
-- MIGRATION 001: Initial Database Setup
-- ==========================================
-- Description: Create initial database and enable required extensions
-- Date: 2025-11-01
-- ==========================================

-- Create database (run this as postgres superuser)
-- This is separated because it needs to be run before connecting to the database

-- Check if database exists
SELECT 'CREATE DATABASE crypto_trading_bot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crypto_trading_bot')\gexec

-- Connect to the database
\c crypto_trading_bot

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Log migration
DO $$
BEGIN
    RAISE NOTICE '✅ Migration 001 completed: Database and extensions created';
END $$;
