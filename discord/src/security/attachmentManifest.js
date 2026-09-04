const IMAGE_ID = /^[a-f0-9]{32}$/;

/**
 * Convert a Core-issued local attachment manifest to a Discord-safe URL.
 * Strings, filesystem paths, foreign origins, and malformed evidence IDs fail closed.
 */
export function approvedAttachmentUrl(attachment, coreBaseUrl) {
  if (!attachment || typeof attachment !== 'object') return null;
  if (!IMAGE_ID.test(attachment.attachment_id ?? '')) return null;
  if (typeof attachment.delivery_url !== 'string') return null;

  try {
    const coreUrl = new URL(coreBaseUrl);
    const deliveryUrl = new URL(attachment.delivery_url, coreUrl);
    const expectedSuffix = `/${attachment.attachment_id}.webp`;
    if (
      deliveryUrl.origin !== coreUrl.origin
      || !deliveryUrl.pathname.startsWith('/static/uploads/')
      || !deliveryUrl.pathname.endsWith(expectedSuffix)
      || deliveryUrl.search
      || deliveryUrl.hash
    ) {
      return null;
    }
    return deliveryUrl.toString();
  } catch {
    return null;
  }
}
