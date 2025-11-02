# Database Integration Guide

## Understanding the Why (Theory of Mind)

### Why Add a Database?

**You might be thinking:** "The in-memory storage works fine. Why add complexity?"

**Here's the reality:**
- **In-memory is temporary**: When your app restarts, all data is lost. For a real sentiment analysis system, you want to build historical data.
- **You want to track trends**: "How did sentiment for AAPL change over the last 30 days?" - This requires persistent storage.
- **Multiple instances**: When you scale to multiple servers, they need to share the same data.
- **Analytics matter**: Complex queries like "Which stocks had the biggest sentiment shift this week?" need a real database.

**What you're gaining:**
- Historical sentiment tracking
- Ability to analyze trends over time
- Proper data persistence
- Support for scaling to multiple servers
- Advanced query capabilities

## Step-by-Step Setup (With Context)

### Step 1: Understanding PostgreSQL + pgvector

**What you're installing:** PostgreSQL with the pgvector extension.

**Why PostgreSQL?**
- Industry standard, battle-tested
- Excellent JSON support for metadata
- ACID compliance (your data stays consistent)
- Great indexing for fast queries

**Why pgvector?**
- You'll store embeddings (768-dimensional vectors) for each post
- pgvector makes similarity search fast: "Find posts similar to this one"
- Without it, you'd need a separate vector database (more complexity)

**What this enables:**
```
"Find all posts about AAPL with similar sentiment to this one"
→ This is semantic search, not just keyword matching
```

### Step 2: The Schema Design (Each Table Explained)

**You might wonder:** "Why so many tables? Can't I just dump everything in one?"

**Here's the reasoning:**

#### `social_posts` - The Core Data
**What it stores:** Every social media post we collect
**Why separate:** This is your source of truth. Everything else derives from it.
**Key insight:** We use (source, platform_id) as a unique constraint because:
  - Different platforms use different ID formats
  - A post from Reddit with ID "abc123" is different from Twitter's "abc123"
  - This prevents duplicate ingestion

#### `post_embeddings` - The Semantic Layer
**What it stores:** Vector representations of posts (768 numbers per post)
**Why separate:**
  - Embeddings are large (3KB+ per post)
  - Not every post needs an embedding
  - Makes it optional and doesn't bloat the main table
**Key insight:** Using VECTOR(768) type from pgvector enables fast similarity search

#### `sentiment` - The Analysis Results
**What it stores:** Sentiment scores (polarity, subjectivity, sarcasm)
**Why separate:**
  - You might re-score posts with better models
  - Keeps analysis separate from raw data
  - Allows multiple sentiment models side-by-side
**Key insight:** The `model` field lets you track which algorithm produced each score

#### `resolver_cache` - The Performance Boost
**What it stores:** Symbol lookups (e.g., "Apple" → "AAPL")
**Why separate:**
  - Symbol resolution can be slow (API calls)
  - Cache hits save time and money
  - 7-day expiration balances freshness vs performance
**Key insight:** This is a classic cache pattern - optimize the slow operation

#### `source_accounts` - The Metadata
**What it stores:** Information about who's posting
**Why separate:**
  - Track follower counts over time
  - Identify influential accounts
  - Filter bot accounts
**Key insight:** Helps you weight sentiment by account influence

### Step 3: Indexes (The Speed Secret)

**You might think:** "Indexes are advanced. Can I skip them?"

**Reality check:** Without indexes, your queries will be SLOW.

**What each index does:**

```sql
CREATE INDEX idx_social_posts_symbols ON social_posts USING GIN (symbols);
```
**Why GIN index?**
- `symbols` is an array: `['AAPL', 'TSLA']`
- GIN indexes are designed for arrays
- Makes "find all posts mentioning AAPL" super fast
- Without this: Database scans EVERY row (slow)
- With this: Database jumps straight to matches (fast)

```sql
CREATE INDEX idx_social_posts_created ON social_posts (created_at DESC);
```
**Why DESC order?**
- Most queries want recent posts first
- `DESC` means "newest first" is pre-sorted
- Makes "last 24 hours of posts" instant
- Without this: Database sorts on every query (slow)

```sql
CREATE INDEX idx_social_posts_source_created ON social_posts (source, created_at DESC);
```
**Why composite index?**
- Queries often filter by BOTH source AND time
- "Show me Reddit posts from last week"
- Composite index serves both conditions at once
- Much faster than two separate indexes

### Step 4: Connection Pooling (Preventing Bottlenecks)

**You might ask:** "Why not just connect to the database directly?"

**The problem:**
- Opening a database connection is SLOW (100ms+)
- Your API might handle 100 requests/second
- If each request opens a new connection: 💥 Disaster
- Database has a connection limit (usually 100)

**The solution: Connection pooling**
```python
# Without pool: Every request connects
request → open connection → query → close connection (SLOW!)

# With pool: Reuse connections
request → grab from pool → query → return to pool (FAST!)
```

**What you're configuring:**
- `min_size=2`: Always keep 2 connections ready (fast first requests)
- `max_size=10`: Never exceed 10 connections (respect DB limits)
- Connections are shared across all requests

### Step 5: Migrations (Evolving Your Schema)

**You might wonder:** "Can't I just modify the schema file?"

**The problem:**
- Production database already has data
- You can't just DROP and recreate tables
- Need to ADD a column, not rebuild everything

**The solution: Migration system**
```python
# migrations/001_initial_schema.sql - Applied once
# migrations/002_add_retweet_count.sql - Applied next
# migrations/003_add_sentiment_index.sql - Applied after
```

**How it works:**
1. System tracks which migrations ran: `applied_migrations` table
2. On startup: Run any new migrations
3. Never re-runs old migrations (safe!)
4. Lets you evolve schema over time

### Step 6: Health Checks (Know When Things Break)

**You might think:** "If it crashes, I'll know."

**Reality:** Databases fail in subtle ways:
- Connection pool exhausted
- Disk full
- Locks causing slowdowns
- Replication lag

**The solution: Health monitoring**
```python
GET /healthz/db
→ {
  "status": "healthy",
  "connections_used": 3,
  "connections_available": 7,
  "query_time_ms": 2.5
}
```

**What you're checking:**
1. Can we connect? (Basic availability)
2. Can we query? (Database is responsive)
3. How fast? (Performance degradation)
4. Pool status? (Connection exhaustion)

### Step 7: Error Handling (Graceful Degradation)

**You might ask:** "What if the database is down?"

**The approach:**
```python
# Don't crash the whole app
try:
    db.query(...)
except DatabaseError:
    logger.error("Database unavailable")
    # Fall back to in-memory
    # OR return cached results
    # OR return error with retry-after
```

**Why this matters:**
- Partial functionality > complete failure
- Users get some response vs timeout
- Gives you time to fix the issue

## Common Questions (Anticipated)

### Q: "Do I HAVE to use PostgreSQL?"
**A:** No, but it's recommended. The code abstracts the database layer, so you could swap it out. But PostgreSQL + pgvector is the best-supported path.

### Q: "Can I start with in-memory and switch later?"
**A:** Yes! That's exactly the design. Set `USE_POSTGRES=false` initially, then flip it to `true` when ready.

### Q: "What if I already have a PostgreSQL server?"
**A:** Perfect! Just point `DATABASE_URL` to it. No Docker needed.

### Q: "How much data can this handle?"
**A:** PostgreSQL can handle millions of posts. The limiting factor is usually query design and indexing, which we've optimized.

### Q: "What about backups?"
**A:** You'll need to set up PostgreSQL backups separately. Standard approach: `pg_dump` on a schedule.

### Q: "Can I see the data?"
**A:** Yes! Use any PostgreSQL client:
- CLI: `psql -h localhost -U user -d sentiment`
- GUI: pgAdmin, DBeaver, TablePlus, etc.

## Next Steps

1. Review the schema in `app/storage/schemas.sql`
2. Check the migration system in `app/storage/migrations.py`
3. Look at connection pooling in `app/storage/db_pool.py`
4. Run the setup: `docker-compose up -d`
5. Verify: `python verify_db.py`

## Troubleshooting (Predictive)

### "Connection refused"
**Likely cause:** PostgreSQL not running
**Fix:** `docker-compose up -d` or check if your PostgreSQL server is started

### "Password authentication failed"
**Likely cause:** Wrong credentials in `.env`
**Fix:** Match `DATABASE_URL` to your actual PostgreSQL user/password

### "Database does not exist"
**Likely cause:** Database not created
**Fix:** `docker-compose down && docker-compose up -d` (recreates everything)

### "Queries are slow"
**Likely cause:** Missing indexes or not using them correctly
**Fix:** Check query EXPLAIN plans, ensure you're filtering on indexed columns

### "Too many connections"
**Likely cause:** Connection pool exhausted or not closing connections
**Fix:** Check pool settings, look for connection leaks in code

## Philosophy

This guide follows **theory of mind** principles:
- **Explains WHY, not just WHAT**: You understand the reasoning
- **Anticipates questions**: Answers before you ask
- **Provides context**: You see how pieces fit together
- **Assumes good intent**: You're learning, not expected to know everything
- **Empowers decisions**: You can modify based on your needs

Ready to proceed with the integration!
