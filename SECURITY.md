# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 2.0.x   | ✅ Active support  |
| 1.0.x   | ⚠️ Critical fixes only |
| < 1.0   | ❌ No longer supported |

## Reporting a Vulnerability

If you discover a security vulnerability in ProjectCompass, please report it responsibly.

### How to Report

**Email**: [giacomo.saccaggi@gmail.com](mailto:giacomo.saccaggi@gmail.com)

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### What to Expect

- **Acknowledgment** within 48 hours
- **Assessment** within 1 week
- **Fix timeline** communicated after assessment
- **Credit** in the changelog (unless you prefer anonymity)

### Scope

The following are in scope:
- Authentication bypass
- Authorization flaws (RBAC escalation)
- SQL injection (DuckDB or SQLite)
- Code execution via the analysis sandbox
- API token leakage
- Cross-site scripting (XSS)
- Sensitive data exposure

### Out of Scope

- Denial of service (DoS) attacks
- Social engineering
- Issues in third-party dependencies (report upstream)
- Issues requiring physical access to the server

### Safe Harbor

We will not take legal action against researchers who:
- Act in good faith
- Avoid accessing other users' data
- Do not disrupt service availability
- Report findings promptly and privately

## Security Best Practices for Operators

- Always set a strong `SECRET_KEY` in production
- Use `ADMIN_PASSWORD_HASH` (never plaintext passwords)
- Restrict `ALLOWED_ORIGINS` to your domain
- Keep Docker image updated (`docker compose pull`)
- Review API tokens periodically via `/settings`
- Monitor the audit log at `/admin/metrics`
