# Backlog

> **Note:** Items in this backlog are **intentionally deferred**. They are improvements, not urgent fixes.
>
> **Priority:** Focus on new features first. Only work on backlog items during:
>
> * Downtime between features
> * When specifically needed for new functionality
> * Learning/practice sessions

---

## 🔧 Code Quality (Low Priority)

### Type Hints

* [ ] Add consistent type hints across all modules
* [ ] Add return type annotations to all functions
* [ ] Type hint `**kwargs` parameters properly
* **Impact:** Better IDE support, not blocking functionality
* **Effort:** ~2–3 hours
* **Do when:** Onboarding new developers or Python 3.12+ migration

### Documentation

* [ ] Add docstrings to core classes (Selfbot, Module, Listener)
* [ ] Document public methods in modules
* [ ] Create inline comments for complex logic
* **Impact:** Easier maintenance, not urgent
* **Effort:** ~4–5 hours
* **Do when:** Project reaches 10+ modules or open-sourcing

### Code Organization

* [ ] Extract duplicate error handling patterns into decorator
* [ ] Consider splitting large modules (e.g., `debug.py` is 200+ lines)
* [ ] Standardize naming: `on_*` vs `cmd_*` vs handlers
* **Impact:** Slight readability improvement
* **Effort:** ~3–4 hours
* **Do when:** Code duplication reaches 3+ instances

---

## 🧞 Testing (Nice to Have)

### Unit Tests

* [ ] Add tests for critical paths (database operations)
* [ ] Test listener registration/unregistration
* [ ] Mock Telegram API responses
* **Impact:** Prevent regressions
* **Effort:** ~8–10 hours
* **Do when:** After 5+ modules are stable or before v1.0 release

### Integration Tests

* [ ] Test module loading/unloading
* [ ] Test event dispatching flow
* [ ] Test database connection handling
* **Impact:** Confidence in deployments
* **Effort:** ~6–8 hours
* **Do when:** Team grows or CI/CD is set up

---

## 🚀 Features (Someday/Maybe)

### Core Enhancements

* [ ] Add command aliases (e.g., `p` and `ping` both work)
* [ ] Implement module hot-reload without restart
* [ ] Add rate limiting per command
* [ ] Create admin-only command decorator
* [ ] Add logging levels configuration

### New Modules

* [ ] Stats module (message count, uptime, etc.)
* [ ] Reminder/scheduler module
* [ ] Auto-reply module with patterns
* [ ] Media group support in handlers
* [ ] Backup/restore database command

### User Experience

* [ ] Better error messages for users
* [ ] Command autocomplete hints
* [ ] Inline help with examples
* [ ] Multi-language support

---

## 🔒 Security (Review Later)

* [ ] Audit database query injection points
* [ ] Review eval/exec usage in debug module (already safe with aexec, but double-check)
* [ ] Add command permission system
* [ ] Sanitize user inputs in telegraph module
* **Do when:** Before making repo public or adding contributors

---

## 📦 Infrastructure

### Docker

* [ ] Multi-platform build (arm64 support)
* [ ] Health check endpoint
* [ ] Optimize image size (currently ~200 MB, could be smaller)
* **Do when:** Deploying to ARM servers or optimizing costs

### Database

* [ ] Add database migration system (Alembic)
* [ ] Database backup automation
* [ ] Connection pool optimization
* **Do when:** Schema changes become frequent

### Deployment

* [ ] CI/CD pipeline (GitHub Actions)
* [ ] Automated testing on PR
* [ ] Release automation
* **Do when:** Multiple contributors join

---

## 🐛 Known Issues (Non-Critical)

* [ ] Long-running eval commands (>15 min) might timeout
* [ ] Large purge operations (>1000 messages) need better batching
* [ ] Telegraph module doesn’t handle all HTML edge cases
* **Impact:** Edge cases, not common usage
* **Fix when:** User reports or when working on related features

---

## 📚 Documentation (External)

* [ ] README with setup instructions
* [ ] Module development guide
* [ ] Configuration examples
* [ ] FAQ for common issues
* [ ] Architecture overview diagram
* **Do when:** Open-sourcing or team expansion

---

## 🎯 Decision Rules

### ✅ Work on Backlog Item If:

1. It’s blocking a new feature you’re building **right now**
2. The same issue appeared 3+ times in different places
3. A user explicitly requested it
4. You have genuine downtime (no active features in progress)

### ❌ Don’t Work on Backlog If:

1. “It would be nice to have…”
2. “Maybe someday we’ll need…”
3. “This could be cleaner…”
4. You’re in the middle of implementing a feature

---

## 📊 Backlog Stats

* **Total Items:** 40+
* **Estimated Total Effort:** 30–40 hours
* **Current Priority:** **NEW FEATURES > Backlog**

---

## 🛠️ Review Schedule

* Review backlog: **Monthly** (or when 10+ new features are added)
* Promote to “Now”: Only if blocking current work
* Archive completed: Move to `CHANGELOG.md`

---

**Last Updated:** 2025-10-19
**Next Review:** 2025-11-19
