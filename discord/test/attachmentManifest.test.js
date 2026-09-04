import assert from 'node:assert/strict';
import test from 'node:test';

import { approvedAttachmentUrl } from '../src/security/attachmentManifest.js';

const attachmentId = 'a'.repeat(32);
const coreUrl = 'https://api.example.test';

test('accepts a Core-issued local evidence manifest', () => {
  assert.equal(
    approvedAttachmentUrl(
      {
        attachment_id: attachmentId,
        delivery_url: `/static/uploads/2026/09/${attachmentId}.webp`,
      },
      coreUrl,
    ),
    `https://api.example.test/static/uploads/2026/09/${attachmentId}.webp`,
  );
});

test('rejects model URL, local path, and malformed evidence IDs', () => {
  assert.equal(approvedAttachmentUrl('https://attacker.test/x.webp', coreUrl), null);
  assert.equal(
    approvedAttachmentUrl(
      { attachment_id: attachmentId, delivery_url: 'https://attacker.test/x.webp' },
      coreUrl,
    ),
    null,
  );
  assert.equal(
    approvedAttachmentUrl(
      { attachment_id: attachmentId, delivery_url: '../../secrets.txt' },
      coreUrl,
    ),
    null,
  );
  assert.equal(
    approvedAttachmentUrl(
      { attachment_id: 'untrusted', delivery_url: `/static/uploads/${attachmentId}.webp` },
      coreUrl,
    ),
    null,
  );
});
