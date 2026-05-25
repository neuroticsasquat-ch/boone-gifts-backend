## [0.2.0] - 2026-05-25

### 🚀 Features

- Add computed status field to invite list response (NEU-232) (#46)
- Add self-deactivation guard and deactivation round-trip tests (NEU-234) (#47)
- Add archive lifecycle for lists and collections (NEU-243) (#49)
- Add seen tracking and unseen count endpoint for shared lists (NEU-238) (#50)
- Add email notifications, sort lists by recency, and claim count fields (NEU-239, NEU-240, NEU-242) (#51)
- Add connection lists endpoint for profile page (NEU-245) (#52)
- Add collections-for-list endpoint (NEU-247) (#53)
- Add shared users endpoint for list detail (NEU-248) (#54)
- Add profile name update endpoint (NEU-251) (#55)
- Add purchase tracking and per-collection shopping list (NEU-253) (#56)

### 🐛 Bug Fixes

- Make gift claim atomic to prevent race condition (NEU-224) (#48)
- Add list_id to ShoppingListItem schema (NEU-254) (#57)
- Chain purchase migration after seen_at migration (#58)
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
- Simplify backup script to use SSH config alias

### 📚 Documentation

- Rewrite backup setup guide to match actual deploy
- Add deploy and rollback runbook

### ⚙️ Miscellaneous Tasks

- Migrate deployment off Azure to Coolify (#22)
- Add healthcheck to prod compose
- *(tests)* Silence two unrelated deprecation warnings (#33)
- Merge main into release/v0.1.0
- Remove .env.example
