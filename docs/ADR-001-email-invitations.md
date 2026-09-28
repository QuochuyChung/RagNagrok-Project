# ADR 001: Email Invitation System for User Onboarding

## 1. Context and Problem
As a multi-tenant platform, Ragnarok needs a scalable and secure mechanism for onboarding users. Specifically, when a Platform Admin provisions a new tenant workspace, they need to simultaneously onboard the Tenant Admin. Similarly, Tenant Admins need the ability to onboard large numbers of standard users into their workspaces. 

Initially, creating user accounts involved setting manual or temporary plain-text passwords. This approach is fraught with security risks (passwords intercepted in email, failure of users to change default passwords) and presents a poor, outdated User Experience (UX). We needed to implement a system that aligns with modern SaaS best practices for secure, frictionless user onboarding.

## 2. Options Considered

### Option 1: Temporary Plain-Text Passwords
- **Description:** System generates a random password, creates the active user account, and emails the plaintext password.
- **Pros:** Easy to implement; no complex frontend logic required.
- **Cons:** Highly insecure (passwords transmitted in plaintext over email); requires users to manually navigate to a "Change Password" page after logging in; bad UX.

### Option 2: Pre-generated Accounts (SSO Only)
- **Description:** Accounts are pre-created without passwords. Users can only authenticate via an Identity Provider (IdP) like Google Workspace or Okta.
- **Pros:** Maximum security; no password management required.
- **Cons:** Inflexible. Not all tenants will have or want to integrate a dedicated IdP. It heavily restricts the platform's market adoption.

### Option 3: Token-Based Email Invitations (Magic Links)
- **Description:** Users are pre-created in an inactive state. The system generates a cryptographically secure, one-time use token with a Time-To-Live (TTL) and emails a link to the user. Clicking the link allows the user to securely set their password and activate their account.
- **Pros:** Modern UX; highly secure (no passwords sent via email); inherently verifies the user's email address; easily supports bulk onboarding.
- **Cons:** Requires SMTP infrastructure; adds complexity to both backend (token lifecycle management) and frontend (new unauthenticated routing flows).

## 3. Decision
We chose **Option 3: Token-Based Email Invitations**. 

To maximize security, we implemented the following technical decisions within this flow:
- **Hashed Tokens:** The backend generates a 32-byte secure random string, but **only the SHA-256 hash** of this string is stored in the database. The raw token is sent in the email and never persisted.
- **Inactive Pre-creation:** Invited users are inserted into the `users` table immediately with `is_active=False` and a randomly generated, locked bcrypt password hash. This ensures database constraints are met while strictly preventing login before the invitation is explicitly accepted.
- **Single-Use Verification:** Once a token is validated and a password is set, the token is stamped with an `accepted_at` timestamp, permanently invalidating it.

## 4. Consequences

### Positive
* **Security:** Immune to database leaks. Even if the `invitation_tokens` table is compromised, attackers only get SHA-256 hashes, not usable invite links.
* **UX:** Users experience a modern, seamless flow where they establish their own credentials immediately upon joining the platform.
* **Scalability:** The architecture easily supports bulk invitations. A Tenant Admin can invite 100 users in a single API call without waiting for synchronous password generation overhead.

### Negative
* **Infrastructure Dependency:** The platform now has a hard dependency on an SMTP server/service (e.g., SendGrid, AWS SES) for the onboarding flow to function.
* **Frontend Complexity:** The React application must handle unauthenticated deep-linking (`/accept-invite?token=...`) and gracefully manage token validation errors (e.g., expired or revoked tokens).

## 5. Related Decisions and Trade-offs

* **Async Email Delivery:** We decided to dispatch emails asynchronously (using `asyncio.to_thread`) so that bulk invite API calls return `202 Accepted` immediately without blocking the HTTP response. 
  * *Trade-off:* We sacrifice strict delivery guarantees. If the application crashes immediately after returning the API response but before the email thread finishes, the email is lost, though the token remains valid in the DB. In a future production iteration (Sprint 4+), this will be migrated to a durable background task queue (e.g., Celery or ARQ).
* **Role-Based Access Control (RBAC):** We restricted invitation privileges. Platform Admins can invite anyone, but Tenant Admins are restricted to only issuing `USER` role invitations bounded strictly to their own `tenant_id`.
