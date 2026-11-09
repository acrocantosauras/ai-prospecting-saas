"""Workspace roles and the permissions they grant.

The matrix is intentionally explicit rather than hierarchical arithmetic so a
reviewer can read off exactly what each role may do.

Decisions relative to the product as it exists today:

* ``viewer`` reads everything in the workspace (batches, prospects provider
  status, usage) but may not create, modify, export or cancel anything.
* ``member`` is the working role: it manages client profiles and ICPs, runs and
  cancels batches, and exports prospects. Editing prospect research fields is
  treated as profile management so the manual review workflow keeps working.
* ``admin`` adds member management and workspace settings, but cannot delete the
  workspace and cannot change owner-level memberships.
* ``owner`` adds workspace deletion. Deletion is deliberately not exposed as an
  HTTP endpoint yet (see the sprint report): the schema has no cascade rules and
  deleting a workspace would orphan batches, prospects and usage rows.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Role(StrEnum):
    """A member's role inside one workspace."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(StrEnum):
    """An action a role may perform inside one workspace."""

    VIEW_WORKSPACE = "workspace:view"
    MANAGE_PROFILES = "profiles:manage"
    RUN_BATCHES = "batches:run"
    EXPORT_PROSPECTS = "prospects:export"
    MANAGE_MEMBERS = "members:manage"
    MANAGE_SETTINGS = "settings:manage"
    DELETE_WORKSPACE = "workspace:delete"


_VIEWER: Final = frozenset({Permission.VIEW_WORKSPACE})
_MEMBER: Final = _VIEWER | {
    Permission.MANAGE_PROFILES,
    Permission.RUN_BATCHES,
    Permission.EXPORT_PROSPECTS,
}
_ADMIN: Final = _MEMBER | {
    Permission.MANAGE_MEMBERS,
    Permission.MANAGE_SETTINGS,
}
_OWNER: Final = _ADMIN | {Permission.DELETE_WORKSPACE}

ROLE_PERMISSIONS: Final[dict[Role, frozenset[Permission]]] = {
    Role.VIEWER: _VIEWER,
    Role.MEMBER: frozenset(_MEMBER),
    Role.ADMIN: frozenset(_ADMIN),
    Role.OWNER: frozenset(_OWNER),
}

ROLE_LABELS: Final[dict[Role, str]] = {
    Role.OWNER: "Owner",
    Role.ADMIN: "Admin",
    Role.MEMBER: "Member",
    Role.VIEWER: "Viewer",
}


def parse_role(value: str) -> Role | None:
    """Return the role for ``value`` or ``None`` when it is not a known role."""
    try:
        return Role(value)
    except (ValueError, TypeError):
        return None


def has_permission(role: str, permission: Permission) -> bool:
    """Return True when ``role`` grants ``permission``."""
    parsed = parse_role(role)
    if parsed is None:
        return False
    return permission in ROLE_PERMISSIONS[parsed]


def permissions_for(role: str) -> frozenset[Permission]:
    """Return the permissions granted by ``role`` (empty for unknown roles)."""
    parsed = parse_role(role)
    if parsed is None:
        return frozenset()
    return ROLE_PERMISSIONS[parsed]
