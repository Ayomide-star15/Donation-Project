# Phase 1 — Super Admin

Phase 1 is delivered as vertical slices. A slice is complete only when its migration,
API behavior, authorization, audit events, and tests are complete.

## 1. Foundation and authentication

- [x] Remove Supabase coupling
- [x] Add PostgreSQL, SQLAlchemy, and Alembic
- [x] Combine identity and password credentials in `users`
- [x] Add Argon2id password hashing
- [x] Add one-time MFA challenges and encrypted TOTP secrets
- [x] Add one-time MFA recovery codes
- [x] Add short-lived JWT access tokens
- [x] Add rotating, hashed refresh tokens and device sessions
- [x] Add session listing and revocation
- [x] Add login lockout and authentication audit events
- [x] Add Super Admin bootstrap command
- [ ] Add password-reset and email-delivery integration
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
→ enroll MFA
→ log in
→ create hospital
→ create community
→ invite Community Admin
→ suspend and restore a user
→ inspect every privileged action in the audit log
→ revoke the session
```
