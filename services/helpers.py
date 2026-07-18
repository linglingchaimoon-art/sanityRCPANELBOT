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
            "Give the bot Manage Nicknames and place "
            "its role above the member.",
        )

    except discord.HTTPException as exc:
        return (
            False,
            f"Discord rejected the nickname update: {exc}",
        )