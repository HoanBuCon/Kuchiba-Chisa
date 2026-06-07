import { PermissionFlagsBits } from 'discord.js';

export function isGuildModeratorOrAdmin(member) {
  if (!member) return false;
  // Check if member is Administrator or ManageGuild
  if (member.permissions.has(PermissionFlagsBits.Administrator) || member.permissions.has(PermissionFlagsBits.ManageGuild)) {
    return true;
  }
  // Check if member has a role matching moderator/mod/admin (case-insensitive)
  if (member.roles && member.roles.cache) {
    return member.roles.cache.some((role) =>
      /moderator|mod|admin/i.test(role.name)
    );
  }
  return false;
}
