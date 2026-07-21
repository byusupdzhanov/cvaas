# Security Policy

## Supported Versions

CVaaS is a small self-hosted project, so security fixes are generally applied to the current mainline version rather than maintained across a wide range of old releases.

If you report a valid security issue, the fix will be prepared for the current actively maintained codebase.

## Reporting a Vulnerability

Please do **not** open a public GitHub issue for security vulnerabilities.

Instead, report it privately to:

- Email: [byusupdzhanov@mail.ru](mailto:byusupdzhanov@mail.ru)
- Telegram: [@dontbesoseriouspls](https://t.me/dontbesoseriouspls)

Please include:
- a clear description of the issue;
- reproduction steps;
- potential impact;
- affected files or flows if you know them;
- a proof of concept if it is safe to share.

## What to Expect

- I will review the report privately.
- If the issue is confirmed, I will prepare a fix.
- Public disclosure should ideally happen after a fix is available.

## Scope

Relevant examples:
- authentication and session issues;
- admin panel access bypass;
- CSRF or brute-force weaknesses;
- file upload issues;
- data exposure;
- vulnerabilities that allow code execution or unauthorized data modification.

Non-security bugs such as layout issues, ordinary validation bugs, or low-impact UX problems should go to the normal issue tracker.
