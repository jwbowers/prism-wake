# prism-wake

[![tests](https://github.com/jwbowers/prism-wake/actions/workflows/ci.yml/badge.svg)](https://github.com/jwbowers/prism-wake/actions/workflows/ci.yml)

One web link that starts a hibernated research workspace on AWS, and a timer
that puts it back to sleep when nobody is using it.

It exists for a particular situation: you run an EC2 machine with RStudio
Server on it, a collaborator needs to use it, and that collaborator has no AWS
account, has installed nothing, and should not have to email you every morning
to ask you to switch the machine on. They get one web address. Everything else
happens on Amazon's side.

## What your collaborator sees

They save one link in their browser. Opening it produces, in order:

```
Starting the workspace        the machine is booting
Almost ready                  the machine is up, RStudio is still starting
The workspace is ready        with a link to RStudio and their username
```

Each page refreshes itself every fifteen seconds and says so, so there is
nothing to click and nothing to reload. When the link to RStudio finally
appears, it works: the page has already checked that RStudio is answering. A
"Finished for today" button on the last page puts the machine back to sleep
without losing their R session.

They never see AWS, never install anything, and never need an account anywhere.

## What you need before you start

Four things about the workspace itself, and one about you.

The EC2 instance must have hibernation turned on. This is chosen when the
instance is launched and cannot be added afterwards, so check it before
anything else:

```bash
aws ec2 describe-instances --instance-ids i-YOURINSTANCE --region YOUR-REGION \
  --query 'Reservations[].Instances[].HibernationOptions.Configured'
```

That must print `true`. Hibernating writes the contents of memory to disk and
restores it on the next start, which is what lets an R session survive being
switched off. A plain stop would discard it.

RStudio Server must accept the account your collaborator will use. Look in
`/etc/rstudio/rserver.conf` on the machine. If it contains a line like
`auth-required-user-group=sudo`, then only members of that group can sign in,
and the collaborator's Linux account has to be one of them.

The security group must allow inbound TCP on RStudio's port, which is 8787
unless you changed it, from wherever your collaborator works.

The collaborator needs a Linux account on the machine with a password they
know. If you are setting one, the plainest route is to connect to the machine
and run `sudo passwd theirusername`, which records the password nowhere.

And you need the AWS command line tool, signed in to an account that can
create IAM roles, Lambda functions, and API Gateways.

## Setting up your own config.sh

Everything specific to you goes in one file that is never committed. Start
from the example:

```bash
git clone https://github.com/jwbowers/prism-wake
cd prism-wake
cp config.example.sh config.sh
```

Then open `config.sh` and fill in five values. The rest have working defaults.

`AWS_PROFILE` is the named profile the AWS command line tool should use. If you
have only ever used one set of credentials this is `default`. List what you
have with `aws configure list-profiles`.

`REGION` is the AWS region the workspace runs in, such as `us-east-2`.

`ACCOUNT` is your twelve-digit AWS account number:

```bash
aws sts get-caller-identity --query Account --output text
```

`INSTANCE_ID` identifies the machine this link wakes. If you know what the
machine is called, find its identifier by that name:

```bash
aws ec2 describe-instances --region YOUR-REGION \
  --filters Name=tag:Name,Values=YOUR-WORKSPACE-NAME \
  --query 'Reservations[].Instances[].InstanceId' --output text
```

`RSTUDIO_USER` is the Linux account your collaborator signs in to RStudio with.
The page shows it to them so they do not have to remember it.

Two more control when the timer puts the machine to sleep. `IDLE_MINUTES`
defaults to 120 and `IDLE_CPU_PERCENT` to 5, which together mean: sleep only
when every five-minute processor reading in the last two hours was below five
percent. Lengthen the window if your collaborator spends long stretches reading
output rather than computing.

`config.sh` is listed in `.gitignore`, so your account number and your
collaborator's login stay on your own computer.

## Deploying

```bash
./deploy.sh
```

It creates the permissions, the two programs, the public web address, and the
timer, and then prints the link. Send that link to your collaborator and
nothing else. Run it once, when none of those things exist yet; running it a
second time stops on the first thing it tries to create, because that thing is
already there.

To change the code afterwards:

```bash
make package
aws lambda update-function-code --function-name prism-wake-web \
  --region YOUR-REGION --zip-file fileb://dist/prism-wake.zip
```

## What AWS charges

The link itself is close to free. Lambda's free allowance covers a few
thousand wake-ups a month, and API Gateway charges about one dollar per million
requests.

The saving is on the workspace. AWS charges about $4.84 a day for an
`m7i.xlarge` left running, which is $145 a month. The same machine woken for six hours a day, five days
a week, is about 130 hours a month, which is $26. Disk charges continue either
way, at about $6.40 a month for an 80 GB volume, because a sleeping machine
still keeps its disk.

## The pieces, and what each one is

AWS Lambda runs a small program on Amazon's computers without renting a machine
to hold it. You upload the code once, and Amazon runs it whenever something
asks it to. Two such programs share one upload here:

- `wake.web.lambda_handler` answers the link, through an API Gateway, which is
  the Amazon service that takes web requests from the world and hands them to a
  program of yours.
- `wake.idle.lambda_handler` runs every fifteen minutes, started by an Amazon
  timer called an EventBridge rule. It reads how busy the workspace's processor
  has been from CloudWatch, where AWS records measurements about a running
  machine, and puts the workspace to sleep if it has been quiet long enough.

Both run under one IAM role, which is the set of permissions AWS allows them.
Theirs lets them start and stop this one workspace, read whether it is running,
and read its processor measurements, and nothing else.

## Decisions and their reasons

### Sleep by hibernating, never by stopping

Both the button and the timer put the workspace to sleep in the way that keeps
what is in memory, which AWS calls hibernating and which the code asks for as
`StopInstances` with `Hibernate=True`. A plain stop discards that memory along
with anything unsaved in it.

### No reserved address

The workspace comes back on a different public address after every
hibernation. Reserving a fixed one, which AWS calls an Elastic IP, would be
$3.60 a month. Instead the page reads the workspace's current address every
time someone opens it and builds the RStudio link fresh. The collaborator's one
link is the wake page, never the RStudio address itself. In testing, one
workspace had three different addresses in an afternoon and the page found each
one.

### The link is the credential

The web address is open to anyone, because requiring a login is what the link
exists to avoid. A secret in the address is what keeps strangers out, so the
link should travel the way a password would. A wrong secret returns the same
bytes as a missing page, so someone guessing addresses cannot tell they have
found something real. The secret is checked before any call to AWS, so a
stranger can neither spend money nor start the workspace.

`deploy.sh` generates the secret when it runs and prints it once. It is stored
only in Amazon's copy of the program and is in no file here.

### Stopping needs a form submission, not a link

Mail programs and browsers fetch links on their own to preview them. If
stopping were reachable by an ordinary link, a link checker running over your
mail could put the workspace to sleep while your collaborator was working in
it.

### The link to RStudio waits until RStudio answers

A workspace reports itself running about twenty-five seconds before RStudio is
listening. Offering the link during that gap sends your collaborator to a dead
address, and someone in another time zone who cannot ask you what went wrong
will conclude the workspace is broken. So the page asks RStudio whether it is
up before offering the link, and shows a different wait page until it is.

### Two hours below 5%, and every five-minute period must be quiet

AWS records one processor-usage figure for a running machine every five
minutes, so five minutes is the shortest stretch CloudWatch can answer about.
Across the last two hours, the timer treats the workspace as idle only when
every one of those figures is below 5%. Judging the two hours on their average
instead would call ten minutes of model fitting followed by an hour of reading
the output quiet, while somebody is plainly still there.

The timer never treats a missing measurement as quiet. In the first minutes
after a workspace wakes, AWS has recorded nothing yet, and reading that as idle
would put the workspace back to sleep seconds after your collaborator woke it.

## Running the tests

```bash
make test
```

31 tests. None of them needs AWS credentials or a network connection, and the
suite fails loudly if a test tries to reach either. The same tests run on every
push and every pull request, along with a check that `deploy.sh` parses, passes
shellcheck, and refuses to touch AWS when no `config.sh` is present. Both AWS connections are
handed in as arguments, and the stand-ins in `tests/conftest.py` record every
call, so a test can check the calls that were made and, more often, the calls
that were not.

## Things that caught me out

Lambda offers its own public web addresses, called function URLs, and they are
simpler than an API Gateway. In the account this was built for, a function URL
configured exactly as AWS documents refused every request with `403
AccessDeniedException`, and no command-line call I could find explained why.
The API Gateway worked immediately. If you prefer the simpler route, try it,
but this is why the script does not.

A machine that reports `running` is not a machine that can serve a web page.
There were about twenty-five seconds between the two.

Prism's channel for running commands on the machine, AWS Systems Manager, takes
several minutes to come back after a hibernation. Nothing here depends on it,
but do not read its absence as a broken workspace.

## Relationship to Prism

The workspace this was written for was created by
[Prism](https://github.com/scttfrdmn/prism), but nothing here depends on Prism.
It works with any EC2 instance that has hibernation turned on. Prism's own
scheduling runs inside a program on your own laptop, so it cannot wake a
workspace while the laptop is asleep, and a collaborator cannot reach it at
all. That is what this adds.

## Removing it

```bash
aws events remove-targets --rule prism-wake-idle-check --ids 1 --region YOUR-REGION
aws events delete-rule --name prism-wake-idle-check --region YOUR-REGION
aws apigatewayv2 delete-api --api-id YOUR-API-ID --region YOUR-REGION
aws lambda delete-function --function-name prism-wake-web --region YOUR-REGION
aws lambda delete-function --function-name prism-wake-idle --region YOUR-REGION
aws iam delete-role-policy --role-name prism-wake-role --policy-name prism-wake
aws iam delete-role --role-name prism-wake-role
```

## Licence

Apache 2.0, the same licence Prism uses, so Prism could take this code
directly without a compatibility question. See `LICENSE`.
