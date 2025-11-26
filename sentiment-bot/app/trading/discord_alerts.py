"""
Discord bot for sending swing trading alerts.

Posts daily market scan results and trade opportunities to Discord.
"""

import logging
from typing import List, Optional
from datetime import datetime
import discord
from discord.ext import commands, tasks

from app.trading.scanner import scan_market, OpportunityScore
from app.config import get_settings

logger = logging.getLogger(__name__)


class TradingAlertsBot(commands.Cog):
    """Discord bot for trading alerts."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = get_settings()
        self.scan_market_loop.start()

    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        self.scan_market_loop.cancel()

    @tasks.loop(hours=24)
    async def scan_market_loop(self):
        """Run daily market scan and post to Discord."""
        try:
            logger.info("Running daily market scan for Discord alerts...")

            # Get channel to post to
            channel_id = int(self.settings.discord_alerts_channel or 0)
            if not channel_id:
                logger.warning("DISCORD_ALERTS_CHANNEL not configured, skipping alerts")
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"Could not find Discord channel {channel_id}")
                return

            # Run scan
            opportunities = await scan_market(min_conviction=5.0, max_results=10)

            if not opportunities:
                await channel.send("📊 **Daily Market Scan** - No high-conviction opportunities found today.")
                return

            # Post results
            embeds = self._create_opportunity_embeds(opportunities)

            for embed in embeds:
                await channel.send(embed=embed)

            logger.info(f"Posted {len(opportunities)} opportunities to Discord")

        except Exception as e:
            logger.error(f"Error in daily scan loop: {e}", exc_info=True)

    @scan_market_loop.before_loop
    async def before_scan_loop(self):
        """Wait for bot to be ready before starting loop."""
        await self.bot.wait_until_ready()

    @commands.command(name="scan")
    async def manual_scan(self, ctx):
        """
        Manual command to run market scan.

        Usage: !scan
        """
        async with ctx.typing():
            try:
                opportunities = await scan_market(min_conviction=5.0, max_results=10)

                if not opportunities:
                    await ctx.send("📊 No high-conviction opportunities found.")
                    return

                embeds = self._create_opportunity_embeds(opportunities)

                for embed in embeds:
                    await ctx.send(embed=embed)

            except Exception as e:
                await ctx.send(f"❌ Error scanning market: {str(e)}")
                logger.error(f"Error in manual scan: {e}")

    @commands.command(name="price")
    async def check_price(self, ctx, symbol: str):
        """
        Check sentiment for a specific stock.

        Usage: !price AAPL
        """
        async with ctx.typing():
            try:
                from app.orchestration.tasks import aggregate_social

                result = aggregate_social(symbol.upper(), "7d")

                if result.get("error"):
                    await ctx.send(f"❌ Error: {result.get('error')}")
                    return

                sentiment = result.get("sentiment", {})
                sources = result.get("sources", {})

                embed = discord.Embed(
                    title=f"💰 {symbol.upper()} Sentiment Analysis",
                    description=f"7-day window | {result.get('posts_found', 0)} posts analyzed",
                    color=discord.Color.green() if sentiment.get("avg_polarity", 0) > 0 else discord.Color.red()
                )

                embed.add_field(
                    name="Sentiment",
                    value=f"Polarity: `{sentiment.get('avg_polarity', 0):.2f}` (-1 to +1)\nConfidence: `{sentiment.get('confidence', 0):.2%}`",
                    inline=True
                )

                embed.add_field(
                    name="Sources",
                    value=f"X: {sources.get('x', 0)}\nReddit: {sources.get('reddit', 0)}\nStockTwits: {sources.get('stocktwits', 0)}\nDiscord: {sources.get('discord', 0)}",
                    inline=True
                )

                embed.set_footer(text=f"Analyzed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")

                await ctx.send(embed=embed)

            except Exception as e:
                await ctx.send(f"❌ Error: {str(e)}")
                logger.error(f"Error checking price: {e}")

    def _create_opportunity_embeds(self, opportunities: List[OpportunityScore]) -> List[discord.Embed]:
        """
        Create Discord embeds for opportunities.

        Args:
            opportunities: List of trading opportunities

        Returns:
            List of Discord Embed objects
        """
        embeds = []

        # Header embed
        header = discord.Embed(
            title="📊 Daily Swing Trading Scan",
            description=f"Found {len(opportunities)} high-conviction opportunities",
            color=discord.Color.blue()
        )
        header.set_footer(text=f"Scan time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        embeds.append(header)

        # One embed per opportunity
        for i, opp in enumerate(opportunities, 1):
            color = discord.Color.green() if opp.sentiment_polarity > 0 else discord.Color.red()

            embed = discord.Embed(
                title=f"{i}. {opp.symbol} - {opp.company_name}",
                description=opp.divergence_reason,
                color=color
            )

            # Conviction and signal type
            conviction_bar = self._create_conviction_bar(opp.conviction_score)
            embed.add_field(
                name="Signal Strength",
                value=f"{conviction_bar} {opp.conviction_score:.1f}/10 ({opp.signal_type})",
                inline=False
            )

            # Sentiment
            embed.add_field(
                name="Sentiment",
                value=f"Polarity: `{opp.sentiment_polarity:.2f}`\nConfidence: `{opp.sentiment_confidence:.0%}`",
                inline=True
            )

            # Price action
            embed.add_field(
                name="Price Action",
                value=f"7d: `{opp.price_change_7d:+.1f}%`\n30d: `{opp.price_change_30d:+.1f}%`",
                inline=True
            )

            # Trade setup
            embed.add_field(
                name="💼 Trade Setup",
                value=(
                    f"Entry: `${opp.entry_price:.2f}`\n"
                    f"Stop: `${opp.stop_loss:.2f}` (-10%)\n"
                    f"T1: `${opp.target_1:.2f}` (+20%)\n"
                    f"T2: `${opp.target_2:.2f}` (+50%)\n"
                    f"T3: `${opp.target_3:.2f}` (+100%)"
                ),
                inline=False
            )

            # Position sizing and risk/reward
            embed.add_field(
                name="💰 Position Size",
                value=f"`${opp.position_size_dollars:,}` ($2K max loss)\nR/R: `{opp.risk_reward_ratio:.1f}:1`",
                inline=False
            )

            embeds.append(embed)

        return embeds

    def _create_conviction_bar(self, score: float) -> str:
        """Create a visual bar for conviction score."""
        filled = int(score / 2)  # 0-10 -> 0-5
        empty = 5 - filled
        return "█" * filled + "░" * empty


async def setup_trading_alerts_bot(token: str, alerts_channel_id: Optional[int] = None) -> commands.Bot:
    """
    Setup and start the trading alerts Discord bot.

    Args:
        token: Discord bot token
        alerts_channel_id: Channel ID for posting alerts

    Returns:
        Configured Discord bot
    """
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.guild_messages = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        logger.info(f"Trading alerts bot logged in as {bot.user}")

    # Add cog
    await bot.add_cog(TradingAlertsBot(bot))

    return bot


def run_trading_alerts_bot(token: str):
    """
    Run the trading alerts bot (blocking call).

    Args:
        token: Discord bot token
    """
    import asyncio

    async def main():
        bot = await setup_trading_alerts_bot(token)
        await bot.start(token)

    asyncio.run(main())
