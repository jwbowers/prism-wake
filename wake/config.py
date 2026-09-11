"""Settings, read from the environment on every call.

Reading at call time rather than once at the top of the file is deliberate.
Amazon reuses the same running copy of the program for a stretch of requests,
so a setting read once at the top would keep its old value after you changed
it, until Amazon happened to start a fresh copy. Reading per call also lets the
tests set the environment after importing this file.
"""

import os


def instance_id():
    return os.environ["INSTANCE_ID"]


def secret():
    return os.environ["WAKE_SECRET"]


def rstudio_port():
    return os.environ.get("RSTUDIO_PORT", "8787")


def rstudio_user():
    return os.environ.get("RSTUDIO_USER", "")


def idle_cpu_percent():
    return float(os.environ.get("IDLE_CPU_PERCENT", "5"))


def idle_minutes():
    return int(os.environ.get("IDLE_MINUTES", "120"))
