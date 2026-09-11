# uv manages the interpreter and the locked dependencies, so every target
# below runs against the same environment on any machine.

.PHONY: test lint package clean

test:
	uv run pytest -q

# Watch mode is handy while filling in the implementation.
test-watch:
	uv run pytest -q --looponfail

# Compiled bytecode from a different interpreter is excluded: shipping stale
# .pyc files to Lambda is a reliable way to debug code that is not running.
package:
	rm -rf build dist && mkdir -p build dist
	cp -r wake build/
	find build -name __pycache__ -type d -exec rm -rf {} +
	cd build && zip -qr ../dist/prism-wake.zip wake
	@echo "dist/prism-wake.zip"

clean:
	rm -rf build dist .pytest_cache
