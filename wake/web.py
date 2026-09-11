"""What happens when the collaborator opens the link.

One page. It reports whether the workspace is running, starts it when it finds
it asleep, and hands over the RStudio address once the workspace can answer on
it. It also accepts a form submission that puts the workspace back to sleep.
"""

import base64
import hmac
import urllib.error
import urllib.parse
import urllib.request

from wake import config, page

# How long to wait for RStudio to answer before deciding it is not ready. Kept
# short because a visitor is sitting in front of this page while it runs.
PROBE_TIMEOUT_SECONDS = 3


def _authorised(params):
    """Check the secret in a way that takes the same time however wrong it is.

    A plain `==` stops as soon as two characters differ, so a wrong secret
    that starts correctly takes measurably longer to reject than one that is
    wrong from the first character. Someone timing the answers can recover the
    secret a character at a time. `hmac.compare_digest` always reads to the
    end.
    """
    return hmac.compare_digest(params.get("k", ""), config.secret())


def _client():
    # Imported inside this function rather than at the top of the file. The
    # tests always pass in a stand-in, so importing at the top would make them
    # need AWS credentials they have no use for.
    import boto3

    return boto3.client("ec2")


def _rstudio_answers(address, port):
    """Ask RStudio whether it is listening yet.

    A workspace reports itself running about twenty-five seconds before
    RStudio can serve anything, and a link offered during that gap takes the
    collaborator
    nowhere. Any reply at all counts, including the redirect RStudio sends to
    its own sign-in page; the question is only whether something is there.
    """
    url = f"http://{address}:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_SECONDS) as r:
            return r.status < 500
    except urllib.error.HTTPError:
        # An HTTP error is still an answer, so RStudio is up.
        return True
    except Exception:
        # Refused, timed out, DNS, reset: nothing is listening yet.
        return False


def _describe(ec2, instance_id):
    reservations = ec2.describe_instances(InstanceIds=[instance_id])
    instance = reservations["Reservations"][0]["Instances"][0]
    return instance["State"]["Name"], instance.get("PublicIpAddress")


def _fields(event, method):
    """Pull the submitted values out of wherever this kind of request puts
    them.

    Someone following a link carries values in the web address. A submitted
    form carries them in the body of the request instead, sometimes plain and
    sometimes base64-encoded. Reading only the web address is why the finish
    button once returned "not found" to every press.
    """
    if method != "POST":
        return event.get("queryStringParameters") or {}

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", "replace")
    return {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}


def handle(event, ec2=None, rstudio_answers=None):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    params = _fields(event, method)

    # The key check comes before anything else. A stranger provokes no AWS
    # call at all, so nothing is billed and nothing starts.
    if not _authorised(params):
        return page.not_found()

    ec2 = ec2 or _client()
    rstudio_answers = rstudio_answers or _rstudio_answers
    instance_id = config.instance_id()
    state, address = _describe(ec2, instance_id)

    # Only a form submission may stop the workspace. Browsers use two ways
    # of asking for a page: the ordinary one for following a link, and a
    # second one for submitting a form. Anything arriving the first way is
    # treated as an ordinary visit, whatever it asks for.
    if params.get("action") == "stop" and method == "POST":
        if state == "running":
            # Hibernating keeps what is in memory. A plain stop would
            # discard his R session along with anything unsaved in it.
            ec2.stop_instances(InstanceIds=[instance_id], Hibernate=True)
        # Pressing it twice, or pressing it on a workspace the timer has
        # already put to sleep, should say so rather than wake anything up.
        return page.asleep()

    if state == "stopped":
        ec2.start_instances(InstanceIds=[instance_id])
        return page.starting()

    if state == "running":
        # A workspace can report itself running for a few seconds before AWS
        # has given it a public address, and for a further half minute before
        # RStudio is listening on it. A link offered in either window goes
        # nowhere, and they would conclude the workspace is broken.
        if not address:
            return page.starting()
        port = config.rstudio_port()
        try:
            ready = rstudio_answers(address, port)
        except Exception:
            # The probe crosses the network, so it can fail in ways urlopen
            # does not catch. Any failure means "not yet", never an error page.
            ready = False
        if not ready:
            return page.starting_r()
        return page.ready(address, port, config.rstudio_user(), config.secret())

    # The workspace is part way between running and stopped. Wait for it to
    # settle rather than act on it.
    return page.in_transition(state)


def lambda_handler(event, context):
    return handle(event)
