# uv manages the interpreter and the locked dependencies, so every target
# below runs against the same environment on any machine.

# What gets stamped onto the deployed programs. `--always` falls back to the
# short commit when there is no tag, and `--dirty` appends a marker when the
# working tree has uncommitted changes, so a stamp can never claim a deployment
# came from a commit that does not contain it.
GIT_STAMP := $(shell git describe --always --dirty --abbrev=8 2>/dev/null || echo unknown)

.PHONY: test test-watch package version deploy clean

test:
	uv run pytest -q

# Watch mode is handy while filling in the implementation.
test-watch:
	uv run pytest -q --looponfail

version:
	@echo $(GIT_STAMP)

# Compiled bytecode from a different interpreter is excluded: shipping stale
# .pyc files to Lambda is a reliable way to debug code that is not running.
package:
	rm -rf build dist && mkdir -p build dist
	cp -r wake build/
	find build -name __pycache__ -type d -exec rm -rf {} +
	cd build && zip -qr ../dist/prism-wake.zip wake
	@echo "dist/prism-wake.zip"

# Update both programs to the current code and record which commit it came
# from. The stamp is merged into whatever variables are already set rather
# than replacing them, because the wake secret lives there and exists nowhere
# else.
deploy: test package
	@test -f config.sh || { echo "No config.sh found. See config.example.sh" >&2; exit 1; }
	@set -eu; . ./config.sh; \
	for fn in "$$WEB_FN" "$$IDLE_FN"; do \
	  echo "updating $$fn to $(GIT_STAMP)"; \
	  aws lambda update-function-code --function-name "$$fn" --region "$$REGION" \
	    --zip-file fileb://dist/prism-wake.zip --query CodeSha256 --output text; \
	  aws lambda wait function-updated --function-name "$$fn" --region "$$REGION"; \
	  vars=$$(aws lambda get-function-configuration --function-name "$$fn" \
	    --region "$$REGION" --query Environment.Variables --output json \
	    | python3 scripts/stamp.py "$(GIT_STAMP)"); \
	  aws lambda update-function-configuration --function-name "$$fn" \
	    --region "$$REGION" --environment "{\"Variables\":$$vars}" \
	    --query 'Environment.Variables.GIT_COMMIT' --output text; \
	  aws lambda wait function-updated --function-name "$$fn" --region "$$REGION"; \
	done

clean:
	rm -rf build dist .pytest_cache
