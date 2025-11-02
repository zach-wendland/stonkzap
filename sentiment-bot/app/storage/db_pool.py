"""
Database Connection Pool

WHY YOU NEED THIS (Theory of Mind):

YOU MIGHT THINK: "Can't I just connect to the database each time?"

THE REALITY:
- Opening a database connection is SLOW (50-100ms)
- Your API might handle 100 requests/second
- 100 requests × 100ms = 10 seconds of just connecting!
- Database has connection limits (usually 100 max)

THE SOLUTION: Connection Pooling
- Keep connections open and reuse them
- Like a taxi stand: taxis wait for passengers (fast!)
- vs calling a new taxi every time (slow!)

WHAT THIS GIVES YOU:
- Fast response times (no connection overhead)
- Efficient resource usage (limited connections)
- Automatic connection management (no leaks!)
- Health monitoring (know when things go wrong)
"""

import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager
import psycopg
from psycopg_pool import ConnectionPool
from app.config import get_settings

logger = logging.getLogger(__name__)


class DatabasePool:
    """
    Manages a pool of database connections.

    ANALOGY:
    Think of this as a parking lot for database connections.
    - min_size: Always keep this many spots filled
    - max_size: Never exceed this many total spots
    - Connections wait if lot is full
    - Connections are returned after use
    """

    def __init__(self, database_url: str, min_size: int = 2, max_size: int = 10):
        """
        Initialize the connection pool.

        PARAMETERS EXPLAINED:
        - min_size=2: Why 2?
          → First 2 requests don't wait for connection creation
          → Keeps pool "warm" even during idle periods
          → Low overhead (just 2 connections)

        - max_size=10: Why 10?
          → Balances parallelism vs database load
          → PostgreSQL default max_connections is 100
          → Leaves room for other apps/admin connections
          → Can adjust based on your needs

        WHAT HAPPENS ON INIT:
        1. Creates the pool (but doesn't connect yet)
        2. Pool lazily creates connections as needed
        3. Maintains min_size connections once warmed up
        """
        self.database_url = database_url
        self.min_size = min_size
        self.max_size = max_size
        self._pool: Optional[ConnectionPool] = None

        logger.info(
            f"Database pool configured: "
            f"min={min_size}, max={max_size}"
        )

    def initialize(self):
        """
        Actually create the connection pool.

        WHY SEPARATE FROM __init__:
        - Allows you to configure first, connect later
        - Easier error handling (connection errors vs config errors)
        - Can retry connection without recreating object

        WHAT HAPPENS:
        - Creates ConnectionPool object
        - Pool opens min_size connections immediately
        - Ready to serve requests
        """
        try:
            self._pool = ConnectionPool(
                self.database_url,
                min_size=self.min_size,
                max_size=self.max_size,
                timeout=30,  # Wait up to 30 seconds for a connection
                max_idle=300,  # Close idle connections after 5 minutes
                max_lifetime=3600,  # Recycle connections after 1 hour
                check=ConnectionPool.check_connection  # Verify connections work
            )

            # Warm up the pool
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")

            logger.info("✓ Database pool initialized and healthy")

        except Exception as e:
            logger.error(f"✗ Failed to initialize database pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """
        Get a connection from the pool (context manager).

        USAGE:
        with pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ...")
                # Connection automatically returned to pool

        WHAT HAPPENS:
        1. Check out a connection from pool
        2. You use it
        3. Automatically returned when done
        4. If error: Connection is still returned (safe!)

        WHY CONTEXT MANAGER (@contextmanager):
        - Guarantees connection is returned (even if your code crashes)
        - Can't forget to close (common bug!)
        - Clean, readable code
        """
        if self._pool is None:
            raise RuntimeError(
                "Pool not initialized! Call initialize() first."
            )

        # Get connection from pool
        connection = None
        try:
            connection = self._pool.getconn()
            yield connection

        except Exception as e:
            logger.error(f"Database error: {e}")
            raise

        finally:
            # Always return connection to pool
            if connection is not None:
                self._pool.putconn(connection)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get pool statistics for monitoring.

        WHAT YOU'RE SEEING:
        - How many connections are in use?
        - How many are available?
        - Is the pool healthy?

        WHEN TO USE:
        - Health check endpoint: GET /healthz/db
        - Monitoring dashboard
        - Debugging performance issues
        - Capacity planning
        """
        if self._pool is None:
            return {
                "status": "not_initialized",
                "error": "Pool has not been initialized"
            }

        try:
            pool_size = self._pool.get_stats()

            return {
                "status": "healthy",
                "pool_size": pool_size["pool_size"],
                "pool_available": pool_size["pool_available"],
                "requests_waiting": pool_size.get("requests_waiting", 0),
                "min_size": self.min_size,
                "max_size": self.max_size,
                "usage_percent": (
                    (pool_size["pool_size"] - pool_size["pool_available"])
                    / self.max_size * 100
                )
            }

        except Exception as e:
            logger.error(f"Failed to get pool stats: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    def close(self):
        """
        Close the pool and all its connections.

        WHEN TO CALL:
        - Application shutdown
        - Testing cleanup
        - Switching database URLs

        WHAT HAPPENS:
        - All connections are closed gracefully
        - Pool releases all resources
        - Subsequent get_connection() calls will fail
        """
        if self._pool:
            try:
                self._pool.close()
                logger.info("Database pool closed")
            except Exception as e:
                logger.error(f"Error closing pool: {e}")

    def health_check(self) -> bool:
        """
        Verify the pool is healthy.

        WHAT'S CHECKED:
        1. Pool exists
        2. Can get a connection
        3. Can execute a query
        4. Connection returns to pool

        RETURNS:
        True if healthy, False if not

        USE IN:
        - Health check endpoints
        - Startup verification
        - Monitoring systems
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    return result[0] == 1

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


# ============================================================================
# Global Pool Instance
# ============================================================================
# WHY GLOBAL:
# - Single pool for entire application
# - Shared across all requests
# - Initialized once at startup
# - Reused throughout app lifetime
#
# PATTERN:
# This is the "singleton" pattern - only one pool exists.
# Every part of your app uses the same pool.

_global_pool: Optional[DatabasePool] = None


def initialize_pool() -> DatabasePool:
    """
    Initialize the global connection pool.

    WHEN THIS RUNS:
    - Application startup (in main.py)
    - Before handling any requests

    WHY:
    - Ensures pool is ready before traffic comes in
    - Validates database connection at startup
    - Fails fast if database is unreachable
    """
    global _global_pool

    settings = get_settings()

    if not settings.use_postgres:
        logger.info("PostgreSQL not enabled, skipping pool initialization")
        return None

    if not settings.database_url:
        raise ValueError("DATABASE_URL not configured")

    logger.info("Initializing database connection pool...")

    _global_pool = DatabasePool(
        database_url=settings.database_url,
        min_size=2,
        max_size=10
    )

    _global_pool.initialize()

    return _global_pool


def get_pool() -> DatabasePool:
    """
    Get the global connection pool.

    USAGE:
    from app.storage.db_pool import get_pool

    pool = get_pool()
    with pool.get_connection() as conn:
        # Use connection

    ERROR HANDLING:
    If pool isn't initialized, raises RuntimeError.
    This prevents silent failures.
    """
    if _global_pool is None:
        raise RuntimeError(
            "Database pool not initialized! "
            "Call initialize_pool() at startup."
        )
    return _global_pool


def close_pool():
    """
    Close the global pool.

    WHEN TO CALL:
    - Application shutdown
    - Testing cleanup

    SAFE TO CALL MULTIPLE TIMES:
    Won't crash if pool is already closed.
    """
    global _global_pool

    if _global_pool:
        _global_pool.close()
        _global_pool = None


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

def example_usage():
    """
    Examples of how to use the connection pool.

    YOU DON'T RUN THIS - it's just for reference!
    """

    # Example 1: Initialize at startup
    pool = initialize_pool()

    # Example 2: Use a connection
    with pool.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM social_posts LIMIT 10")
            posts = cur.fetchall()

    # Example 3: Check pool health
    is_healthy = pool.health_check()
    if not is_healthy:
        # Alert! Database problems!
        pass

    # Example 4: Monitor pool usage
    stats = pool.get_stats()
    print(f"Pool usage: {stats['usage_percent']:.1f}%")

    # Example 5: Shutdown
    pool.close()


# ============================================================================
# COMMON ISSUES AND SOLUTIONS
# ============================================================================

"""
ISSUE: "PoolTimeout: couldn't get a connection after 30s"
CAUSE: All connections are busy, none available
SOLUTIONS:
1. Increase max_size (more connections)
2. Investigate slow queries (why are connections tied up?)
3. Check for connection leaks (connections not returned)

ISSUE: "Too many connections" from PostgreSQL
CAUSE: max_size × number_of_app_instances > postgres max_connections
SOLUTION: Lower max_size OR increase PostgreSQL max_connections

ISSUE: "Connection reset by peer"
CAUSE: Connection closed on database side
SOLUTION: Pool's max_lifetime parameter handles this (auto-recycles)

ISSUE: Slow first request after idle period
CAUSE: Connections might have timed out
SOLUTION: min_size > 0 keeps some connections always alive
"""
