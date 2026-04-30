# Security Policy

Please do not open public issues containing secrets, tokens, credentials, private endpoint URLs, or customer data.

## Reporting

If you discover a vulnerability, report it privately to the project maintainer or security contact configured for the GitHub repository.

## Secret Handling

Runtime secrets must be supplied through environment variables. The repository should only contain placeholders in `.env.example`.
