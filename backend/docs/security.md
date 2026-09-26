# Authentication, RBAC, and audit

The hackathon backend uses a local identity provider with an explicit
`IdentityProvider` interface. A future LDAP/AD adapter can implement the same interface
without changing HTTP handlers.

This is an MVP security boundary, not a claim of legal compliance by itself. Production
deployment still requires an approved personal-data threat model, TLS, secret storage,
retention rules, backups, access reviews, and integration with the customer's identity
infrastructure.

## Bootstrap

Set these values before the first API startup:

```dotenv
JWT_SECRET=replace-with-at-least-32-random-characters
JWT_ISSUER=sensor-predictive-backend
JWT_ACCESS_TTL=1h
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=replace-with-at-least-12-characters
```

The bootstrap account is inserted only when its normalized username does not already
exist. Its password is not overwritten on later restarts. Remove
`BOOTSTRAP_ADMIN_PASSWORD` from the runtime environment after the first successful
startup.

Passwords are stored as Argon2id hashes with random salts. JWT access tokens use
HS256, expire after the configured TTL, and must be sent as:

```http
Authorization: Bearer <access_token>
```

Health and login endpoints are public. Business data requires authentication.

## Roles

| Role | Read telemetry, predictions, objects, incidents | Change incidents | View imports | Manage users/audit |
|---|---:|---:|---:|---:|
| `admin` | yes | yes | yes | yes |
| `dispatcher` | yes | yes | no | no |
| `analyst` | yes | no | yes | no |
| `manager` | yes | no | no | no |

Only administrators can publish a sensor event through HTTP. Normal importer,
simulator, and model pipelines use Kafka directly.

## Initial workflow

Authenticate:

```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-bootstrap-password"}'
```

Create a dispatcher using the returned token:

```bash
curl -X POST http://localhost:8080/api/v1/users \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"username":"dispatcher1","password":"a-long-unique-password","role":"dispatcher"}'
```

Native browser `EventSource` cannot attach an Authorization header. Until cookie-based
authentication is added, the frontend should consume the protected SSE endpoint using
`fetch` streaming with the Bearer header.

## Audit

Successful incident mutations, user creation, telemetry publication, and successful or
failed login attempts are written to `audit_logs`. Only an administrator can read
`GET /api/v1/audit-logs`.

Audit records contain usernames, request paths, remote IP addresses, resource IDs, and
timestamps. Never put passwords, access tokens, or raw request bodies into audit
details.
