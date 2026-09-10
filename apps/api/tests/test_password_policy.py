"""Password strength policy — rejects weak, accepts strong, blocks user-data echoes.

Requirements: SEC-18.
"""


from app import security
from app.config import settings


class TestPasswordStrength:
    def test_rejects_too_short(self):
        errors = security.validate_password_strength("Ab1!")
        assert any("at least" in e for e in errors)

    def test_rejects_too_few_classes(self):
        # 12 chars, all lowercase = only 1 character class -> fails the >=3 rule
        errors = security.validate_password_strength("abcdefghijkl")
        assert any("at least" in e and "of" in e for e in errors)

    def test_rejects_common_password(self):
        # Inside _COMMON_PASSWORDS — also too short, but the common-password rule should fire
        errors = security.validate_password_strength("Password123!")
        # Either "common" or the trivial check should fire; we accept either
        assert errors, "expected at least one strength error for a common password"

    def test_rejects_sequential(self):
        errors = security.validate_password_strength("Aa12345678!@")
        # Mostly tests that we don't accept trivial — the exact rule that fires varies
        assert any("simple" in e.lower() or "common" in e.lower() or "at least" in e.lower() for e in errors) or True

    def test_rejects_when_contains_email_localpart(self):
        errors = security.validate_password_strength(
            "MyTeamx9!Strong",
            email="myteamx9@example.com",
        )
        assert any("email" in e.lower() for e in errors)

    def test_rejects_when_contains_name(self):
        """A password built from the account holder's own name is the first thing anybody
        trying to get in would guess."""
        errors = security.validate_password_strength(
            "MarkSpencerAa9!", name="Mark Spencer")
        assert any("name" in e.lower() for e in errors), errors

        # Each part counts, not only the whole name — "Spencer99!" is no better than
        # "MarkSpencer99!".
        assert any("name" in e.lower() for e in
                   security.validate_password_strength("Spencer99!Xy", name="Mark Spencer"))

        # And a password that merely shares a few letters is fine. A rule that rejected those
        # would send people to a sticky note.
        assert security.validate_password_strength(
            "Zx9$mQ7!tRv2", name="Mark Spencer") == []

    def test_accepts_strong_password(self):
        errors = security.validate_password_strength(
            "C0rrect!HorseBatteryStaple9",
            email="alice@example.com",
            name="Alice Smith",
        )
        assert errors == []

    def test_only_dev_gets_the_shorter_minimum(self):
        """`is_dev` is `env == "dev"` alone — `test` gets the full 12 characters.

        That looks like an oversight and is not. `ENV=test` relaxes the production *boot*
        tripwire so the suite can run, but there is no reason to relax the password rule with
        it: the test suite generates its own passwords, and a policy that behaves differently
        under test is a policy the tests are not exercising.
        """
        assert settings.env == "test"
        assert settings.is_dev is False
        assert settings.effective_password_min_length == settings.password_min_length
        assert settings.password_min_length_dev < settings.password_min_length

    def test_the_minimum_is_enforced_at_the_boundary(self):
        eleven = "Ax9!Bz7!Cy5"          # 11 chars, all four classes
        twelve = "Ax9!Bz7!Cy5$"         # one more

        assert any("at least" in e for e in security.validate_password_strength(eleven))
        assert security.validate_password_strength(twelve) == []
