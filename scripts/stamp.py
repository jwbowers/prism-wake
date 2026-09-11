"""Record which commit a deployed program was built from.

AWS replaces the entire set of environment variables when you change one, so
adding a stamp means reading what is there, merging, and sending it all back.
Getting that wrong would lose the wake secret, which is generated once when the
programs are created and kept nowhere else, and the link already in a
collaborator's browser would stop working with no copy to restore.

Used by the Makefile:

    aws lambda get-function-configuration ... --query Environment.Variables \
      | python3 scripts/stamp.py "$(make --no-print-directory version)"
"""

import json
import sys

VARIABLE = "GIT_COMMIT"


def merge(existing, commit):
    """Return the environment with the commit recorded, everything else kept."""
    if commit is None or not str(commit).strip():
        raise ValueError(
            "refusing to stamp an empty commit: a stamp that says nothing is "
            "worse than no stamp, because a reader believes it answered them"
        )
    merged = dict(existing or {})
    merged[VARIABLE] = str(commit).strip()
    return merged


def main(argv):
    if len(argv) != 2:
        print(f"usage: {argv[0]} <commit>   (environment JSON on stdin)",
              file=sys.stderr)
        return 2
    raw = sys.stdin.read().strip()
    # `aws ... --query Environment.Variables` prints "null" for a program that
    # has no variables set, which json.loads turns into None rather than {}.
    existing = json.loads(raw) if raw else {}
    print(json.dumps(merge(existing or {}, argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
