# Database Integration Guide (Docker-Free)

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

## PostgreSQL Setup Options (No Docker Required!)

### Option 1: Use a Cloud-Hosted Database (Recommended)

**WHY THIS IS EASIEST:**
- No installation needed
- Managed backups and updates
- High availability out of the box
- Free tiers available
- Production-ready immediately

#### DigitalOcean Managed PostgreSQL
```bash
# 1. Create database at https://cloud.digitalocean.com/databases
# 2. Select PostgreSQL 16
# 3. Choose your region
# 4. Select basic plan ($15/month) or dev plan ($7/month)
# 5. Copy the connection string

# 6. Add to .env:
DATABASE_URL=postgresql://user:password@your-db.db.ondigitalocean.com:25060/sentiment?sslmode=require
USE_POSTGRES=true
```

**Includes pgvector:** ✓ Available in PostgreSQL 16+

#### AWS RDS PostgreSQL
```bash
# 1. Create RDS instance in AWS Console
# 2. Select PostgreSQL 16
# 3. Choose db.t3.micro for free tier
# 4. Enable public access
# 5. Create database named 'sentiment'

# 6. Install pgvector extension:
# Connect with psql and run:
CREATE EXTENSION vector;

# 7. Add to .env:
DATABASE_URL=postgresql://postgres:password@your-db.rds.amazonaws.com:5432/sentiment
USE_POSTGRES=true
```

#### Supabase (Free Tier Available!)
```bash
# 1. Sign up at https://supabase.com
# 2. Create new project
# 3. Go to Database > Connection String
# 4. Copy the direct connection URI

# 5. Add to .env:
DATABASE_URL=your_supabase_connection_string
USE_POSTGRES=true
```

**Includes pgvector:** ✓ Pre-installed!

#### Neon (Serverless PostgreSQL - Free Tier)
```bash
# 1. Sign up at https://neon.tech
# 2. Create project
# 3. Copy connection string

# 4. Add to .env:
DATABASE_URL=your_neon_connection_string
USE_POSTGRES=true
```

**Includes pgvector:** ✓ Supported!

### Option 2: Native Local PostgreSQL Installation

**WHY LOCAL:**
- Full control
- No internet required
- No monthly cost
- Fast development

#### macOS (using Homebrew)
```bash
# 1. Install PostgreSQL
brew install postgresql@16

# 2. Start PostgreSQL
brew services start postgresql@16

# 3. Create database
createdb sentiment

# 4. Install pgvector
brew install pgvector

# 5. Connect and enable extension
psql sentiment
CREATE EXTENSION vector;
\q

# 6. Add to .env:
DATABASE_URL=postgresql://$(whoami)@localhost:5432/sentiment
USE_POSTGRES=true
```

#### Ubuntu/Debian Linux
```bash
# 1. Add PostgreSQL repository
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt-get update

# 2. Install PostgreSQL 16
sudo apt-get install -y postgresql-16 postgresql-contrib-16

# 3. Install pgvector
sudo apt-get install -y postgresql-16-pgvector

# 4. Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 5. Create database and user
sudo -u postgres psql
CREATE DATABASE sentiment;
CREATE USER sentimentuser WITH PASSWORD 'yourpassword';
GRANT ALL PRIVILEGES ON DATABASE sentiment TO sentimentuser;
\c sentiment
CREATE EXTENSION vector;
\q

# 6. Add to .env:
DATABASE_URL=postgresql://sentimentuser:yourpassword@localhost:5432/sentiment
USE_POSTGRES=true
```

#### Windows
```bash
# 1. Download PostgreSQL 16 from:
#    https://www.postgresql.org/download/windows/

# 2. Run installer and follow wizard
#    - Remember your password!
#    - Use default port 5432

# 3. Download pgvector from:
#    https://github.com/pgvector/pgvector/releases

# 4. Install pgvector:
#    - Extract files to PostgreSQL installation directory
#    - Copy files to lib/ and share/extension/

# 5. Open SQL Shell (psql) and run:
CREATE DATABASE sentiment;
CREATE EXTENSION vector;
\q

# 6. Add to .env:
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/sentiment
USE_POSTGRES=true
```

### Option 3: Use Existing PostgreSQL Server

**If you already have PostgreSQL:**

```bash
# 1. Create the database
psql -U your_user -h your_host
CREATE DATABASE sentiment;
\c sentiment
CREATE EXTENSION vector;
\q

# 2. Add to .env:
DATABASE_URL=postgresql://your_user:your_password@your_host:5432/sentiment
USE_POSTGRES=true
```

## Verification

After setting up PostgreSQL (any option above):

```bash
# 1. Test connection
python verify_database.py
```

Expected output:
```
✓ [PASS] Connect to PostgreSQL
✓ [PASS] pgvector extension installed
✓ [PASS] Applied 1 migration(s)
✓ [PASS] All tables exist
...
🎉 ALL CHECKS PASSED!
```

## Quick Comparison

| Option | Cost | Setup Time | Maintenance | Best For |
|--------|------|------------|-------------|----------|
| **Supabase** | Free tier! | 5 minutes | None | Getting started |
| **Neon** | Free tier! | 5 minutes | None | Serverless apps |
| **DigitalOcean** | $7-15/mo | 5 minutes | Low | Production |
| **AWS RDS** | $15+/mo | 15 minutes | Low | Enterprise |
| **Local macOS** | Free | 10 minutes | You | Development |
| **Local Linux** | Free | 15 minutes | You | Development |
| **Local Windows** | Free | 20 minutes | You | Development |

## Recommended Path

### For Development:
1. **Start with in-memory** (no setup needed!)
2. **Move to Supabase/Neon free tier** when you want persistence
3. **Upgrade to paid hosting** when scaling

### For Production:
1. **Use managed hosting** (DigitalOcean, AWS RDS, etc.)
2. **Never use in-memory** (data loss on restart!)
3. **Set up automated backups**

## The Rest of the Guide

Everything else in this guide remains the same:
- Schema design rationale
- Migration system
- Connection pooling
- Health checks
- Troubleshooting

**The key change:** You now have MULTIPLE ways to get PostgreSQL without Docker!

## Troubleshooting

### "Connection refused"
**Likely cause:** PostgreSQL not running or wrong host
**Fix:**
- Cloud: Check your connection string
- Local: `sudo systemctl status postgresql` (Linux) or `brew services list` (macOS)

### "Password authentication failed"
**Likely cause:** Wrong credentials in DATABASE_URL
**Fix:** Double-check username and password

### "Extension 'vector' not found"
**Likely cause:** pgvector not installed
**Fix:**
- Cloud: Choose PostgreSQL 16+ (includes pgvector)
- Local: Install pgvector package for your OS

### "Database does not exist"
**Likely cause:** Database not created
**Fix:** Run `CREATE DATABASE sentiment;` in psql

## Next Steps

1. Choose your PostgreSQL option from above
2. Set up database (5-20 minutes depending on option)
3. Run verification: `python verify_database.py`
4. Start app: `uvicorn app.main:app --reload`
5. Check health: `curl http://localhost:8000/healthz/db`

**No Docker required!** 🎉
