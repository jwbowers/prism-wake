"""What the timer does.

A separate function runs on a schedule and hibernates the workspace once it has
been quiet for a long stretch. The substantive claim: AWS stops billing for the
machine when nobody is using it, and it never sleeps while somebody is there.

The danger in a rule like this is asymmetric. Hibernating too late wastes a few
dollars. Hibernating too early interrupts the collaborator, and because they
are in another
country they cannot ask the owner to fix it quickly. Every test below leans
that way.
"""

import pytest

from conftest import (
    FakeCloudWatch,
    FakeEC2,
    INSTANCE_ID,
    busy_window,
    quiet_window,
)
from wake import idle


def window_with_one_busy_period(busy_at=11):
    """A quiet window interrupted by a single burst of real work."""
    points = quiet_window()
    points[busy_at] = {"Average": 61.0}
    return points


# --- the quiet machine -------------------------------------------------

def test_quiet_machine_is_hibernated(env):
    """Two hours below five percent CPU is nobody working."""
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    cw = FakeCloudWatch(quiet_window())

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    assert ec2.stop_calls == [{"ids": [INSTANCE_ID], "hibernate": True}]


def test_hibernate_rather_than_stop(env):
    """Same reason as the button: a stop would discard his R session."""
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    cw = FakeCloudWatch(quiet_window())

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    assert ec2.stop_calls[0]["hibernate"] is True


# --- the busy machine --------------------------------------------------

def test_busy_machine_is_left_alone(env):
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    cw = FakeCloudWatch(busy_window())

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    assert ec2.stop_calls == []


def test_one_busy_period_protects_the_whole_window(env):
    """the collaborator runs a model for ten minutes, then reads the output for
    an hour.

    Judging the window by its average would hibernate him during the reading.
    The rule is that any single period above the threshold means somebody is
    there, so the window has to be quiet throughout.
    """
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    cw = FakeCloudWatch(window_with_one_busy_period())

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    assert ec2.stop_calls == []


# --- the machine that has just woken up --------------------------------

def test_no_datapoints_means_do_not_hibernate(env):
    """This is the test that stops the link from being useless.

    In the minutes after a resume, CloudWatch has published no CPU metric yet,
    so the query comes back empty. Treating "no data" as "quiet" would
    hibernate the machine seconds after the collaborator woke it, and they
    would click the
    link again, and it would happen again.
    """
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    cw = FakeCloudWatch([])

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    assert ec2.stop_calls == []


def test_a_partly_filled_window_does_not_hibernate(env):
    """Twenty minutes of quiet is not two hours of quiet.

    Right after a resume the window fills up one datapoint at a time. Until
    there are enough of them to cover the full idle period, the evidence for
    "nobody is here" does not exist yet.
    """
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    cw = FakeCloudWatch(quiet_window(n=3))  # 3 of the 24 five-minute periods

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    assert ec2.stop_calls == []


# --- states where the question does not arise --------------------------

def test_already_stopped_machine_is_not_stopped_again(env):
    ec2 = FakeEC2(state="stopped")
    cw = FakeCloudWatch(quiet_window())

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    assert ec2.stop_calls == []


def test_a_stopped_machine_is_not_queried_for_metrics(env):
    """Asking CloudWatch about a machine that is off is a wasted call."""
    ec2 = FakeEC2(state="stopped")
    cw = FakeCloudWatch(quiet_window())

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    assert cw.calls == []


def test_pending_machine_is_left_alone(env):
    """Hibernating something mid-boot is how instances end up wedged."""
    ec2 = FakeEC2(state="pending")
    cw = FakeCloudWatch([])

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    assert ec2.stop_calls == []


# --- the window it actually asks about ---------------------------------

def test_metrics_are_requested_for_the_configured_window(env):
    """IDLE_MINUTES is 120 in the environment, so the query covers two hours.

    If the code asked for the last ten minutes instead, every test above would
    still pass while the deployed function hibernated the collaborator
    constantly.
    """
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    cw = FakeCloudWatch(quiet_window())

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    call = cw.calls[0]
    window = call["EndTime"] - call["StartTime"]
    assert window.total_seconds() == 120 * 60


def test_metrics_are_requested_for_this_instance_only(env):
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    cw = FakeCloudWatch(quiet_window())

    idle.handle({}, ec2=ec2, cloudwatch=cw)

    dimensions = cw.calls[0]["Dimensions"]
    assert dimensions == [{"Name": "InstanceId", "Value": INSTANCE_ID}]
