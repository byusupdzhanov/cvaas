# Contributing to CVaaS

Thanks for contributing.

## Before You Start

- Check existing issues or discussions first if you plan a bigger change.
- Prefer small, focused pull requests over large mixed changes.
- If you change behavior, update the documentation too.

## Local Setup

```bash
git clone git@github.com:byusupdzhanov/cvaas.git
cd cvaas
./setup.sh
```

If you already have a local setup, make sure the app still starts after your changes.

## What to Keep in Mind

- Preserve the self-hosted, simple deployment model.
- Avoid introducing heavy infrastructure assumptions by default.
- Keep the UI clean and practical.
- Prefer readable code over clever code.
- Do not commit secrets, private `.env` files, local databases, or uploaded assets.

## Pull Request Guidelines

Include:
- what problem you are solving;
- what changed;
- anything user-visible in the UI or UX;
- screenshots if the change affects the interface;
- migration or setup notes if required.

## Code Style

- Keep changes narrow in scope.
- Reuse existing patterns unless there is a good reason to change them.
- Avoid breaking existing resume data or admin workflows.
- If you touch security-sensitive flows, explain the reasoning in the PR description.

## Testing

At minimum, verify:
- the app starts;
- login works;
- admin pages still save correctly;
- public resume rendering still works;
- print / PDF behavior is not broken if your change affects the resume layout.

## Documentation

Update `README.md` when you change:
- installation flow;
- environment variables;
- public behavior;
- major UI flows.
