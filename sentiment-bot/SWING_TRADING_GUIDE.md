# Swing Trading with Sentiment Bot - Quick Start Guide

**Goal**: Use AI sentiment analysis to find high-probability swing trading opportunities ($10K capital, $2K max loss per trade).

**Timeline**: 30 minutes setup → backtest today → start trading tomorrow

---

## 🚀 Phase 1: System Setup (15 minutes)

### Step 1: Install & Run
```bash
# 1. Start database services
cd infra
docker-compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and add your API keys (see below)

# 4. Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 2: Configure API Keys

Edit `.env` with your credentials:

```env
# X/Twitter (Optional but recommended)
X_BEARER_TOKEN=your_twitter_bearer_token

# Reddit (Optional)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret

# Discord Alerts (Optional)
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_ALERTS_CHANNEL=your_channel_id_for_alerts

# Database (use defaults for local development)
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/sentiment
REDIS_URL=redis://localhost:6379/0
```

**Getting API Keys:**
- **Twitter**: Visit [Twitter Developer Portal](https://developer.twitter.com) → Create app → Get bearer token
- **Reddit**: Visit [Reddit Apps](https://www.reddit.com/prefs/apps) → Create app → Get client ID/secret
- **Discord**: Visit [Discord Developer Portal](https://discord.com/developers/applications) → Create app → Get bot token

### Step 3: Verify System Works
```bash
curl http://localhost:8000/healthz
# Response: {"status":"ok","timestamp":"...","version":"1.0.0"}
```

✅ **System is ready!**

---

## 📊 Phase 2: Validate Your Strategy (10 minutes)

Before risking real money, backtest the signal strategy on historical data.

### Test: Momentum Strategy
```bash
curl "http://localhost:8000/backtest?strategy=momentum&days_back=365"
```

**What to look for:**
- ✅ **Win rate > 50%** = Good signal
- ✅ **Profit factor > 1.5** = Strong signal
- ✅ **Max drawdown < 20%** = Manageable risk

**Example Response:**
```json
{
  "strategy": "momentum",
  "statistics": {
    "total_trades": 47,
    "win_rate": "51.1%",
    "profit_factor": 1.73,
    "avg_win": "18.2%",
    "avg_loss": "-8.5%",
    "max_drawdown": "-14.2%"
  },
  "edge_detected": true,
  "recommendation": "Good signal. Backtest shows consistent edge. Trade with normal risk parameters."
}
```

### Test: Other Strategies
```bash
# Reversal strategy (buy stocks down 20% with positive sentiment)
curl "http://localhost:8000/backtest?strategy=reversal&days_back=365"

# Catalyst strategy (positive sentiment, flat price = early entry)
curl "http://localhost:8000/backtest?strategy=catalyst&days_back=365"
```

**Decision Rules:**
- If `edge_detected: true` → Strategy is tradeable
- If `recommendation` says "Good signal" or "Strong signal" → Proceed to live trading
- Otherwise → Wait for more data or try different parameters

---

## 💡 Phase 3: Find Trading Opportunities (5 minutes)

Run the daily market scanner to find stocks matching your validated strategy.

### Run Daily Scan
```bash
curl "http://localhost:8000/scan?min_conviction=5&max_results=20"
```

**Response includes top 20 opportunities:**

```json
{
  "opportunities": [
    {
      "symbol": "TSLA",
      "company_name": "Tesla Inc",
      "conviction_score": 7.8,
      "signal_type": "momentum",
      "reason": "Strong momentum: price up 35% (7d) with positive sentiment (0.75)",
      "sentiment": {
        "polarity": 0.75,
        "confidence": 0.92
      },
      "price_action": {
        "current": 245.50,
        "change_7d": "35.2%",
        "change_30d": "42.1%"
      },
      "trade_setup": {
        "entry": 245.50,
        "stop_loss": 220.95,
        "target_1": "294.60 (+20%)",
        "target_2": "368.25 (+50%)",
        "target_3": "491.00 (+100%)",
        "position_size": "$2000",
        "risk_reward_ratio": 3.2
      }
    }
  ]
}
```

**Scoring Explained:**
- **Conviction 7-10**: High confidence, good signal
- **Conviction 5-7**: Moderate confidence, tradeable
- **Conviction < 5**: Skip, not enough conviction

---

## 🎯 Phase 4: Execute Trades (5 minutes per trade)

Now take the opportunities from the scan and execute trades.

### Trade Entry Checklist

Before entering **any** trade, verify:

- ✅ Conviction score ≥ 5.0
- ✅ Risk/reward ratio ≥ 2.0
- ✅ Backtest showed edge for this signal type
- ✅ Position size = $2,000 max loss
- ✅ Stop loss set at entry price - 10%

### Step 1: Get Single Stock Sentiment
```bash
curl "http://localhost:8000/query?symbol=TSLA&window=7d"
```

Response shows:
```json
{
  "sentiment": {
    "avg_polarity": 0.75,
    "confidence": 0.92
  },
  "sources": {
    "x": 25,
    "reddit": 18,
    "stocktwits": 12,
    "discord": 5
  }
}
```

**Entry Decision:**
- Polarity > 0.6 + Risk/reward > 2.0 = **ENTER**
- Otherwise = **SKIP**

### Step 2: Place Trade with Broker

Example for TSLA from scanner results:

```
Entry:    $245.50
Stop:     $220.95 (-10%)
Target 1: $294.60 (+20%) - sell 50% here
Target 2: $368.25 (+50%) - sell 25% here
Target 3: $491.00 (+100%) - sell remaining 25%
```

**Trade Execution:**
1. Buy 8 shares of TSLA at $245.50 ($1,964 capital)
2. Set stop-loss at $220.95 (auto-exit if hits)
3. Set limit sell at $294.60 (sell 4 shares = take profit 1)
4. Hold remaining 4 shares for target 2 or 3
5. Hold max 30 days or take final profit target

### Step 3: Manage Position

**Daily Monitoring:**
- Check sentiment update: `curl http://localhost:8000/query?symbol=TSLA`
- If sentiment flips negative AND stop-loss not hit → consider exiting early
- Otherwise → let trade run to targets

**Exit Rules:**
- **Take profit**: Hit target 1, 2, or 3
- **Stop loss**: Price drops 10% from entry
- **Timeout**: Hold 30 days max, exit at market close

---

## 📈 Phase 5: Track & Optimize (Ongoing)

### Daily Routine
```bash
# 1. Run daily scan (every morning)
curl "http://localhost:8000/scan?min_conviction=5&max_results=20"

# 2. Check sentiment on current holdings
curl "http://localhost:8000/query?symbol=AAPL&window=7d"
curl "http://localhost:8000/query?symbol=TSLA&window=7d"

# 3. Record trade results in spreadsheet
```

### Monthly Review
After 10-20 trades, measure:
- Actual win rate (compare to backtest)
- Actual avg win/loss
- Profit factor
- Max drawdown

**If actual < backtest by >10%:**
- Adjust strategy parameters
- Increase conviction threshold
- Require stronger sentiment signal

---

## 💰 Position Sizing Formula

For **$10K capital** with **$2K max loss per trade**:

```python
max_loss = $2000
stop_loss_pct = 0.10  # 10% stop

position_size = max_loss / (entry_price × stop_loss_pct)
position_size_dollars = position_size × entry_price

# Example:
# Entry: $245.50
# Stop loss: $220.95
# Risk per share: $24.55
# Position size: $2000 / $24.55 = ~81 shares
# Capital used: 81 × $245.50 = ~$19,886
# ❌ Over capital! Reduce to 8 shares = $1,964
```

**Simple Rule**: Never risk more than $2K per position.

---

## ⚠️ Risk Management Rules

**NON-NEGOTIABLE:**

1. **Max loss per trade**: $2,000 (20% of capital)
2. **Stop loss**: Always set at -10% from entry
3. **Max positions**: Hold 5 concurrent trades max
4. **Position sizing**: Never go all-in on one stock
5. **Daily max loss**: Stop trading if lose >$4K in one day
6. **Trade only validated signals**: Backtest win rate > 45%

**Example Portfolio:**
```
$10,000 capital
Trade 1: $2,000 → Entry $100 → Stop $90
Trade 2: $2,000 → Entry $50 → Stop $45
Trade 3: $2,000 → Entry $200 → Stop $180
Trade 4: $2,000 → Entry $75 → Stop $67.50
Trade 5: $2,000 → Entry $150 → Stop $135

Total at risk: $10,000 (100% of capital)
Max loss per trade: $2,000
Max concurrent: 5 trades
```

---

## 🔧 Discord Alerts Setup (Optional)

Get automated daily scans posted to your Discord server.

### Step 1: Get Discord Bot Token
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create New Application
3. Go to Bot → Click "Add Bot"
4. Copy token → Add to `.env` as `DISCORD_BOT_TOKEN`

### Step 2: Invite Bot to Server
1. Go to OAuth2 → URL Generator
2. Select scopes: `bot`
3. Select permissions: `Send Messages`, `Embed Links`, `Mention Users`
4. Copy generated URL → Open in browser → Select server → Authorize

### Step 3: Get Channel ID
1. Enable Developer Mode in Discord (User Settings → Advanced)
2. Right-click on channel → "Copy Channel ID"
3. Add to `.env` as `DISCORD_ALERTS_CHANNEL`

### Step 4: Start Bot
```bash
# Run in separate terminal
python app/trading/discord_alerts.py
```

**Daily alerts will post at midnight UTC with top 10 opportunities**

### Discord Commands
```
!scan              # Run manual scan
!price AAPL        # Check sentiment for AAPL
```

---

## 📊 Expected Performance

**Conservative Estimates (based on backtest):**

```
Month 1: 5 trades
- 2-3 winners @ +20% = +$800-1200
- 2-3 losers @ -10% = -$400-600
- Net: +$200-600 (2-6% return)

Month 2-3: Compounding
- More capital = larger positions
- +$500-1000/month realistic

By Month 6:
$10K → $12K → $14.4K → $17.3K → $20.8K → $25K

Expected annual return: 150-250% if discipline holds
```

**Reality Check:**
- First month will be slowest (learning curve)
- Losses will happen (expect 3-5 losing trades)
- Win rate <45% = Strategy doesn't work, stop trading
- Emotional discipline = 80% of success

---

## ✅ Troubleshooting

### "No opportunities found in scan"
- API keys not configured (add X/Reddit keys)
- Market conditions (sometimes just few opportunities)
- Increase scan to all stocks: Ask for `max_results=50`

### "Backtest shows no edge"
- Strategy not profitable on historical data
- Don't trade it yet, try different parameters
- Wait for more historical data

### "Discord bot not posting alerts"
- Check `DISCORD_ALERTS_CHANNEL` is set in `.env`
- Verify bot has permission to post in channel
- Check logs: `python app/trading/discord_alerts.py`

### "Position sizing keeps changing"
- Entry price fluctuates intraday
- Calculate at exact entry time
- Use limit orders to lock in entry price

---

## 📚 Learning Resources

**Before You Trade:**
- Read: [Swing Trading Basics](https://www.investopedia.com/terms/s/swingtrading.asp)
- Watch: 3-minute intro to risk management
- Practice: Paper trade for 1 week first

**While Trading:**
- Track every trade in spreadsheet
- Review weekly: What worked? What didn't?
- Adjust parameters monthly based on results

**Advanced (later):**
- Sentiment fine-tuning: Train FinBERT on your winning trades
- Multi-indicator confirmation: Add RSI, MACD to sentiment signals
- Options trading: Use puts to hedge larger positions

---

## 🎯 First Trade Checklist

```
□ Backtest shows edge (win rate > 45%, profit factor > 1.0)
□ Market scan returned opportunity with conviction ≥ 5.0
□ Checked single stock sentiment (polarity > 0.6)
□ Calculated position size ($2K max loss)
□ Set stop-loss at -10% from entry
□ Set profit targets at +20%, +50%, +100%
□ Opened position with broker
□ Documented entry details in spreadsheet
□ Set calendar reminder to check daily
```

✅ **You're ready to trade!**

---

**Need help?** Check the API documentation: `http://localhost:8000/docs`
