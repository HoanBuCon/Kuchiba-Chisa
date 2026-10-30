// Guild moderation authority for destructive/administrative bot commands (B-3, FR-CH-003).
//
// Authority comes ONLY from Discord-verified permission flags or from an explicit
// allowlist of role IDs configured by the operator (DISCORD_MODERATOR_ROLE_IDS).
// Role *names* are user-controlled display text and are never trusted: a role named
// "Model", "Mod fan" or "admin-wannabe" must not grant moderation rights.

const MODERATION_PERMISSION_FLAGS = ['Administrator', 'ManageGuild'];
const SNOWFLAKE = /^\d{17,20}$/;

export function parseModeratorRoleIds(value = process.env.DISCORD_MODERATOR_ROLE_IDS) {
  if (!value) return new Set();
  return new Set(
    String(value)
      .split(',')
      .map((item) => item.trim())
      .filter((item) => SNOWFLAKE.test(item)),
  );
}

export function isGuildModeratorOrAdmin(member, { moderatorRoleIds = parseModeratorRoleIds() } = {}) {
  if (!member) return false;

  const permissions = member.permissions;
  if (permissions && typeof permissions.has === 'function') {
    for (const flag of MODERATION_PERMISSION_FLAGS) {
      if (permissions.has(flag)) return true;
    }
  }

  if (moderatorRoleIds.size === 0) return false;
  const roleCache = member.roles?.cache;
  if (!roleCache || typeof roleCache.has !== 'function') return false;
  for (const roleId of moderatorRoleIds) {
    if (roleCache.has(roleId)) return true;
  }
  return false;
}
