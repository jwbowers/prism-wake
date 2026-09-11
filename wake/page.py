"""The HTML the visitor sees.

Kept apart from the request handling so that the rules about what may appear
on the page (never an RStudio link before the machine can answer, never an
address that does not exist) are readable in one place.
"""

REFRESH_SECONDS = 15

_STYLE = (
    "font-family:system-ui,-apple-system,sans-serif;max-width:32em;"
    "margin:4em auto;padding:0 1.5em;line-height:1.5"
)


def _render(title, body, refresh=None):
    head = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": (
            "<!doctype html><html lang=en><head><meta charset=utf-8>"
            '<meta name=viewport content="width=device-width,initial-scale=1">'
            f"{head}<title>{title}</title></head>"
            f'<body style="{_STYLE}">{body}</body></html>'
        ),
    }


# The same reassurance on every waiting page. Someone looking at a page whose
# words do not change assumes it has hung, and the reasonable thing to do then
# is click again, so each page says plainly that it is working and that
# clicking is not needed.
_WAITING = (
    f"<p>This page refreshes itself every {REFRESH_SECONDS} seconds. You do "
    "not need to click anything or reload it. Just leave it open.</p>"
)


def starting():
    """Shown while the workspace boots, and while it has no address yet."""
    return _render(
        "Starting the workspace",
        "<h2>Starting the workspace</h2>"
        "<p>Waking it up usually takes a minute or two.</p>"
        f"{_WAITING}",
        refresh=REFRESH_SECONDS,
    )


def starting_r():
    """Shown once the workspace is up but RStudio is not yet listening.

    Deliberately different wording from `starting`, so that someone watching
    can see the wait move forward rather than stare at one unchanging page.
    """
    return _render(
        "Almost ready",
        "<h2>Almost ready</h2>"
        "<p>The workspace is running and RStudio is still starting up. This "
        "is the last step and it takes a few more seconds.</p>"
        f"{_WAITING}",
        refresh=REFRESH_SECONDS,
    )


def in_transition(state):
    return _render(
        "Workspace is busy",
        f"<h2>The workspace is {state}</h2>"
        f"{_WAITING}",
        refresh=REFRESH_SECONDS,
    )


def ready(address, port, user, secret_value):
    """Shown once RStudio can answer on the address.

    The finish button is a form rather than a link because mail programs and
    browsers fetch links on their own to preview them. One of them fetching a
    stop link would put the workspace to sleep while the collaborator was
    working in it.
    """
    url = f"http://{address}:{port}"
    sign_in = f"<p>Sign in as <code>{user}</code>.</p>" if user else ""
    return _render(
        "Workspace is ready",
        "<h2>The workspace is ready</h2>"
        f'<p><a href="{url}">Open RStudio</a></p>'
        f"{sign_in}"
        '<form method="post" style="margin-top:3em">'
        f'<input type="hidden" name="k" value="{secret_value}">'
        '<input type="hidden" name="action" value="stop">'
        '<button type="submit">Finished for today</button>'
        "</form>"
        "<p><small>Finishing saves your session and puts the machine to "
        "sleep. Your work is still here when you come back.</small></p>",
    )


def asleep():
    """Shown when someone finishes on a workspace that is already asleep."""
    return _render(
        "Workspace is asleep",
        "<h2>The workspace is asleep</h2>"
        "<p>Nothing to do. Open this page again when you want to work.</p>",
    )


def not_found():
    """The answer to a wrong key and to a wrong address alike.

    Returning the same bytes for both means someone guessing addresses cannot
    tell that they have found a real endpoint.
    """
    return {"statusCode": 404,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "body": "<!doctype html><html><body>Not found</body></html>"}
