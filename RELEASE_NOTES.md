# Release notes

## 0.5.0 — 2026-09-09

### Budgets

- Give every user a private budget per occasion and folder ([NEU-1275](https://linear.app/neuroticsasquatch/issue/NEU-1275)) ([#175](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/175))

### Claims

- Move the claim onto its own table with what it cost ([NEU-1268](https://linear.app/neuroticsasquatch/issue/NEU-1268)) ([#172](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/172))
- File each claim under one occasion ([NEU-1269](https://linear.app/neuroticsasquatch/issue/NEU-1269)) ([#173](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/173))
- Serve each shopping tab the caller's own claims ([NEU-1273](https://linear.app/neuroticsasquatch/issue/NEU-1273)) ([#174](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/174))
- Count what each viewer still has to buy on a list row ([NEU-1279](https://linear.app/neuroticsasquatch/issue/NEU-1279)) ([#176](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/176))

### Families

- Retire simple mode ([NEU-1260](https://linear.app/neuroticsasquatch/issue/NEU-1260)) ([#169](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/169))

### Folders

- Rename occasions to folders ([NEU-1258](https://linear.app/neuroticsasquatch/issue/NEU-1258)) ([#168](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/168))

### Occasions

- Add the family occasion, its CRUD and its role gate ([NEU-1263](https://linear.app/neuroticsasquatch/issue/NEU-1263)) ([#170](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/170))

### Sharing

- Share a list to an occasion, not to a family ([NEU-1265](https://linear.app/neuroticsasquatch/issue/NEU-1265)) ([#171](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/171))

## 0.4.0 — 2026-09-08

### Account

- Shared accounts — schema, migrations, and API ([NEU-1228](https://linear.app/neuroticsasquatch/issue/NEU-1228)) ([#160](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/160))

### Lists

- One shared scope carrying shared_via ([NEU-1227](https://linear.app/neuroticsasquatch/issue/NEU-1227)) ([#159](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/159))
- Drop recipient_has_account ([NEU-1230](https://linear.app/neuroticsasquatch/issue/NEU-1230)) ([#161](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/161))

### Migrations

- Make families migration idempotent and drop stray temp-table op

### Occasions

- Rename collections to occasions ([NEU-1226](https://linear.app/neuroticsasquatch/issue/NEU-1226)) ([#158](https://github.com/neuroticsasquat-ch/boone-gifts-backend/pull/158))

## [0.3.0] - 2026-06-29

### 🚀 Features

- Add LinkPreview.net fallback for URL metadata fetching
- Add families/family_members models and users.simple_mode (M1) (#89)
- *(families)* Add families CRUD API with organizer-role enforcement (NEU-336) (#90)
- *(families)* Add member leave/remove and role promote/demote endpoints (NEU-337) (#91)
- *(access)* Add can_view_list predicate and route ViewableList through it (NEU-338) (#92)
- *(lists)* Add filter=family to return family co-members' gift lists (#93)
- *(families)* Unclaim gifts and drop collection items when membership ends (#94)
- *(collections)* Gate add_item on can_view_list to allow family-visible lists (#95)
- *(families)* Add family_invites model and M3 migration (NEU-342) (#96)
- *(families)* Add family invites API (NEU-343) (#97)
- *(family-invites)* Add accept/decline endpoints and incoming invite listing (NEU-344) (#98)
- *(auth)* Support registration via family invite token (NEU-345) (#99)
- *(auth)* Add simple_mode JWT claim and profile toggle (NEU-352) (#106)
- *(auth)* Propagate simple_mode from family invite to new user on registration (NEU-353) (#107)

### 🐛 Bug Fixes

- Block list deletion when gifts are claimed (#70)
- Use realistic User-Agent for URL metadata fetching
- Add Walmart captcha title to useless-title blocklist
- Delete related shares, collection items, and gifts before deleting a list
- *(ci)* Merge main into dependency branch via PR instead of force-push
- Support partial profile updates so simple-mode toggle works (#110)

### 📚 Documentation

- *(claude-md)* Document family groups + simple_mode feature (NEU-356) (#109)

### 🧪 Testing

- *(families)* Add edge-case tests for cascade delete and organizer guard (NEU-355) (#108)

### ⚙️ Miscellaneous Tasks

- Set specs_dir to docs so loop/implementit find specs+plans (NEU-355) (#105)
## [0.2.1] - 2026-05-25

### 🚀 Features

- Registration improvements, user search, and cascade delete

### 🐛 Bug Fixes

- Use production-safe SMTP defaults and add .env.example
- Handle naive datetime comparison in invite validity check
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
