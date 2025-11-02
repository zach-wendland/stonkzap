"""
Database Migration System

WHY THIS EXISTS (Theory of Mind):
- You can't just change schema.sql in production - there's already data!
- Need to ADD columns, not DROP and recreate tables
- Migrations let you evolve the database safely over time

HOW IT WORKS:
1. Each migration is a numbered SQL file
2. System tracks which migrations have run
3. On startup, applies any new migrations in order
4. Never re-runs old migrations (idempotent)

EXAMPLE WORKFLOW:
- Today: You have 001_initial_schema.sql
- Tomorrow: You add 002_add_sentiment_confidence.sql
- System detects new migration and runs it
- Your data is preserved, just the schema changes
"""

import os
import logging
from typing import List, Optional
from datetime import datetime
import psycopg

logger = logging.getLogger(__name__)


class MigrationManager:
    """
    Manages database schema migrations.

    Theory of Mind: You want to:
    - Track what's been applied
    - Apply new migrations automatically
    - Never lose data
    - Be able to see migration history
    """

    def __init__(self, conn):
        self.conn = conn
        self.migrations_dir = os.path.join(
            os.path.dirname(__file__),
            'migrations'
        )
        self._ensure_migrations_table()

    def _ensure_migrations_table(self):
        """
        Create the migrations tracking table if it doesn't exist.

        WHY: We need to remember which migrations have run.
        This table is the "memory" of our migration system.
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS applied_migrations (
                    id SERIAL PRIMARY KEY,
                    migration_name VARCHAR(255) NOT NULL UNIQUE,
                    applied_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    applied_by VARCHAR(100),
                    execution_time_ms INTEGER,
                    notes TEXT
                )
            """)
            logger.info("Migration tracking table ready")

    def get_applied_migrations(self) -> List[str]:
        """
        Get list of migrations that have already been applied.

        WHAT YOU'RE SEEING: The history of all schema changes.
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT migration_name
                FROM applied_migrations
                ORDER BY applied_at
            """)
            return [row[0] for row in cur.fetchall()]

    def get_pending_migrations(self) -> List[str]:
        """
        Find migrations that haven't been applied yet.

        WHAT HAPPENS:
        1. Lists all .sql files in migrations/
        2. Compares to applied_migrations table
        3. Returns the difference

        WHY SORTED: Migrations must run in order (002 after 001).
        """
        applied = set(self.get_applied_migrations())

        # Create migrations directory if it doesn't exist
        os.makedirs(self.migrations_dir, exist_ok=True)

        # Find all migration files
        all_migrations = []
        if os.path.exists(self.migrations_dir):
            all_migrations = [
                f for f in os.listdir(self.migrations_dir)
                if f.endswith('.sql')
            ]

        # Filter to only pending
        pending = [m for m in sorted(all_migrations) if m not in applied]

        return pending

    def apply_migration(self, migration_name: str) -> bool:
        """
        Apply a single migration.

        WHAT HAPPENS:
        1. Read the SQL file
        2. Execute it in a transaction
        3. If successful: Mark as applied
        4. If failed: Roll back everything

        WHY TRANSACTION: All-or-nothing. Either the whole migration
        works, or none of it does. Your data stays consistent.
        """
        migration_path = os.path.join(self.migrations_dir, migration_name)

        if not os.path.exists(migration_path):
            logger.error(f"Migration file not found: {migration_name}")
            return False

        logger.info(f"Applying migration: {migration_name}")
        start_time = datetime.now()

        try:
            # Read migration SQL
            with open(migration_path, 'r') as f:
                migration_sql = f.read()

            # Execute in transaction
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    # Run the migration
                    cur.execute(migration_sql)

                    # Record that it ran
                    execution_time = int(
                        (datetime.now() - start_time).total_seconds() * 1000
                    )

                    cur.execute("""
                        INSERT INTO applied_migrations
                        (migration_name, applied_by, execution_time_ms)
                        VALUES (%s, %s, %s)
                    """, (
                        migration_name,
                        'system',  # Could be username in multi-user system
                        execution_time
                    ))

            logger.info(
                f"✓ Migration {migration_name} applied successfully "
                f"({execution_time}ms)"
            )
            return True

        except Exception as e:
            logger.error(f"✗ Migration {migration_name} failed: {e}")
            logger.error("Transaction rolled back - your data is safe!")
            return False

    def apply_all_pending(self) -> int:
        """
        Apply all pending migrations in order.

        WHAT YOU WANT: "Just make my database up to date!"

        SAFETY: If any migration fails, we stop. Don't want to apply
        migration 003 if 002 failed - that could break things.
        """
        pending = self.get_pending_migrations()

        if not pending:
            logger.info("No pending migrations - database is up to date")
            return 0

        logger.info(f"Found {len(pending)} pending migration(s)")
        applied_count = 0

        for migration in pending:
            if self.apply_migration(migration):
                applied_count += 1
            else:
                logger.error(
                    f"Stopped at {migration}. "
                    f"Fix the error and try again."
                )
                break

        return applied_count

    def get_migration_history(self) -> List[dict]:
        """
        Show complete migration history.

        USEFUL FOR:
        - Debugging: "When did we add that column?"
        - Auditing: "What changed and when?"
        - Troubleshooting: "Was it working before that migration?"
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    migration_name,
                    applied_at,
                    applied_by,
                    execution_time_ms,
                    notes
                FROM applied_migrations
                ORDER BY applied_at DESC
            """)

            history = []
            for row in cur.fetchall():
                history.append({
                    'name': row[0],
                    'applied_at': row[1].isoformat(),
                    'applied_by': row[2],
                    'execution_time_ms': row[3],
                    'notes': row[4]
                })

            return history

    def create_migration_file(self, description: str) -> str:
        """
        Helper to create a new migration file with proper naming.

        WHAT IT DOES:
        - Finds the next migration number
        - Creates a template file
        - Returns the filename

        EXAMPLE:
        >>> mgr.create_migration_file("add user preferences")
        "003_add_user_preferences.sql"
        """
        # Find next migration number
        existing = self.get_applied_migrations() + self.get_pending_migrations()
        if not existing:
            next_num = 1
        else:
            # Extract numbers from filenames (001_, 002_, etc.)
            numbers = []
            for m in existing:
                try:
                    num = int(m.split('_')[0])
                    numbers.append(num)
                except ValueError:
                    continue
            next_num = max(numbers) + 1 if numbers else 1

        # Create filename
        filename = f"{next_num:03d}_{description.replace(' ', '_')}.sql"
        filepath = os.path.join(self.migrations_dir, filename)

        # Create template
        template = f"""-- Migration: {description}
-- Created: {datetime.now().isoformat()}
--
-- WHY THIS MIGRATION:
-- [Explain what problem this solves or what feature it enables]
--
-- EXAMPLE:
-- [Show example query or usage after this migration]

-- Your SQL here:

"""

        with open(filepath, 'w') as f:
            f.write(template)

        logger.info(f"Created migration template: {filename}")
        return filename


def run_migrations(database_url: str) -> bool:
    """
    Convenience function to run all pending migrations.

    TYPICAL USAGE:
    >>> from app.storage.migrations import run_migrations
    >>> success = run_migrations(settings.database_url)
    >>> if success:
    >>>     print("Database is up to date!")

    WHEN THIS RUNS:
    - Application startup (automatic)
    - After deploying new code (automatic)
    - Manual: python -m app.storage.migrations
    """
    try:
        conn = psycopg.connect(database_url, autocommit=True)
        manager = MigrationManager(conn)
        applied = manager.apply_all_pending()

        if applied > 0:
            logger.info(f"Applied {applied} migration(s) successfully")

        conn.close()
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == '__main__':
    """
    Run migrations from command line.

    USAGE:
    python -m app.storage.migrations

    OR:
    python app/storage/migrations.py

    WHEN YOU'D USE THIS:
    - Testing migrations locally
    - Manual deployment step
    - Debugging migration issues
    """
    import sys
    from app.config import get_settings

    settings = get_settings()

    if not settings.use_postgres:
        print("PostgreSQL is not enabled in config")
        print("Set USE_POSTGRES=true in .env")
        sys.exit(1)

    if not settings.database_url:
        print("DATABASE_URL not configured in .env")
        sys.exit(1)

    print(f"Connecting to database...")
    success = run_migrations(settings.database_url)

    if success:
        print("✓ Migrations complete!")
        sys.exit(0)
    else:
        print("✗ Migration failed!")
        sys.exit(1)
