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

PACKAGE_SETTINGS = {
    "vip": ("VIP", VIP_COMMANDS, VIP_COOLDOWN_SECONDS),
    "diamond": ("Diamond VIP", DIAMOND_COMMANDS, DIAMOND_COOLDOWN_SECONDS),
    "ultimate": ("Ultimate VIP", ULTIMATE_COMMANDS, ULTIMATE_COOLDOWN_SECONDS),
}


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def safe_text(value: str) -> str:
    return value.replace('"', "").replace("\n", " ").replace("\r", " ").strip()


async def fetch_member(bot, discord_id: int):
    guild = bot.get_guild(bot.guild_id)
    if guild is None:
        return None
    member = guild.get_member(discord_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(discord_id)
    except discord.HTTPException:
        return None


async def announce(rcon_service, text: str) -> None:
    if not INGAME_MESSAGES_ENABLED:
        return
    clean = safe_text(f"{SERVER_MESSAGE_PREFIX} {text}")
    await rcon_service.send_command(f'global.say "{clean}"')


async def log_claim(bot, title: str, description: str, success: bool) -> None:
    if not CLAIM_LOG_CHANNEL_ID:
        return
    channel = bot.get_channel(CLAIM_LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(CLAIM_LOG_CHANNEL_ID)
        except discord.HTTPException:
            return
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green() if success else discord.Color.red(),
    )
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        logger.exception("Failed to send claim log")


async def handle_reward_trigger(bot, rcon_service, player_name: str, phrase: str, requested_package: str) -> dict:
    link = await get_link_by_gamertag(player_name)
    if not link:
        await announce(rcon_service, f"{player_name}: link your Discord account with /link first.")
        return {"delivered": False, "reason": "not_linked"}

    member = await fetch_member(bot, int(link["discord_id"]))
    if member is None:
        await announce(rcon_service, f"{player_name}: your linked Discord member could not be found.")
        return {"delivered": False, "reason": "member_not_found"}

    owned_package = get_package_for_member(member)
    if owned_package != requested_package:
        package_name = PACKAGE_SETTINGS[requested_package][0]
        await announce(rcon_service, f"{player_name}: this command requires {package_name}.")
        return {"delivered": False, "reason": "wrong_vip_tier", "owned": owned_package, "requested": requested_package}

    display_name, commands, cooldown = PACKAGE_SETTINGS[requested_package]
    remaining = await get_action_cooldown_remaining(player_name, requested_package, cooldown)
    if remaining > 0:
        await announce(rcon_service, f"{player_name}: {display_name} is on cooldown for {format_duration(remaining)}.")
        return {"delivered": False, "reason": "cooldown", "remaining_seconds": remaining}

    if not commands:
        await announce(rcon_service, f"{player_name}: {display_name} rewards are not configured.")
        return {"delivered": False, "reason": "no_commands_configured"}

    safe_player = safe_text(player_name)
    details: list[str] = []
    success = True
    for template in commands:
        command = template.format(player=safe_player)
        sent, response = await rcon_service.send_command(command)
        details.append(f"{command} -> {response}")
        if not sent:
            success = False
            break
        await asyncio.sleep(0.25)

    detail = "\n".join(details)
    await store_vip_claim(member.id, player_name, requested_package, phrase, success, detail)

    if success:
        await announce(rcon_service, f"{player_name} claimed the {display_name} kit. Next claim in {format_duration(cooldown)}.")
    else:
        await announce(rcon_service, f"{player_name}: the reward failed. Please contact staff.")

    await log_claim(
        bot,
        f"{'✅' if success else '❌'} {display_name} claim",
        f"**Player:** `{player_name}`\n**Discord:** {member.mention}\n**Trigger:** `{phrase}`\n**Commands:** {len(commands)}",
        success,
    )
    return {"delivered": success, "package": requested_package, "detail": detail}


async def handle_outpost_trigger(bot, rcon_service, player_name: str, phrase: str, user_id: int | None) -> dict:
    link = await get_link_by_gamertag(player_name)
    if not link:
        await announce(rcon_service, f"{player_name}: link your Discord account with /link first.")
        return {"delivered": False, "reason": "not_linked"}
    if not user_id:
        await announce(rcon_service, f"{player_name}: your Rust player ID could not be read. Try again.")
        return {"delivered": False, "reason": "missing_user_id"}
    if OUTPOST_X == 0.0 and OUTPOST_Y == 0.0 and OUTPOST_Z == 0.0:
        await announce(rcon_service, f"{player_name}: Outpost teleport is not configured yet.")
        return {"delivered": False, "reason": "outpost_not_configured"}

    remaining = await get_action_cooldown_remaining(player_name, "outpost", OUTPOST_COOLDOWN_SECONDS)
    if remaining > 0:
        await announce(rcon_service, f"{player_name}: Outpost teleport is on cooldown for {format_duration(remaining)}.")
        return {"delivered": False, "reason": "cooldown", "remaining_seconds": remaining}

    command = f'global.teleportpos {OUTPOST_X} {OUTPOST_Y} {OUTPOST_Z} "{int(user_id)}"'
    sent, response = await rcon_service.send_command(command)
    await store_vip_claim(int(link["discord_id"]), player_name, "outpost", phrase, sent, f"{command} -> {response}")
    if sent:
        await announce(rcon_service, f"{player_name} has been teleported to Outpost.")
    else:
        await announce(rcon_service, f"{player_name}: teleport failed. Please contact staff.")
    await log_claim(bot, f"{'✅' if sent else '❌'} Outpost teleport", f"**Player:** `{player_name}`\n**User ID:** `{user_id}`", sent)
    return {"delivered": sent, "action": "outpost", "detail": response}
