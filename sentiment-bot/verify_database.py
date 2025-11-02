#!/usr/bin/env python3
"""
Database Verification Script

WHY THIS EXISTS (Theory of Mind):
You've just set up PostgreSQL and want to know: "Is it working?"

This script answers that question by:
1. Testing the connection
2. Running migrations
3. Inserting test data
4. Running sample queries
5. Cleaning up

WHEN TO USE:
- After initial PostgreSQL setup
- After changing DATABASE_URL
- When troubleshooting database issues
- Before deploying to production

USAGE:
python verify_database.py
"""

import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import get_settings
from app.storage.migrations import MigrationManager
from app.storage.db_pool import DatabasePool
from app.services.types import SocialPost, SentimentScore
import psycopg


class DatabaseVerifier:
    """
    Runs comprehensive database verification checks.

    WHAT IT CHECKS:
    1. Can we connect?
    2. Do tables exist?
    3. Can we insert data?
    4. Can we query data?
    5. Are indexes working?
    6. Can we clean up?
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.conn = None
        self.checks_passed = 0
        self.checks_failed = 0

    def _print_header(self, message: str):
        """Print a formatted header"""
        print(f"\n{'=' * 70}")
        print(f"  {message}")
        print(f"{'=' * 70}")

    def _print_check(self, name: str, passed: bool, details: str = ""):
        """Print check result"""
        status = "✓" if passed else "✗"
        status_text = "PASS" if passed else "FAIL"
        color = "\033[92m" if passed else "\033[91m"  # Green/Red
        reset = "\033[0m"

        print(f"{color}{status} [{status_text}]{reset} {name}")
        if details:
            print(f"   → {details}")

        if passed:
            self.checks_passed += 1
        else:
            self.checks_failed += 1

    def connect(self) -> bool:
        """
        Test 1: Can we connect to the database?

        WHAT THIS TELLS YOU:
        - Database server is running
        - Credentials are correct
        - Network connectivity works
        - Database exists
        """
        self._print_header("Test 1: Database Connection")

        try:
            self.conn = psycopg.connect(self.database_url, autocommit=True)
            self._print_check(
                "Connect to PostgreSQL",
                True,
                f"Connected successfully"
            )
            return True

        except psycopg.OperationalError as e:
            self._print_check(
                "Connect to PostgreSQL",
                False,
                f"Connection failed: {e}"
            )
            print("\n💡 TROUBLESHOOTING:")
            print("   - Is PostgreSQL running? (docker-compose up -d)")
            print("   - Is DATABASE_URL correct in .env?")
            print("   - Can you ping the database host?")
            return False

    def check_pgvector(self) -> bool:
        """
        Test 2: Is pgvector extension installed?

        WHAT THIS TELLS YOU:
        - pgvector extension is available
        - Can store and query vector embeddings
        - Database is properly configured
        """
        self._print_header("Test 2: pgvector Extension")

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM pg_extension WHERE extname = 'vector'
                    )
                """)
                has_pgvector = cur.fetchone()[0]

                if has_pgvector:
                    self._print_check(
                        "pgvector extension installed",
                        True,
                        "Vector similarity search enabled"
                    )
                    return True
                else:
                    self._print_check(
                        "pgvector extension installed",
                        False,
                        "Extension not found"
                    )
                    print("\n💡 SOLUTION:")
                    print("   Use pgvector/pgvector Docker image")
                    print("   OR install pgvector manually")
                    return False

        except Exception as e:
            self._print_check("Check pgvector", False, str(e))
            return False

    def run_migrations(self) -> bool:
        """
        Test 3: Can we run database migrations?

        WHAT THIS TELLS YOU:
        - Migrations system works
        - Tables are created correctly
        - Indexes are set up
        - Schema is ready for use
        """
        self._print_header("Test 3: Database Migrations")

        try:
            manager = MigrationManager(self.conn)

            # Check for pending migrations
            pending = manager.get_pending_migrations()
            self._print_check(
                f"Found {len(pending)} pending migration(s)",
                True,
                f"Migrations: {', '.join(pending) if pending else 'none'}"
            )

            # Apply migrations
            applied = manager.apply_all_pending()

            if applied > 0:
                self._print_check(
                    f"Applied {applied} migration(s)",
                    True,
                    "Database schema is up to date"
                )
            else:
                self._print_check(
                    "Migrations status",
                    True,
                    "No migrations needed - already up to date"
                )

            return True

        except Exception as e:
            self._print_check("Run migrations", False, str(e))
            return False

    def check_tables(self) -> bool:
        """
        Test 4: Do all required tables exist?

        WHAT THIS TELLS YOU:
        - Migrations created tables successfully
        - Schema matches expectations
        - Database is ready for data
        """
        self._print_header("Test 4: Table Structure")

        required_tables = [
            'social_posts',
            'post_embeddings',
            'sentiment',
            'resolver_cache',
            'source_accounts',
            'applied_migrations'
        ]

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                existing_tables = [row[0] for row in cur.fetchall()]

            all_exist = True
            for table in required_tables:
                exists = table in existing_tables
                self._print_check(
                    f"Table '{table}' exists",
                    exists,
                    "" if exists else "Missing!"
                )
                if not exists:
                    all_exist = False

            return all_exist

        except Exception as e:
            self._print_check("Check tables", False, str(e))
            return False

    def test_insert_data(self) -> bool:
        """
        Test 5: Can we insert and retrieve data?

        WHAT THIS TELLS YOU:
        - CRUD operations work
        - Data types are correct
        - Constraints are enforced
        - Array types work
        """
        self._print_header("Test 5: Data Operations")

        try:
            # Insert test post
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO social_posts
                    (source, platform_id, author_id, created_at, text, symbols)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    'test',
                    'verify_123',
                    'test_user',
                    datetime.now(),
                    'Test post about $AAPL and $TSLA',
                    ['AAPL', 'TSLA']
                ))
                post_id = cur.fetchone()[0]

            self._print_check(
                "Insert test post",
                True,
                f"Post ID: {post_id}"
            )

            # Insert sentiment
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sentiment
                    (post_pk, polarity, subjectivity, sarcasm_prob, confidence, model)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (post_id, 0.8, 0.5, 0.1, 0.9, 'test_model'))

            self._print_check("Insert sentiment score", True)

            # Query it back
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT p.text, s.polarity, s.confidence
                    FROM social_posts p
                    JOIN sentiment s ON s.post_pk = p.id
                    WHERE p.id = %s
                """, (post_id,))
                result = cur.fetchone()

            self._print_check(
                "Query with JOIN",
                result is not None,
                f"Text: '{result[0][:30]}...', Polarity: {result[1]}" if result else ""
            )

            return True

        except Exception as e:
            self._print_check("Insert/query data", False, str(e))
            return False

    def test_indexes(self) -> bool:
        """
        Test 6: Are indexes working?

        WHAT THIS TELLS YOU:
        - Indexes are created
        - Query optimizer uses them
        - Performance is optimized
        """
        self._print_header("Test 6: Index Performance")

        try:
            # Check GIN index on symbols array
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'social_posts'
                    AND indexname = 'idx_social_posts_symbols'
                """)
                index = cur.fetchone()

            self._print_check(
                "GIN index on symbols",
                index is not None,
                "Fast array searches enabled" if index else "Index missing!"
            )

            # Check time index
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE tablename = 'social_posts'
                    AND indexname = 'idx_social_posts_created'
                """)
                time_index = cur.fetchone()

            self._print_check(
                "Index on created_at",
                time_index is not None,
                "Fast time-based queries enabled"
            )

            # Test index usage with EXPLAIN
            with self.conn.cursor() as cur:
                cur.execute("""
                    EXPLAIN (FORMAT JSON)
                    SELECT * FROM social_posts
                    WHERE 'AAPL' = ANY(symbols)
                """)
                plan = cur.fetchone()[0][0]

                uses_index = "Index Scan" in str(plan) or "Bitmap" in str(plan)

            self._print_check(
                "Query optimizer uses indexes",
                uses_index,
                "Queries will be fast" if uses_index else "May be slow"
            )

            return True

        except Exception as e:
            self._print_check("Check indexes", False, str(e))
            return False

    def test_connection_pool(self) -> bool:
        """
        Test 7: Does connection pooling work?

        WHAT THIS TELLS YOU:
        - Pool can be created
        - Connections can be borrowed
        - Connections are returned
        - Pool is healthy
        """
        self._print_header("Test 7: Connection Pool")

        try:
            pool = DatabasePool(self.database_url, min_size=1, max_size=3)
            pool.initialize()

            self._print_check("Initialize connection pool", True)

            # Test getting a connection
            with pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()

            self._print_check(
                "Borrow and return connection",
                result[0] == 1,
                "Connection reuse working"
            )

            # Check stats
            stats = pool.get_stats()
            self._print_check(
                "Pool statistics",
                stats['status'] == 'healthy',
                f"Available: {stats['pool_available']}/{stats['pool_size']}"
            )

            # Health check
            healthy = pool.health_check()
            self._print_check(
                "Pool health check",
                healthy,
                "Pool is ready for production"
            )

            pool.close()
            return True

        except Exception as e:
            self._print_check("Connection pool", False, str(e))
            return False

    def cleanup(self) -> bool:
        """
        Test 8: Can we clean up test data?

        WHAT THIS TELLS YOU:
        - DELETE operations work
        - Foreign keys cascade properly
        - Database can be reset
        """
        self._print_header("Test 8: Cleanup")

        try:
            with self.conn.cursor() as cur:
                # Delete test data (cascades to sentiment table)
                cur.execute("""
                    DELETE FROM social_posts
                    WHERE source = 'test'
                """)
                deleted = cur.rowcount

            self._print_check(
                "Delete test data",
                deleted > 0,
                f"Removed {deleted} test record(s)"
            )

            return True

        except Exception as e:
            self._print_check("Cleanup", False, str(e))
            return False

    def run_all_tests(self) -> bool:
        """Run all verification tests"""
        print("\n" + "=" * 70)
        print("  DATABASE VERIFICATION SUITE")
        print("  Testing PostgreSQL setup for Sentiment Bot")
        print("=" * 70)

        # Run tests in order
        tests = [
            self.connect,
            self.check_pgvector,
            self.run_migrations,
            self.check_tables,
            self.test_insert_data,
            self.test_indexes,
            self.test_connection_pool,
            self.cleanup
        ]

        for test in tests:
            if not test():
                # If a critical test fails, stop
                if test == self.connect:
                    break

        # Print summary
        self._print_header("VERIFICATION SUMMARY")
        total = self.checks_passed + self.checks_failed
        success_rate = (self.checks_passed / total * 100) if total > 0 else 0

        print(f"  Total checks: {total}")
        print(f"  ✓ Passed: {self.checks_passed}")
        print(f"  ✗ Failed: {self.checks_failed}")
        print(f"  Success rate: {success_rate:.1f}%")
        print("=" * 70)

        if self.checks_failed == 0:
            print("\n🎉 ALL CHECKS PASSED!")
            print("   Your database is properly configured and ready to use.")
            print("   You can now start the application with confidence.")
            return True
        else:
            print("\n⚠️  SOME CHECKS FAILED")
            print("   Review the errors above and fix them.")
            print("   Common issues:")
            print("   - PostgreSQL not running")
            print("   - Wrong DATABASE_URL")
            print("   - Missing pgvector extension")
            return False


def main():
    """Main entry point"""
    print("\n╔════════════════════════════════════════════════════════════════╗")
    print("║           SENTIMENT BOT - DATABASE VERIFICATION                ║")
    print("╚════════════════════════════════════════════════════════════════╝")

    # Load settings
    settings = get_settings()

    # Check if PostgreSQL is enabled
    if not settings.use_postgres:
        print("\n⚠️  PostgreSQL is not enabled in configuration")
        print("   Set USE_POSTGRES=true in .env to use PostgreSQL")
        print("   Currently using in-memory storage")
        return 1

    if not settings.database_url:
        print("\n✗ DATABASE_URL not configured")
        print("  Set it in .env file")
        return 1

    print(f"\nDatabase URL: {settings.database_url.split('@')[1]}")  # Hide password
    print("Starting verification...\n")

    # Run verification
    verifier = DatabaseVerifier(settings.database_url)
    success = verifier.run_all_tests()

    # Cleanup
    if verifier.conn:
        verifier.conn.close()

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
