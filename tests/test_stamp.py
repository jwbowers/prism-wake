"""Stamping the deployed programs with the commit they were built from.

AWS replaces the whole set of environment variables when you change one, so
the only safe way to add a stamp is to read what is there, merge, and send it
back. The variable that matters most is the wake secret: it is generated once
at deployment and stored nowhere else, so losing it would break the link
already in a collaborator's browser and there would be no copy to restore.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stamp


def test_the_wake_secret_survives_a_stamp():
    """The one that would break the live link if it did not."""
    before = {"WAKE_SECRET": "the-only-copy", "INSTANCE_ID": "i-0123456789abcdef0"}

    after = stamp.merge(before, "abc1234")

    assert after["WAKE_SECRET"] == "the-only-copy"


def test_every_other_setting_survives_too():
    before = {
        "WAKE_SECRET": "s", "INSTANCE_ID": "i-0", "RSTUDIO_PORT": "8787",
        "RSTUDIO_USER": "collaborator", "IDLE_CPU_PERCENT": "5",
        "IDLE_MINUTES": "120",
    }

    after = stamp.merge(before, "abc1234")

    for key, value in before.items():
        assert after[key] == value


def test_the_commit_is_recorded():
    after = stamp.merge({"WAKE_SECRET": "s"}, "abc1234")

    assert after["GIT_COMMIT"] == "abc1234"


def test_a_second_deployment_replaces_the_old_commit():
    """Otherwise the stamp would report whatever was deployed first, forever."""
    after = stamp.merge({"GIT_COMMIT": "old1111", "WAKE_SECRET": "s"}, "new2222")

    assert after["GIT_COMMIT"] == "new2222"


def test_an_empty_environment_is_not_an_error():
    """A function created outside deploy.sh may carry nothing at all."""
    assert stamp.merge({}, "abc1234") == {"GIT_COMMIT": "abc1234"}


def test_a_refusal_rather_than_a_stamp_that_says_nothing():
    """An empty commit would produce a stamp nobody could act on.

    Reporting GIT_COMMIT as the empty string is worse than reporting nothing,
    because someone reading it would believe the question had been answered.
    """
    for useless in ("", "   ", None):
        try:
            stamp.merge({"WAKE_SECRET": "s"}, useless)
        except ValueError:
            continue
        raise AssertionError(f"merge accepted {useless!r} as a commit")


def test_the_script_runs_as_a_command_and_prints_json():
    """The Makefile calls this as a command, so that path has to work."""
    script = Path(__file__).resolve().parents[1] / "scripts" / "stamp.py"
    result = subprocess.run(
        [sys.executable, str(script), "abc1234"],
        input=json.dumps({"WAKE_SECRET": "s"}),
        capture_output=True, text=True, check=True,
    )

    assert json.loads(result.stdout) == {"WAKE_SECRET": "s", "GIT_COMMIT": "abc1234"}
