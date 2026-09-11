"""What a visitor's request does.

The substantive claim this module defends: the collaborator, who has no AWS
account and has
installed nothing, can open one link and reach a running RStudio; and a
stranger who guesses the address learns nothing and spends none of the owner's
money.
"""

import pytest

from conftest import FakeEC2, INSTANCE_ID, SECRET, get, post


def yes(*_):
    """Stand in for a probe that finds RStudio answering."""
    return True


def no(*_):
    """Stand in for a probe that finds nothing listening yet."""
    return False
from wake import web


# --- the stranger ------------------------------------------------------

def test_wrong_secret_makes_no_aws_call(env):
    """A wrong key must not even reach EC2.

    This is the claim that protects the bill. If the handler described the
    instance before checking the key, every visit by a stranger would be an
    API call billed to the owner, and a flood of them could start the machine.
    """
    ec2 = FakeEC2(state="stopped")
    response = web.handle(get({"k": "wrong"}), ec2=ec2)

    assert response["statusCode"] == 404
    assert ec2.describe_calls == []
    assert ec2.start_calls == []


def test_missing_secret_makes_no_aws_call(env):
    ec2 = FakeEC2(state="stopped")
    response = web.handle(get(None), ec2=ec2)

    assert response["statusCode"] == 404
    assert ec2.describe_calls == []
    assert ec2.start_calls == []


def test_wrong_secret_is_indistinguishable_from_a_missing_page(env):
    """A prober must not learn that the endpoint exists.

    If a wrong key produced "forbidden" while a bad path produced "not found",
    someone scanning URLs would know they had found something real and worth
    attacking. Both answers are byte-identical instead.
    """
    ec2 = FakeEC2()
    wrong_key = web.handle(get({"k": "wrong"}), ec2=ec2)
    no_key = web.handle(get({}), ec2=ec2)

    assert wrong_key == no_key


# --- waking the machine ------------------------------------------------

def test_stopped_instance_is_started_exactly_once(env):
    """The whole point of the link, stated as a test."""
    ec2 = FakeEC2(state="stopped")
    response = web.handle(get({"k": SECRET}), ec2=ec2)

    assert ec2.start_calls == [[INSTANCE_ID]]
    assert response["statusCode"] == 200
    assert "Starting" in response["body"]


def test_refreshing_while_pending_does_not_start_it_again(env):
    """The page refreshes itself every few seconds while the machine boots.

    Each refresh is a fresh request. If the handler started the instance on
    every request, a two-minute boot would issue eight StartInstances calls.
    EC2 tolerates that, but the handler should not rely on EC2's tolerance.
    """
    ec2 = FakeEC2(state="pending")
    web.handle(get({"k": SECRET}), ec2=ec2)
    web.handle(get({"k": SECRET}), ec2=ec2)

    assert ec2.start_calls == []


def test_running_instance_is_not_started_again(env):
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    web.handle(get({"k": SECRET}), ec2=ec2, rstudio_answers=yes)

    assert ec2.start_calls == []


# --- handing over the RStudio link -------------------------------------

def test_rstudio_link_appears_only_when_the_machine_can_answer(env):
    """A link shown too early sends the collaborator to a dead port and they
    give up.

    RStudio is reachable only once the instance is running, so the link must
    be absent in every other state.
    """
    for state in ("stopped", "pending", "stopping"):
        ec2 = FakeEC2(state=state)
        body = web.handle(get({"k": SECRET}), ec2=ec2)["body"]
        assert "8787" not in body, f"link leaked while {state}"


def test_running_instance_hands_over_a_usable_link(env):
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    body = web.handle(get({"k": SECRET}), ec2=ec2, rstudio_answers=yes)["body"]

    assert "http://203.0.113.7:8787" in body
    assert "collaborator" in body


def test_no_link_until_rstudio_itself_answers(env):
    """Running is not the same as ready, by about twenty-five seconds.

    Watching a real wake on 2026-09-11, the workspace reported itself running
    while RStudio was still starting, and a visitor quick enough to click the
    link in that window reached nothing. The collaborator is in another time
    zone and cannot ask
    anyone what went wrong, so they would conclude the workspace is broken.
    """
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    body = web.handle(get({"k": SECRET}), ec2=ec2, rstudio_answers=no)["body"]

    assert "8787" not in body


def test_the_wait_page_tells_him_not_to_click(env):
    """He is waiting at a page that looks stuck, so it has to say it is not.

    Without this, the reasonable thing for him to do is click again, and again.
    """
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    body = web.handle(get({"k": SECRET}), ec2=ec2, rstudio_answers=no)["body"]

    assert "do not need to" in body.lower()
    assert "refresh" in body.lower()


def test_the_wait_page_distinguishes_booting_from_starting_R(env):
    """Two different waits, so he can see that something is happening.

    A page whose words never change reads as a page that has hung.
    """
    booting = web.handle(get({"k": SECRET}),
                         ec2=FakeEC2(state="stopped"), rstudio_answers=no)["body"]
    starting_r = web.handle(get({"k": SECRET}),
                            ec2=FakeEC2(state="running", public_ip="203.0.113.7"),
                            rstudio_answers=no)["body"]

    assert booting != starting_r


def test_rstudio_is_not_probed_when_the_workspace_is_asleep(env):
    """Nothing is listening on an address that does not exist yet."""
    asked = []
    ec2 = FakeEC2(state="stopped")
    web.handle(get({"k": SECRET}), ec2=ec2,
               rstudio_answers=lambda *a: asked.append(a) or False)

    assert asked == []


def test_a_probe_that_raises_is_treated_as_not_answering(env):
    """The probe reaches out over the network, so it can fail in any way.

    An exception escaping here would show the collaborator a server error
    instead of a
    wait page, which is worse than simply waiting.
    """
    def explodes(*_):
        raise OSError("connection reset")

    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    response = web.handle(get({"k": SECRET}), ec2=ec2, rstudio_answers=explodes)

    assert response["statusCode"] == 200
    assert "8787" not in response["body"]


def test_link_uses_the_address_found_on_this_request(env):
    """This is the decision to skip the Elastic IP, written as a test.

    Without a reserved address the machine comes back on a different one after
    every hibernate. The page is correct only if it reads the address afresh
    on each visit rather than remembering one.
    """
    first = web.handle(get({"k": SECRET}),
                       ec2=FakeEC2(state="running", public_ip="203.0.113.7"),
                       rstudio_answers=yes)
    second = web.handle(get({"k": SECRET}),
                        ec2=FakeEC2(state="running", public_ip="198.51.100.22"),
                        rstudio_answers=yes)

    assert "203.0.113.7:8787" in first["body"]
    assert "198.51.100.22:8787" in second["body"]


def test_running_but_addressless_instance_does_not_produce_a_broken_link(env):
    """There is a window where the state is running and no address exists yet.

    Building "http://None:8787" would be worse than saying "still starting",
    because the collaborator would click it, fail, and conclude the workspace
    is broken.
    """
    ec2 = FakeEC2(state="running", public_ip=None)
    body = web.handle(get({"k": SECRET}), ec2=ec2)["body"]

    assert "None" not in body
    assert "8787" not in body


# --- finishing for the day ---------------------------------------------

def test_finished_button_hibernates_rather_than_stops(env):
    """Hibernating is what preserves the collaborator's R session.

    A plain stop would discard the memory of a running R process, losing
    whatever he had not written to disk. The distinction is the whole reason
    the button is safe to offer him.
    """
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    web.handle(post({"k": SECRET, "action": "stop"}), ec2=ec2)

    assert ec2.stop_calls == [{"ids": [INSTANCE_ID], "hibernate": True}]


def test_finished_button_ignores_a_GET(env):
    """Browsers and mail clients fetch GET links on their own.

    Some mail clients and browser prefetchers follow links before a human
    clicks them. If stopping were reachable by GET, a link checker scanning
    the owner's email could hibernate the machine out from under the
    collaborator mid-session.
    """
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    web.handle(get({"k": SECRET, "action": "stop"}), ec2=ec2, rstudio_answers=yes)

    assert ec2.stop_calls == []


def test_finished_button_needs_the_secret_too(env):
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    response = web.handle(post({"k": "wrong", "action": "stop"}), ec2=ec2)

    assert response["statusCode"] == 404
    assert ec2.stop_calls == []


def test_finished_button_works_when_the_body_arrives_base64_encoded(env):
    """Amazon sometimes hands the form over base64-encoded rather than plain.

    Which one arrives depends on how the request was made and is not something
    the collaborator controls, so the program has to read both. Reading only
    the plain form would leave the button working for some visitors and
    silently
    doing nothing for others.
    """
    ec2 = FakeEC2(state="running", public_ip="203.0.113.7")
    web.handle(post({"k": SECRET, "action": "stop"}, base64_body=True), ec2=ec2)

    assert ec2.stop_calls == [{"ids": [INSTANCE_ID], "hibernate": True}]


def test_finished_button_on_an_already_stopped_machine_is_harmless(env):
    """the collaborator may press it twice, or press it after an idle
    hibernate."""
    ec2 = FakeEC2(state="stopped")
    response = web.handle(post({"k": SECRET, "action": "stop"}), ec2=ec2)

    assert ec2.stop_calls == []
    assert response["statusCode"] == 200
