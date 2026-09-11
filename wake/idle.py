"""What the timer does.

Every fifteen minutes this asks CloudWatch how busy the workspace has been,
and puts it to sleep once it has been quiet for the whole of the last two
hours.

The two mistakes this can make are not equally bad. Sleeping late wastes a few
dollars. Sleeping early interrupts someone in another country who cannot ask
for it to be undone, so every rule below errs toward leaving the machine up.
"""

from datetime import datetime, timedelta, timezone

from wake import config

# AWS records a processor-usage figure for a running machine once every five
# minutes, so that is the shortest stretch CloudWatch can answer about.
PERIOD_SECONDS = 300

METRIC_NAMESPACE = "AWS/EC2"
METRIC_NAME = "CPUUtilization"


def _ec2():
    # Imported inside this function rather than at the top of the file. The
    # tests always pass in stand-ins, so importing at the top would make them
    # need AWS credentials they have no use for.
    import boto3

    return boto3.client("ec2")


def _cloudwatch():
    import boto3

    return boto3.client("cloudwatch")


def _state(ec2, instance_id):
    reservations = ec2.describe_instances(InstanceIds=[instance_id])
    return reservations["Reservations"][0]["Instances"][0]["State"]["Name"]


def _cpu_averages(cloudwatch, instance_id, minutes):
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    result = cloudwatch.get_metric_statistics(
        Namespace=METRIC_NAMESPACE,
        MetricName=METRIC_NAME,
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start,
        EndTime=end,
        Period=PERIOD_SECONDS,
        Statistics=["Average"],
    )
    return [point["Average"] for point in result["Datapoints"]]


def handle(event, ec2=None, cloudwatch=None, periods_required=None):
    if ec2 is None:
        ec2 = _ec2()
    if cloudwatch is None:
        cloudwatch = _cloudwatch()

    instance_id = config.instance_id()
    state = _state(ec2, instance_id)

    # A workspace that is not running is either already asleep or part way
    # between the two. Putting one to sleep while it is still booting can
    # leave it in a state that only a forced stop in the AWS console clears.
    # Asking CloudWatch about a workspace that is off returns nothing anyway.
    if state != "running":
        return

    minutes = config.idle_minutes()
    if periods_required is None:
        periods_required = (minutes * 60) // PERIOD_SECONDS

    averages = _cpu_averages(cloudwatch, instance_id, minutes)

    # An empty or short answer is not evidence of quiet. In the first minutes
    # after a workspace wakes, AWS has recorded nothing yet, and reading that
    # as "nobody is here" would put the workspace back to sleep seconds after
    # the collaborator woke it.
    if len(averages) < periods_required:
        return

    # Every five-minute figure must be quiet, rather than the two hours
    # averaging out quiet. Ten minutes of model fitting followed by an hour of
    # reading the output averages to nothing, and they are plainly still
    # working.
    if max(averages) >= config.idle_cpu_percent():
        return

    ec2.stop_instances(InstanceIds=[instance_id], Hibernate=True)


def lambda_handler(event, context):
    return handle(event)
