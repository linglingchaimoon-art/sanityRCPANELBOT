from __future__ import annotations

import asyncio
import logging

import discord

from config import (
    CLAIM_LOG_CHANNEL_ID,
    DIAMOND_COMMANDS,
    DIAMOND_COOLDOWN_SECONDS,
    OUTPOST_COOLDOWN_SECONDS,
    OUTPOST_X,
    OUTPOST_Y,
    OUTPOST_Z,
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
from services.helpers import (
    announce_reward,
    clean_rust_text,
    get_package_for_member,
    send_public_rust_message,
)


logger = logging.getLogger(
    "sanity2x.rewards"
)


PACKAGE_SETTINGS = {
    "vip": (
        "VIP Kit",
        VIP_COMMANDS,
        VIP_COOLDOWN_SECONDS,
    ),
    "diamond": (
        "Diamond VIP Kit",
        DIAMOND_COMMANDS,
        DIAMOND_COOLDOWN_SECONDS,
    ),
    "ultimate": (
        "Ultimate VIP Kit",
        ULTIMATE_COMMANDS,
        ULTIMATE_COOLDOWN_SECONDS,
    ),
}


def format_duration(
    seconds: int,
) -> str:
    seconds = max(
        0,
        int(seconds),
    )

    hours, remainder = divmod(
        seconds,
        3600,
    )

    minutes, secs = divmod(
        remainder,
        60,
    )

    if hours:
        return f"{hours}h {minutes}m"

    if minutes:
        return f"{minutes}m {secs}s"

    return f"{secs}s"


async def fetch_member(
    bot,
    discord_id: int,
):
    guild = bot.get_guild(
        bot.guild_id
    )

    if guild is None:
        return None

    member = guild.get_member(
        discord_id
    )

    if member is not None:
        return member

    try:
        return await guild.fetch_member(
            discord_id
        )

    except discord.HTTPException:
        return None


async def log_claim(
    bot,
    title: str,
    description: str,
    success: bool,
) -> None:
    """
    Staff-only Discord log.

    This never sends anything to the public Rust chat.
    """
    if not CLAIM_LOG_CHANNEL_ID:
        return

    channel = bot.get_channel(
        CLAIM_LOG_CHANNEL_ID
    )

    if channel is None:
        try:
            channel = await bot.fetch_channel(
                CLAIM_LOG_CHANNEL_ID
            )

        except discord.HTTPException:
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
        await channel.send(
            embed=embed
        )

    except discord.HTTPException:
        logger.exception(
            "Failed to send claim log"
        )


async def handle_reward_trigger(
    bot,
    rcon_service,
    player_name: str,
    phrase: str,
    requested_package: str,
) -> dict:
    """
    Process a VIP kit trigger.

    Important:
    - Failed attempts stay hidden from public Rust chat.
    - Cooldowns stay hidden from public Rust chat.
    - Only successful kit claims are publicly announced.
    """
    link = await get_link_by_gamertag(
        player_name
    )

    if not link:
        logger.info(
            (
                "Hidden reward rejection: "
                "%s is not linked."
            ),
            player_name,
        )

        return {
            "delivered": False,
            "reason": "not_linked",
        }

    member = await fetch_member(
        bot,
        int(link["discord_id"]),
    )

    if member is None:
        logger.warning(
            (
                "Hidden reward rejection: "
                "Discord member for %s "
                "could not be found."
            ),
            player_name,
        )

        return {
            "delivered": False,
            "reason": "member_not_found",
        }

    owned_package = get_package_for_member(
        member
    )

    if owned_package != requested_package:
        logger.info(
            (
                "Hidden reward rejection: "
                "%s owns %s but requested %s."
            ),
            player_name,
            owned_package,
            requested_package,
        )

        return {
            "delivered": False,
            "reason": "wrong_vip_tier",
            "owned": owned_package,
            "requested": requested_package,
        }

    display_name, commands, cooldown = (
        PACKAGE_SETTINGS[
            requested_package
        ]
    )

    remaining = (
        await get_action_cooldown_remaining(
            player_name,
            requested_package,
            cooldown,
        )
    )

    if remaining > 0:
        logger.info(
            (
                "Hidden reward cooldown: "
                "%s tried %s with %s remaining."
            ),
            player_name,
            requested_package,
            format_duration(remaining),
        )

        return {
            "delivered": False,
            "reason": "cooldown",
            "remaining_seconds": remaining,
        }

    if not commands:
        logger.error(
            (
                "%s reward commands "
                "are not configured."
            ),
            requested_package,
        )

        return {
            "delivered": False,
            "reason": "no_commands_configured",
        }

    safe_player = clean_rust_text(
        player_name
    )

    details: list[str] = []
    success = True

    for template in commands:
        command = template.format(
            player=safe_player
        )

        sent, response = (
            await rcon_service.send_command(
                command
            )
        )

        details.append(
            f"{command} -> {response}"
        )

        if not sent:
            success = False
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
        try:
            announced, announce_response = (
                await announce_reward(
                    rcon_service,
                    player_name,
                    display_name,
                )
            )

            if not announced:
                logger.warning(
                    (
                        "Kit delivered but public "
                        "announcement failed: %s"
                    ),
                    announce_response,
                )

        except Exception:
            logger.exception(
                (
                    "Kit delivered but public "
                    "announcement raised an error"
                )
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
            f"**Trigger:** `{phrase}`\n"
            f"**Commands:** {len(commands)}\n"
            f"**Public announcement:** "
            f"{'Yes' if success else 'No'}"
        ),
        success,
    )

    return {
        "delivered": success,
        "package": requested_package,
        "detail": detail,
    }


async def handle_outpost_trigger(
    bot,
    rcon_service,
    player_name: str,
    phrase: str,
    user_id: int | None,
) -> dict:
    """
    Process Outpost teleport privately.

    Outpost attempts and successful teleports are not announced
    in public Rust chat.
    """
    link = await get_link_by_gamertag(
        player_name
    )

    if not link:
        logger.info(
            (
                "Hidden Outpost rejection: "
                "%s is not linked."
            ),
            player_name,
        )

        return {
            "delivered": False,
            "reason": "not_linked",
        }

    if not user_id:
        logger.warning(
            (
                "Hidden Outpost rejection: "
                "missing Rust ID for %s."
            ),
            player_name,
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
        logger.error(
            "Outpost coordinates are not configured."
        )

        return {
            "delivered": False,
            "reason": "outpost_not_configured",
        }

    remaining = (
        await get_action_cooldown_remaining(
            player_name,
            "outpost",
            OUTPOST_COOLDOWN_SECONDS,
        )
    )

    if remaining > 0:
        logger.info(
            (
                "Hidden Outpost cooldown: "
                "%s has %s remaining."
            ),
            player_name,
            format_duration(remaining),
        )

        return {
            "delivered": False,
            "reason": "cooldown",
            "remaining_seconds": remaining,
        }

    command = (
        f"global.teleportpos "
        f"{OUTPOST_X} "
        f"{OUTPOST_Y} "
        f"{OUTPOST_Z} "
        f'"{int(user_id)}"'
    )

    sent, response = (
        await rcon_service.send_command(
            command
        )
    )

    await store_vip_claim(
        int(link["discord_id"]),
        player_name,
        "outpost",
        phrase,
        sent,
        f"{command} -> {response}",
    )

    await log_claim(
        bot,
        (
            f"{'✅' if sent else '❌'} "
            "Outpost teleport"
        ),
        (
            f"**Player:** `{player_name}`\n"
            f"**User ID:** `{user_id}`\n"
            "**Public announcement:** No"
        ),
        sent,
    )

    return {
        "delivered": sent,
        "action": "outpost",
        "detail": response,
    }


async def announce(
    *args,
    **kwargs,
) -> tuple[bool, str]:
    """
    Backwards-compatible announcement function used by services/rcon.py.

    Supports:
    
announce(rcon_service, message)
announce(bot, message)
announce(rcon_service=..., message=...)
"""

    rcon_service = kwargs.get("rcon_service")
    message = kwargs.get("message")

    for argument in args:
        if hasattr(argument, "send_command"):
            rcon_service = argument

        elif hasattr(argument, "rcon_service"):
            rcon_service = argument.rcon_service

        elif isinstance(argument, str):
            message = argument

    if rcon_service is None:
        return False, "RCON service was not provided."

    if not message:
        return False, "Announcement message was empty."

    return await send_public_rust_message(
        rcon_service,
        str(message),
    )