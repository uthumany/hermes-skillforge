# Security Policy

## Supported Versions

Only the latest release is actively maintained. Please upgrade to the newest
tag before reporting issues.

## Reporting a Vulnerability

We take security seriously. If you discover a vulnerability — for example, a
secret leak path, unsafe command injection, or a validation bypass — please
open a GitHub issue with the **Security** label, or email the maintainer
directly. Do not include live secrets, credentials, or tokens in issues or
discussions.

## What we guarantee

- Detected secrets are redacted from all generated skill output.
- The conversion engine never executes remote code; scripts marked as
  host-dependent are only statically validated.
- The engine is stdlib-only Python with zero third-party dependencies.
