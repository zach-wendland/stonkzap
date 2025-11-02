-- Migration 001: Initial Database Schema
-- Created: 2025-10-28
--
-- WHY THIS MIGRATION:
-- Sets up the foundational database structure for the Sentiment Bot.
-- This creates all tables needed to store social media posts, sentiment
-- analysis, embeddings, and caching.
--
-- WHAT YOU'RE GETTING:
-- - Tables for posts, sentiment scores, embeddings
-- - Proper indexes for fast queries
-- - Symbol resolution caching
-- - Account tracking
--
-- THEORY OF MIND:
-- You might wonder "Why so many tables?" - The answer is separation of concerns.
-- Each table has a specific purpose, making the system modular and maintainable.

-- ============================================================================
-- EXTENSION: pgvector for embedding storage
-- ============================================================================
-- WHY: Enables storing 768-dimensional vectors (embeddings) efficiently
-- WHAT IT DOES: Adds VECTOR data type and similarity search operators
-- IF YOU SEE AN ERROR: Make sure pgvector is installed in PostgreSQL
CREATE EXTENSION IF NOT EXISTS vector;


-- ============================================================================
-- TABLE: source_accounts
-- PURPOSE: Track social media accounts we've seen
-- ============================================================================
-- WHY SEPARATE TABLE:
-- - Track account metadata over time (follower growth)
-- - Identify influential accounts
-- - Filter known bot accounts
-- - Weight sentiment by account influence
--
-- KEY INSIGHT: (source, author_id) combination is unique
-- Same author_id on different platforms = different accounts
CREATE TABLE IF NOT EXISTS source_accounts (
    source TEXT NOT NULL,           -- Platform: 'reddit', 'x', 'stocktwits', etc.
    author_id TEXT NOT NULL,        -- Platform-specific user ID
    handle TEXT,                    -- Username/display name (@elonmusk)
    follower_count INT,             -- Number of followers (influence metric)
    last_seen TIMESTAMPTZ DEFAULT NOW(),  -- When we last saw this account
    PRIMARY KEY (source, author_id)
);

-- USAGE EXAMPLE:
-- INSERT INTO source_accounts (source, author_id, handle, follower_count)
-- VALUES ('x', '12345', 'elonmusk', 150000000);


-- ============================================================================
-- TABLE: social_posts
-- PURPOSE: Store all social media posts we collect
-- ============================================================================
-- WHY THIS IS THE CORE TABLE:
-- - Everything else references this
-- - It's your source of truth
-- - All other tables are derived from this data
--
-- KEY DESIGN DECISIONS:
-- 1. UNIQUE (source, platform_id): Same post_id on different platforms is OK
-- 2. symbols array: A post can mention multiple tickers ["AAPL", "TSLA"]
-- 3. created_at vs ingested_at: When post was made vs when we got it
CREATE TABLE IF NOT EXISTS social_posts (
    id BIGSERIAL PRIMARY KEY,       -- Internal ID (auto-incrementing)
    source TEXT NOT NULL,            -- Where it came from
    platform_id TEXT NOT NULL,       -- Platform's ID for this post
    author_id TEXT NOT NULL,         -- Who posted it
    created_at TIMESTAMPTZ NOT NULL, -- When user created the post
    ingested_at TIMESTAMPTZ DEFAULT NOW(),  -- When WE collected it
    text TEXT NOT NULL,              -- The actual post content
    symbols TEXT[] NOT NULL DEFAULT '{}',   -- Ticker symbols mentioned
    urls TEXT[] DEFAULT '{}',        -- Links in the post
    lang TEXT,                       -- Language code (en, es, etc.)
    reply_to_id TEXT,                -- If it's a reply, what to?
    repost_of_id TEXT,               -- If it's a retweet/share
    like_count INT,                  -- Engagement metrics
    reply_count INT,
    repost_count INT,
    follower_count INT,              -- Author's followers at time of post
    permalink TEXT,                  -- Direct link to original post
    UNIQUE (source, platform_id)     -- Can't import same post twice
);

-- USAGE EXAMPLE:
-- INSERT INTO social_posts (source, platform_id, author_id, created_at, text, symbols)
-- VALUES ('x', '1234567890', 'user123', NOW(), '$AAPL to the moon!', ARRAY['AAPL']);


-- ============================================================================
-- TABLE: post_embeddings
-- PURPOSE: Store vector embeddings for semantic similarity search
-- ============================================================================
-- WHY SEPARATE FROM social_posts:
-- - Embeddings are large (~3KB each)
-- - Not every post needs an embedding
-- - Can re-generate with better models later
-- - Optional feature doesn't bloat main table
--
-- WHAT IS AN EMBEDDING:
-- A 768-number representation of the post's meaning.
-- Similar posts have similar embeddings (mathematically close in 768D space).
--
-- WHAT YOU CAN DO:
-- - "Find posts similar to this one"
-- - "Cluster posts by topic"
-- - "Which posts are outliers?"
CREATE TABLE IF NOT EXISTS post_embeddings (
    post_pk BIGINT PRIMARY KEY REFERENCES social_posts(id) ON DELETE CASCADE,
    emb VECTOR(768)                 -- 768-dimensional embedding vector
);

-- USAGE EXAMPLE:
-- Find similar posts using cosine similarity:
-- SELECT post_pk, 1 - (emb <=> target_embedding) AS similarity
-- FROM post_embeddings
-- ORDER BY emb <=> target_embedding
-- LIMIT 10;


-- ============================================================================
-- TABLE: sentiment
-- PURPOSE: Store sentiment analysis results
-- ============================================================================
-- WHY SEPARATE FROM social_posts:
-- - Sentiment is derived, not raw data
-- - Might run multiple models (can track via 'model' field)
-- - Can re-score posts without touching original data
-- - Keeps analysis separate from facts
--
-- WHAT EACH FIELD MEANS:
-- - polarity: -1 (very negative) to +1 (very positive)
-- - subjectivity: 0 (objective fact) to 1 (personal opinion)
-- - sarcasm_prob: 0 (not sarcastic) to 1 (definitely sarcastic)
-- - confidence: How sure is the model? (0 to 1)
CREATE TABLE IF NOT EXISTS sentiment (
    post_pk BIGINT PRIMARY KEY REFERENCES social_posts(id) ON DELETE CASCADE,
    polarity REAL,                  -- Sentiment score (-1 to +1)
    subjectivity REAL,              -- How opinionated (0 to 1)
    sarcasm_prob REAL,              -- Sarcasm detection (0 to 1)
    confidence REAL,                -- Model confidence (0 to 1)
    model TEXT                      -- Which model produced this
);

-- USAGE EXAMPLE:
-- SELECT p.text, s.polarity, s.confidence
-- FROM social_posts p
-- JOIN sentiment s ON s.post_pk = p.id
-- WHERE 'AAPL' = ANY(p.symbols)
-- ORDER BY s.polarity DESC
-- LIMIT 10;


-- ============================================================================
-- TABLE: resolver_cache
-- PURPOSE: Cache symbol resolution lookups
-- ============================================================================
-- WHY THIS MATTERS:
-- - "Apple" → "AAPL" lookup might hit external APIs (slow + costs money)
-- - Cache hits are instant and free
-- - 7-day TTL balances freshness vs performance
--
-- WHAT'S STORED:
-- - query: What user searched for ("apple", "tesla", etc.)
-- - symbol: Normalized ticker ("AAPL", "TSLA")
-- - Other identifiers: CIK, ISIN, FIGI for cross-referencing
--
-- CACHE STRATEGY:
-- - Hit: Instant response
-- - Miss: Look up, then cache for next time
-- - Expire after 7 days (keeps data fresh-ish)
CREATE TABLE IF NOT EXISTS resolver_cache (
    query TEXT PRIMARY KEY,         -- What was searched
    symbol TEXT,                    -- Ticker symbol
    cik TEXT,                       -- SEC Central Index Key
    isin TEXT,                      -- International Securities ID
    figi TEXT,                      -- Financial Instrument Global ID
    company_name TEXT,              -- Official company name
    cached_at TIMESTAMPTZ DEFAULT NOW()  -- When we cached this
);

-- USAGE EXAMPLE:
-- -- Check cache first
-- SELECT symbol FROM resolver_cache
-- WHERE query = 'apple'
-- AND cached_at > NOW() - INTERVAL '7 days';


-- ============================================================================
-- INDEXES: The Secret to Fast Queries
-- ============================================================================
-- THEORY OF MIND:
-- You might think "I'll add indexes when it's slow" - DON'T!
-- By then you have production data and users waiting.
-- Add indexes NOW while it's easy.

-- INDEX 1: Symbol lookups
-- WHAT IT DOES: Makes "find all posts about AAPL" instant
-- WHY GIN: symbols is an ARRAY, GIN indexes are perfect for arrays
-- WITHOUT THIS: Database scans every row (1M rows = slow death)
-- WITH THIS: Database jumps to matches (milliseconds)
CREATE INDEX IF NOT EXISTS idx_social_posts_symbols
ON social_posts USING GIN (symbols);

-- QUERY THIS HELPS:
-- SELECT * FROM social_posts WHERE 'AAPL' = ANY(symbols);

-- INDEX 2: Time-based queries
-- WHAT IT DOES: Makes "posts from last 24 hours" instant
-- WHY DESC: Most queries want newest first
-- WITHOUT THIS: Database sorts on every query
-- WITH THIS: Data is pre-sorted in index
CREATE INDEX IF NOT EXISTS idx_social_posts_created
ON social_posts (created_at DESC);

-- QUERY THIS HELPS:
-- SELECT * FROM social_posts
-- WHERE created_at > NOW() - INTERVAL '24 hours'
-- ORDER BY created_at DESC;

-- INDEX 3: Source + Time (composite)
-- WHAT IT DOES: Makes "show me Reddit posts from this week" instant
-- WHY COMPOSITE: Filters by TWO things (source AND time)
-- BENEFIT: One index serves both conditions
CREATE INDEX IF NOT EXISTS idx_social_posts_source_created
ON social_posts (source, created_at DESC);

-- QUERY THIS HELPS:
-- SELECT * FROM social_posts
-- WHERE source = 'reddit'
-- AND created_at > NOW() - INTERVAL '7 days'
-- ORDER BY created_at DESC;


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- After running this migration, you should be able to run these:

-- Check tables exist:
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public';

-- Check pgvector extension:
-- SELECT * FROM pg_extension WHERE extname = 'vector';

-- Count posts (should be 0 initially):
-- SELECT COUNT(*) FROM social_posts;

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- You now have a production-ready database schema with:
-- ✓ Proper table structure
-- ✓ Foreign key relationships
-- ✓ Performance indexes
-- ✓ Vector search capability
-- ✓ Caching layer
--
-- Next steps:
-- 1. Insert test data
-- 2. Run queries to verify indexes work
-- 3. Monitor query performance
-- 4. Add more migrations as needs evolve
