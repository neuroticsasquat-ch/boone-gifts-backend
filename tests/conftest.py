"""Suite-wide fixtures.

Nothing here is about any one domain — this file exists for the settings that
have to be true before the first test builds its first user.
"""
import pytest

# Four is bcrypt's own floor, and the suite is the one place where a work factor
# is pure cost: these passwords exist for a few milliseconds inside a
# transaction that gets rolled back, and no attacker will ever see a hash of
# one. Production keeps `app.models.user.BCRYPT_ROUNDS` at 12 — this lowers it
# for the test process only, and only through that one named constant, so
# nothing about how the application hashes a real password changes here.
#
# It is worth the two lines: at 12 rounds a hash costs ~250ms, every fixture
# that builds a user pays it, and the suite spent roughly two thirds of its
# total runtime inside `bcrypt.hashpw` rather than on any assertion.
TEST_BCRYPT_ROUNDS = 4


@pytest.fixture(scope="session", autouse=True)
def _cheap_password_hashing():
    """Lower bcrypt's work factor for the whole test session.

    Session-scoped and autouse because it has to hold for every fixture that
    builds a user, including the module- and session-scoped ones that run before
    any function-scoped fixture would get a chance to patch it.

    `check_password` is unaffected: bcrypt reads the work factor out of the hash
    it is verifying, so a hash minted at 4 rounds verifies exactly as one minted
    at 12 does. The algorithm under test is the same one; only its cost changes.
    """
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.models.user.BCRYPT_ROUNDS", TEST_BCRYPT_ROUNDS)
        yield


@pytest.fixture(scope="session", autouse=True)
def _email_goes_to_the_log():
    """Keep the suite's email off the network, whatever `.env` says.

    Local `.env` points the provider at the shared Mailpit so the running app's
    mail can be read there, and the tests load the same file. Without this, every
    test that sends an invite or a reset delivers a real message over SMTP. The
    tests that exercise the smtp and resend senders still patch the provider in
    for themselves, and get "log" back when they finish.
    """
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("app.config.settings.email_provider", "log")
        yield
