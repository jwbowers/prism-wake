# bristol-wake

One web link that starts a hibernated research workspace for a
collaborator who has no AWS account and has installed nothing, plus a timer
that puts the workspace back to sleep once it has been quiet for two hours.

## What the collaborator sees

He gets one link and saves it in his browser. Opening it:

1. starts the workspace if it is asleep, and shows a page that refreshes itself
   while the workspace boots;
2. shows an "Open RStudio" link once the workspace can answer on it;
3. offers a "Finished for today" button that puts the workspace back to sleep.

He never sees AWS and never installs anything. The code runs on Amazon's
computers.

## The pieces, and what each one is

AWS Lambda runs a small program on Amazon's computers without renting a machine
to hold it. You upload the code once, and Amazon runs it whenever something
asks it to. Two such programs share one upload here:

- `wake.web.lambda_handler` answers the link. Amazon gives a Lambda program its
  own web address, called a function URL, so visiting that address runs the
  code. That address, with a secret attached, is the link the collaborator
  gets.
- `wake.idle.lambda_handler` runs every fifteen minutes, started by an Amazon
  timer called an EventBridge rule. It reads how busy the workspace's processor
  has been from CloudWatch, where AWS records measurements about a running
  machine, and puts the workspace to sleep if it has been quiet long enough.

Both programs run under one IAM role, which is the set of permissions AWS
allows them. Theirs lets them start and stop this one workspace, read whether
it is running, and read its processor measurements, and nothing else.

## Decisions and their reasons

### Sleep by hibernating, never by stopping

Both the button and the timer put the workspace to sleep in the way that keeps
what is in memory, which AWS calls hibernating and which the code asks for as
`StopInstances` with `Hibernate=True`. Hibernating writes the contents of
memory to disk and restores it on the next start, so a running R session
survives. A plain stop discards that memory along with anything unsaved in it.

### No reserved address

The workspace comes back on a different public address after every
hibernation. Reserving a fixed one, which AWS calls an Elastic IP, would be
$3.60 a month. Instead the page reads the workspace's current address every
time someone opens it and builds the RStudio link fresh. The collaborator's one
link is the wake page, never the RStudio address itself.

### The link is the credential

The function URL is open to anyone, because requiring a login is what the link
exists to avoid. A secret in the web address is what keeps strangers out, so
the link should travel the way a password would. A wrong secret returns the
same bytes as a missing page, so someone guessing addresses cannot tell they
have found something real. The secret is checked before any call to AWS, so a
stranger can neither spend money nor start the workspace.

### Stopping needs a form submission, not a link

Mail programs and browsers fetch links on their own to preview them. If
stopping were reachable by an ordinary link, a link checker running over your
mail could put the workspace to sleep while the collaborator was working in it.

### Two hours below 5%, and every five-minute period must be quiet

AWS records one processor-usage figure for a running machine every five
minutes, so five minutes is the shortest stretch CloudWatch can answer about.
Across the last two hours, we treat the workspace as idle only when every one
of those five-minute figures is below 5%. Judging the two hours on their
average instead would call ten minutes of model fitting followed by an hour of
reading the output quiet, while somebody is plainly still there.

The timer never treats a missing measurement as quiet. In the first minutes
after a workspace wakes, AWS has recorded nothing yet, and reading that as idle
would put the workspace back to sleep seconds after the collaborator woke it.

## Running the tests

    make test

The suite has 25 tests, and none of them needs AWS credentials. Both AWS
connections are handed in as arguments, and the stand-ins in
`tests/conftest.py` record every call, so a test can check the calls that were
made and, more often, the calls that were not.

## Deploying

Your own account number, region, machine, and collaborator's login go in a file
that is never committed:

    cp config.example.sh config.sh
    $EDITOR config.sh
    ./deploy.sh

Creates the role, both programs, the web address, and the timer, then prints
the link to send the collaborator. You need it only once. To change the code
afterwards, use `make package` and then `aws lambda update-function-code`.

## Rebuilding this environment elsewhere

`uv` is a tool that installs Python itself along with the packages a project
needs, and records exactly which versions it installed. `pyproject.toml` names
what this project asks for, and `uv.lock` records the exact version of every
one of those packages and of the packages they in turn need, each with a
checksum. `.python-version` records the exact Python version, 3.13, chosen to
match the one AWS Lambda will run the code on. Recording exact versions this
way is what lets someone rebuild an identical environment years later, rather
than getting whatever happens to be current.
