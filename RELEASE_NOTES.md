## [0.1.0] - 2026-05-23

### 🚀 Features

- *(config)* Fail startup on placeholder JWT secret (NEU-211) (#27)
- *(auth)* Rate-limit login/register/refresh with slowapi (NEU-210) (#28)
- *(email)* Add send_email service with SMTP and log providers (NEU-208) (#29)
- *(invites)* Email invitees with their registration link (NEU-212) (#30)
- *(auth)* Password reset flow with token invalidation (NEU-213) (#31)
- *(auth)* POST /auth/change-password endpoint (NEU-209) (#32)
- SQLite backup script and setup docs (NEU-219) (#37)
- Add Sentry error monitoring integration (#38)

### 🐛 Bug Fixes

- Harden production docker-compose (NEU-217) (#36)

### ⚙️ Miscellaneous Tasks

- Migrate deployment off Azure to Coolify (#22)
- Add healthcheck to prod compose
- *(tests)* Silence two unrelated deprecation warnings (#33)
- Merge main into release/v0.1.0
