"""Shared fakes for the wake-link tests.

The code under test talks to exactly two parts of AWS: the one that runs and
stops machines, and CloudWatch, which records how busy a running machine has
been. Both are replaced here with small hand-written stand-ins rather than a
library, so that each test can check the calls that were made and, just as
much, the calls that were not. Several of the claims these tests encode are
claims about restraint. A stranger must provoke no AWS call at all, and a page
refresh must not start the workspace twice.
"""

import base64
import urllib.parse

import pytest

from wake import web

INSTANCE_ID = "i-0123456789abcdef0"
SECRET = "test-secret-value"


class FakeEC2:
    """Stands in for the AWS connection that starts and stops machines.

    It records every call so a test can check what was asked of AWS.
    """

    def __init__(self, state="stopped", public_ip=None):
        self.state = state
        self.public_ip = public_ip
        self.describe_calls = []
        self.start_calls = []
        self.stop_calls = []

    def describe_instances(self, InstanceIds):
        self.describe_calls.append(InstanceIds)
        instance = {"State": {"Name": self.state}}
        # A sleeping workspace has no public address at all. Reproducing that
        # absence matters, because the page must not build a link out of it.
        if self.public_ip is not None:
            instance["PublicIpAddress"] = self.public_ip
        return {"Reservations": [{"Instances": [instance]}]}

    def start_instances(self, InstanceIds):
        self.start_calls.append(InstanceIds)
        self.state = "pending"
        return {}

    def stop_instances(self, InstanceIds, Hibernate=False):
        self.stop_calls.append({"ids": InstanceIds, "hibernate": Hibernate})
        self.state = "stopping"
        return {}


class FakeCloudWatch:
    """Stands in for the AWS connection that reports processor usage.

    `datapoints` is the list of five-minute averages AWS would return. An
    empty list is the important case: it is what AWS returns in the first
    minutes after a workspace wakes, before it has recorded anything.
    """

    def __init__(self, datapoints=None):
        self.datapoints = [] if datapoints is None else datapoints
        self.calls = []

    def get_metric_statistics(self, **kwargs):
        self.calls.append(kwargs)
        return {"Datapoints": list(self.datapoints)}


# EC2 basic monitoring publishes CPU every five minutes, so a two-hour window
# is twenty-four datapoints. Tests that mean "the machine was quiet for the
# whole window" have to supply that many, or they pass for the wrong reason.
PERIOD_SECONDS = 300
FULL_WINDOW = 24


def quiet_window(n=FULL_WINDOW):
    """A full window of CPU averages that nobody could be working through."""
    return [{"Average": 0.3} for _ in range(n)]


def busy_window(n=FULL_WINDOW):
    return [{"Average": 45.0} for _ in range(n)]


class ReachedTheNetwork(BaseException):
    """Raised when a test lets the real RStudio probe run.

    Deliberately not an Exception, because the code under test catches every
    Exception around the probe and would swallow this, turning a loud failure
    into a confusing one.
    """


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test may touch the network.

    The suite has to run with no AWS credentials and no internet, and it has
    to stay fast. Any test that needs a workspace reporting itself running
    must say what the probe finds, by passing `rstudio_answers=`.
    """
    def forbidden(*args):
        raise ReachedTheNetwork(
            "this test let the real RStudio probe run; "
            "pass rstudio_answers=yes or rstudio_answers=no instead"
        )

    monkeypatch.setattr(web, "_rstudio_answers", forbidden)


@pytest.fixture
def env(monkeypatch):
    """The environment the deployed functions will actually run under."""
    monkeypatch.setenv("INSTANCE_ID", INSTANCE_ID)
    monkeypatch.setenv("WAKE_SECRET", SECRET)
    monkeypatch.setenv("RSTUDIO_PORT", "8787")
    monkeypatch.setenv("RSTUDIO_USER", "collaborator")
    monkeypatch.setenv("IDLE_CPU_PERCENT", "5")
    monkeypatch.setenv("IDLE_MINUTES", "120")


def get(params=None):
    """Build a request in the shape Amazon hands to the program.

    Someone following a link puts everything in the web address itself, which
    arrives as `queryStringParameters`.
    """
    return {
        "queryStringParameters": params,
        "requestContext": {"http": {"method": "GET"}},
        "headers": {},
        "body": None,
        "isBase64Encoded": False,
    }


def post(params=None, base64_body=False):
    """Build a submitted form, which is a different shape entirely.

    A submitted form does not put its fields in the web address. It sends
    them in the body of the request, and the program has to read them from
    there. Modelling this wrongly is how the finish button reached AWS doing
    nothing at all while every test here passed.

    Amazon sometimes hands the body over base64-encoded, so both forms are
    available.
    """
    body = urllib.parse.urlencode(params or {})
    if base64_body:
        body = base64.b64encode(body.encode()).decode()
    return {
        "queryStringParameters": None,
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"content-type": "application/x-www-form-urlencoded"},
        "body": body,
        "isBase64Encoded": base64_body,
    }
