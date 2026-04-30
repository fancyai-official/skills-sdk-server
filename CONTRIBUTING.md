# Contributing

Thanks for considering a contribution.

## Local Checks

```bash
bun install
bun run typecheck
bun run build
```

## Guidelines

- Keep sample apps free of real customer data, real credentials, and private infrastructure references.
- Add or update `.env.example` when introducing new configuration.
- Prefer provider adapters that fail clearly when credentials are missing.
- Do not commit generated files from `.generated/` or local conversation data from `claude-data/`.
