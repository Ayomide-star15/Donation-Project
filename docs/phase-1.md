# Phase 1 — Super Admin

Phase 1 is delivered as vertical slices. A slice is complete only when its migration,
API behavior, authorization, audit events, and tests are complete.

## 1. Foundation and authentication

- [x] Remove Supabase coupling
- [x] Add PostgreSQL, SQLAlchemy, and Alembic
- [x] Combine identity and password credentials in `users`
- [x] Add Argon2id password hashing
- [x] Add single-use, expiring email OTP challenges
- [x] Protect OTPs with keyed HMAC hashing
- [x] Add opaque, hashed server-side sessions
- [x] Add provider-neutral console and SMTP email adapters
- [x] Add session listing and revocation
- [x] Add login lockout and authentication audit events
- [x] Add Super Admin bootstrap command
- [ ] Add production transactional email provider
- [ ] Add password-reset flow
- [ ] Execute automated tests against PostgreSQL in CI

## 2. Authorization and platform policy

- [x] Add roles, permissions, and role assignments schema
- [x] Add protected-route and Super Admin role dependencies
- [ ] Seed the complete Phase 1 permission catalog
- [ ] Add permission-based dependencies and tests

## 3. Hospital management

- [ ] Hospital schema and migration
- [ ] Create, list, search, read, update, and deactivate APIs
- [ ] Super Admin permissions and audit events
- [ ] Integration tests

## 4. Community management

- [ ] Community schema and migration
- [ ] Optional hospital association
- [ ] Create, list, search, read, update, and suspend APIs
- [ ] Super Admin permissions and audit events
- [ ] Integration tests

## 5. Community Admin invitations

- [ ] Hashed, expiring, single-use invitation records
- [ ] Create, resend, revoke, inspect, and accept APIs
- [ ] Community-scoped role assignment on acceptance
- [ ] Transactional email integration
- [ ] Audit events and edge-case tests

## 6. User administration

- [ ] User directory and filters
- [ ] User details
- [ ] Suspend and restore operations
- [ ] Immediate session revocation on suspension
- [ ] Authorization and audit tests

## 7. Audit and dashboard

- [x] Append-only audit-log foundation
- [ ] Audit list/detail APIs and filters
- [ ] Dashboard summary API
- [ ] Retention and sensitive-data policy

## Phase 1 acceptance scenario

```text
Bootstrap Super Admin
→ log in with password
→ verify email OTP
→ create hospital
→ create community
→ invite Community Admin
→ suspend and restore a user
→ inspect every privileged action in the audit log
→ revoke the session
```
