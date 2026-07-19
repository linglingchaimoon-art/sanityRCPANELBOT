from __future__ import annotations

import re
from typing import Optional

import discord

from config import (
    DIAMOND_VIP_ROLE_ID,
    HR_ROLE_IDS,
    STAFF_ROLE_IDS,
    ULTIMATE_VIP_ROLE_ID,
    VIP_ROLE_ID,
)


def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True

    return any(
        role.id in STAFF_ROLE_IDS
        for role in member.roles
    )


def is_hr(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True

    return any(
        role.id in HR_ROLE_IDS
        for role in member.roles
    )


def get_package_for_member(
    member: discord.Member,
) -> Optional[str]:
    role_ids = {
        role.id
        for role in member.roles
    }

    if (
        ULTIMATE_VIP_ROLE_ID
        and ULTIMATE_VIP_ROLE_ID in role_ids
    ):
        return "ultimate"

    if (
        DIAMOND_VIP_ROLE_ID
        and DIAMOND_VIP_ROLE_ID in role_ids
    ):
        return "diamond"

    if (
        VIP_ROLE_ID
        and VIP_ROLE_ID in role_ids
    ):
        return "vip"

    return None


def build_nickname(
    prefix: str,
    gamertag: str,
) -> str:
    clean = " ".join(
        gamertag.strip().split()
    )

    return f"{prefix} {clean}".strip()[:32]


async def set_nickname(
    member: discord.Member,
    prefix: str,
    gamertag: str,
    reason: str,
) -> tuple[bool, str]:
    nickname = build_nickname(
        prefix,
        gamertag,
    )

    try:
        await member.edit(
            nick=nickname,
            reason=reason,
        )

        return True, nickname

    except discord.Forbidden:
        return (
            False,
            (
                "Give the bot Manage Nicknames "
                "and place its role above the member."
            ),
        )

    except discord.HTTPException as exc:
        return (
            False,
            (
                "Discord rejected the nickname "
                f"update: {exc}"
            ),
        )


def clean_rust_text(value: str) -> str:
    """
    Make text safe for a quoted Rust RCON command.
    """
    value = str(value)

    value = (
        value
        .replace('"', "'")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\u0000", "")
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


async def send_public_rust_message(
    rcon_service,
    message: str,
) -> tuple[bool, str]:
    """
    Send a message that every online Rust player can see.

    Only call this for successful kit claims, shop purchases,
    events, or other announcements intended for everyone.
    Never call it for private admin actions.
    """
    safe_message = clean_rust_text(
        message
    )

    if not safe_message:
        return False, "Message was empty."

    return await rcon_service.send_command(
        f'global.say "{safe_message}"'
    )


async def announce_reward(
    rcon_service,
    player_name: str,
    reward_name: str,
) -> tuple[bool, str]:
    """
    Public announcement for a successful VIP or kit claim.
    """
    player_name = clean_rust_text(
        player_name
    )

    reward_name = clean_rust_text(
        reward_name
    )

    message = (
        "<color=#FF3131><b>[SANITY2X]</b></color> "
        f"<color=#FFD700><b>{player_name}</b></color> "
        "<color=#FFFFFF>claimed the</color> "
        f"<color=#00E5FF><b>{reward_name}</b></color> "
        "<color=#FFFFFF>reward!</color>"
    )

    return await send_public_rust_message(
        rcon_service,
        message,
    )


async def announce_shop_purchase(
    rcon_service,
    player_name: str,
    item_name: str,
) -> tuple[bool, str]:
    """
    Public announcement for a successful Sanity Market purchase.
    """
    player_name = clean_rust_text(
        player_name
    )

    item_name = clean_rust_text(
        item_name
    )

    message = (
        "<color=#FF3131><b>[SANITY MARKET]</b></color> "
        f"<color=#FFD700><b>{player_name}</b></color> "
        "<color=#FFFFFF>purchased</color> "
        f"<color=#7CFF6B><b>{item_name}</b></color> "
        "<color=#FFFFFF>using Sanity Coins!</color>"
    )

    return await send_public_rust_message(
        rcon_service,
        message,
    )
