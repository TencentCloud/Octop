# Security Checklist (OWASP-Based)

## General
- [ ] No secrets in code or git (use `.env`).
- [ ] Dependencies are audited (`npm audit`, `pip-audit`).
- [ ] Use HTTPS everywhere (no mixed content).

## Python (Flask/FastAPI)
- [ ] Security headers set (e.g. FastAPI/Starlette middleware, or Flask-Talisman); secure cookie settings.
- [ ] SQL injection prevention (ORM or parametrized queries only).
- [ ] Rate limiting enabled (e.g. `Flask-Limiter`, `slowapi`).

## Node.js (Express)
- [ ] Use `helmet` middleware.
- [ ] Input validation (Joi/Zod) on all endpoints.
- [ ] Sanitize HTML inputs (XSS prevention).

## Docker
- [ ] Run as non-root user.
- [ ] Pin base image versions (e.g. `python:3.11-slim`, not `latest`).
- [ ] Minimal base images (Alpine/Distroless).
