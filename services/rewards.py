import asyncio
import logging

import discord

from config import (
    CLAIM_LOG_CHANNEL_ID,
    DIAMOND_COMMANDS,
    DIAMOND_COOLDOWN_SECONDS,
    INGAME_MESSAGES_ENABLED,
    OUTPOST_COOLDOWN_SECONDS,
    OUTPOST_X,
    OUTPOST_Y,
    OUTPOST_Z,
    SERVER_MESSAGE_PREFIX,
    ULTIMATE_COMMANDS,
    ULTIMATE_COOLDOWN_SECONDS,
    VIP_COMMANDS,
    VIP_COOLDOWN_SECONDS,
)
from services.database import (
    get_action_cooldown_remaining,
    get_link_by_gamertag,
    store_vip_claim,
)
from services.helpers import get_package_for_member


logger = logging.getLogger("sanity2x.rewards")


# =========================================================
# Package configuration
# =========================================================

PACKAGE_SETTINGS = {
    "vip": {
        "display_name": "VIP",
        "commands": VIP_COMMANDS,
        "cooldown": VIP_COOLDOWN_SECONDS,
    },
    "diamond": {
        "display_name": "Diamond VIP",
        "commands": DIAMOND_COMMANDS,
        "cooldown": DIAMOND_COOLDOWN_SECONDS,
    },
    "ultimate": {
        "display_name": "Ultimate VIP",
        "commands": ULTIMATE_COMMANDS,
        "cooldown": ULTIMATE_COOLDOWN_SECONDS,
    },
}


# Higher packages can claim lower package rewards.
#
# VIP:
# - VIP
#
# Diamond:
# - VIP
# - Diamond
#
# Ultimate:
# - VIP
# - Diamond
# - Ultimate

PACKAGE_RANKS = {
    None: 0,
    "vip": 1,
    "diamond": 2,
    "ultimate": 3,
}


# =========================================================
# Utility functions
# =========================================================

def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []

    if days:
        parts.append(f"{days}d")

    if hours:
        parts.append(f"{hours}h")

    if minutes:
        parts.append(f"{minutes}m")

    if not parts or secs:
        parts.append(f"{secs}s")

    return " ".join(parts[:2])


def safe_text(value: object) -> str:
    return (
        str(value)
        .replace('"', "")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\u0000", "")
        .strip()
    )


def can_use_package(
    owned_package: str | None,
    requested_package: str,
) -> bool:
    owned_rank = PACKAGE_RANKS.get(owned_package, 0)
    requested_rank = PACKAGE_RANKS.get(requested_package, 0)

    return owned_rank >= requested_rank


async def fetch_member(
    bot,
    discord_id: int,
) -> discord.Member | None:
    guild = bot.get_guild(bot.guild_id)

    if guild is None:
        logger.warning(
            "Guild %s could not be found.",
            getattr(bot, "guild_id", None),
        )
        return None

    member = guild.get_member(discord_id)

    if member is not None:
        return member

    try:
        return await guild.fetch_member(discord_id)

    except discord.NotFound:
        logger.warning(
            "Discord member %s was not found.",
            discord_id,
        )
        return None

    except discord.Forbidden:
        logger.warning(
            "The bot is not allowed to fetch Discord member %s.",
            discord_id,
        )
        return None

    except discord.HTTPException:
        logger.exception(
            "Failed to fetch Discord member %s.",
            discord_id,
        )
        return None


# =========================================================
# In-game announcements
# =========================================================

async def announce(
    rcon_service,
    text: str,
) -> None:
    if not INGAME_MESSAGES_ENABLED:
        return

    clean_message = safe_text(
        f"{SERVER_MESSAGE_PREFIX} {text}"
    )

    if not clean_message:
        return

    sent, response = await rcon_service.send_command(
        f'global.say "{clean_message}"'
    )

    if not sent:
        logger.warning(
            "Failed to send in-game announcement: %s",
            response,
        )


# =========================================================
# Discord claim logging
# =========================================================

async def log_claim(
    bot,
    title: str,
    description: str,
    success: bool,
) -> None:
    if not CLAIM_LOG_CHANNEL_ID:
        return

    channel = bot.get_channel(CLAIM_LOG_CHANNEL_ID)

    if channel is None:
        try:
            channel = await bot.fetch_channel(
                CLAIM_LOG_CHANNEL_ID
            )

        except discord.HTTPException:
            logger.exception(
                "Failed to fetch claim log channel %s.",
                CLAIM_LOG_CHANNEL_ID,
            )
            return

    if not hasattr(channel, "send"):
        logger.warning(
            "Claim log channel %s cannot receive messages.",
            CLAIM_LOG_CHANNEL_ID,
        )
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=(
            discord.Color.green()
            if success
            else discord.Color.red()
        ),
    )

    try:
        await channel.send(embed=embed)

    except discord.HTTPException:
        logger.exception(
            "Failed to send the claim log embed."
        )


# =========================================================
# VIP reward handling
# =========================================================

async def handle_reward_trigger(
    bot,
    rcon_service,
    player_name: str,
    phrase: str,
    requested_package: str,
) -> dict:
    requested_package = requested_package.strip().lower()

    if requested_package not in PACKAGE_SETTINGS:
        logger.warning(
            "Unknown requested package: %s",
            requested_package,
        )

        return {
            "delivered": False,
            "reason": "unknown_package",
            "requested": requested_package,
        }

    link = await get_link_by_gamertag(player_name)

    if not link:
        await announce(
            rcon_service,
            (
                f"{player_name}: link your Discord "
                f"account with /link first."
            ),
        )

        return {
            "delivered": False,
            "reason": "not_linked",
        }

    try:
        discord_id = int(link["discord_id"])

    except (KeyError, TypeError, ValueError):
        logger.error(
            "Invalid Discord ID stored for player %s: %r",
            player_name,
            link,
        )

        await announce(
            rcon_service,
            (
                f"{player_name}: your linked Discord "
                f"account is invalid. Contact staff."
            ),
        )

        return {
            "delivered": False,
            "reason": "invalid_discord_id",
        }

    member = await fetch_member(
        bot,
        discord_id,
    )

    if member is None:
        await announce(
            rcon_service,
            (
                f"{player_name}: your linked Discord "
                f"member could not be found."
            ),
        )

        return {
            "delivered": False,
            "reason": "member_not_found",
        }

    owned_package = get_package_for_member(member)

    logger.info(
        "[PACKAGE CHECK] Player=%s Discord=%s "
        "Owned=%s Requested=%s",
        player_name,
        member.id,
        owned_package,
        requested_package,
    )

    if not can_use_package(
        owned_package,
        requested_package,
    ):
        package_name = PACKAGE_SETTINGS[
            requested_package
        ]["display_name"]

        await announce(
            rcon_service,
            (
                f"{player_name}: this command "
                f"requires {package_name}."
            ),
        )

        await log_claim(
            bot,
            "❌ Reward denied",
            (
                f"**Player:** `{player_name}`\n"
                f"**Discord:** {member.mention}\n"
                f"**Owned tier:** `{owned_package}`\n"
                f"**Requested tier:** `{requested_package}`\n"
                f"**Reason:** Wrong VIP tier"
            ),
            False,
        )

        return {
            "delivered": False,
            "reason": "wrong_vip_tier",
            "owned": owned_package,
            "requested": requested_package,
        }

    settings = PACKAGE_SETTINGS[requested_package]

    display_name = settings["display_name"]
    commands = settings["commands"]
    cooldown = settings["cooldown"]

    remaining = await get_action_cooldown_remaining(
        player_name,
        requested_package,
        cooldown,
    )

    if remaining > 0:
        await announce(
            rcon_service,
            (
                f"{player_name}: {display_name} "
                f"is on cooldown for "
                f"{format_duration(remaining)}."
            ),
        )

        return {
            "delivered": False,
            "reason": "cooldown",
            "remaining_seconds": remaining,
        }

    if not commands:
        logger.warning(
            "%s commands are not configured.",
            requested_package,
        )

        await announce(
            rcon_service,
            (
                f"{player_name}: {display_name} "
                f"rewards are not configured."
            ),
        )

        return {
            "delivered": False,
            "reason": "no_commands_configured",
        }

    safe_player = safe_text(player_name)

    details: list[str] = []
    success = True

    for template in commands:
        try:
            command = template.format(
                player=safe_player
            )

        except (KeyError, ValueError, IndexError) as exc:
            success = False

            error_detail = (
                f"Template error: {template} -> {exc}"
            )

            details.append(error_detail)

            logger.exception(
                "Invalid reward command template: %s",
                template,
            )
            break

        sent, response = await rcon_service.send_command(
            command
        )

        details.append(
            f"{command} -> {response}"
        )

        if not sent:
            success = False

            logger.warning(
                "Reward command failed for %s: %s",
                player_name,
                response,
            )
            break

        await asyncio.sleep(0.25)

    detail = "\n".join(details)

    await store_vip_claim(
        member.id,
        player_name,
        requested_package,
        phrase,
        success,
        detail,
    )

    if success:
        await announce(
            rcon_service,
            (
                f"{player_name} claimed the "
                f"{display_name} reward. "
                f"Next claim in "
                f"{format_duration(cooldown)}."
            ),
        )

    else:
        await announce(
            rcon_service,
            (
                f"{player_name}: the reward failed. "
                f"Please contact staff."
            ),
        )

    await log_claim(
        bot,
        (
            f"{'✅' if success else '❌'} "
            f"{display_name} claim"
        ),
        (
            f"**Player:** `{player_name}`\n"
            f"**Discord:** {member.mention}\n"
            f"**Owned tier:** `{owned_package}`\n"
            f"**Requested tier:** `{requested_package}`\n"
            f"**Trigger:** `{safe_text(phrase)}`\n"
            f"**Commands:** `{len(commands)}`\n"
            f"**Result:** `{'Success' if success else 'Failed'}`"
        ),
        success,
    )

    logger.info(
        "[REWARD RESULT] Player=%s Package=%s "
        "Owned=%s Delivered=%s",
        player_name,
        requested_package,
        owned_package,
        success,
    )

    return {
        "delivered": success,
        "package": requested_package,
        "owned_package": owned_package,
        "detail": detail,
    }


# =========================================================
# Outpost teleport handling
# =========================================================

async def handle_outpost_trigger(
    bot,
    rcon_service,
    player_name: str,
    phrase: str,
    user_id: int | None,
) -> dict:
    link = await get_link_by_gamertag(player_name)

    if not link:
        await announce(
            rcon_service,
            (
                f"{player_name}: link your Discord "
                f"account with /link first."
            ),
        )

        return {
            "delivered": False,
            "reason": "not_linked",
        }

    if user_id is None:
        await announce(
            rcon_service,
            (
                f"{player_name}: your Rust player "
                f"ID could not be read. Try again."
            ),
        )

        return {
            "delivered": False,
            "reason": "missing_user_id",
        }

    if (
        OUTPOST_X == 0.0
        and OUTPOST_Y == 0.0
        and OUTPOST_Z == 0.0
    ):
        await announce(
            rcon_service,
            (
                f"{player_name}: Outpost teleport "
                f"is not configured yet."
            ),
        )

        return {
            "delivered": False,
            "reason": "outpost_not_configured",
        }

    remaining = await get_action_cooldown_remaining(
        player_name,
        "outpost",
        OUTPOST_COOLDOWN_SECONDS,
    )

    if remaining > 0:
        await announce(
            rcon_service,
            (
                f"{player_name}: Outpost teleport "
                f"is on cooldown for "
                f"{format_duration(remaining)}."
            ),
        )

        return {
            "delivered": False,
            "reason": "cooldown",
            "remaining_seconds": remaining,
        }

    try:
        rust_user_id = int(user_id)

    except (TypeError, ValueError):
        await announce(
            rcon_service,
            (
                f"{player_name}: your Rust player "
                f"ID is invalid. Try again."
            ),
        )

        return {
            "delivered": False,
            "reason": "invalid_user_id",
        }

    command = (
    f'global.teleportposrot '
    f'({OUTPOST_X},{OUTPOST_Y},{OUTPOST_Z}) '
    f'"{rust_user_id}" '
    f'"1"'
)

    sent, response = await rcon_service.send_command(
        command
    )

    try:
        discord_id = int(link["discord_id"])

    except (KeyError, TypeError, ValueError):
        discord_id = 0

    await store_vip_claim(
        discord_id,
        player_name,
        "outpost",
        phrase,
        sent,
        f"{command} -> {response}",
    )

    if sent:
        await announce(
            rcon_service,
            (
                f"{player_name} has been "
                f"teleported to Outpost."
            ),
        )

    else:
        await announce(
            rcon_service,
            (
                f"{player_name}: teleport failed. "
                f"Please contact staff."
            ),
        )

    await log_claim(
        bot,
        (
            f"{'✅' if sent else '❌'} "
            f"Outpost teleport"
        ),
        (
            f"**Player:** `{player_name}`\n"
            f"**Rust user ID:** `{rust_user_id}`\n"
            f"**Coordinates:** "
            f"`{OUTPOST_X}, {OUTPOST_Y}, {OUTPOST_Z}`\n"
            f"**Trigger:** `{safe_text(phrase)}`\n"
            f"**RCON response:** `{safe_text(response)}`"
        ),
        sent,
    )

    logger.info(
        "[OUTPOST RESULT] Player=%s UserId=%s "
        "Delivered=%s Response=%s",
        player_name,
        rust_user_id,
        sent,
        response,
    )

    return {
        "delivered": sent,
        "action": "outpost",
        "detail": response,
    }