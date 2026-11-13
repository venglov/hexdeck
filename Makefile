.PHONY: install test build package deploy preview

install:
	npm install

test:
	python3 -m pytest -q tests

build:
	npm run typecheck
	npm run build

package:
	scripts/package.sh

deploy:
	scripts/deploy.sh $(DECK)

preview: build
	@echo "Open http://localhost:8765/dev/preview.html"
	python3 -m http.server 8765
