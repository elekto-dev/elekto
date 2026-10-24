PYTHON:=venv/bin/python
PIP:=venv/bin/pip
PYTEST:=venv/bin/py.test
COV:=venv/bin/coverage

.PHONY: clean venv run test cov test-build test-docker
clean:
	rm -rf venv

venv: clean
	python3.11 -m venv venv
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) console --run

test:
	$(PYTEST) test

cov:
	$(COV) run -m pytest test || true
	$(COV) html
	open htmlcov/index.html

test-build:
	docker build . -t elekto-test --target test

test-docker: test-build
	docker run -it --rm --entrypoint=./test-entrypoint.sh elekto-test

test-docker-notty: test-build
	docker run --rm --entrypoint=./test-entrypoint.sh elekto-test

# ------------------------------------------------------------------------------------------------ #
#                                             Deploy                                               #
# ------------------------------------------------------------------------------------------------ #
# elections.k8s.io runs the image named in kubernetes/k8s.io. Deploying means opening a PR there
# that changes the image tag. An OWNER approves the PR and ArgoCD rolls it out. Every main commit
# has an image, tagged sha-<first 7 characters of the commit>.
#
#   make deploy-diff                       # Local only: show the k8s.io change for SHA (default HEAD)
#   make deploy K8S_IO_FORK=<you>/k8s.io   # Push the change to your fork, open or update the PR
#
# To add an environment, add a DEPLOY_FILE_<name> line and run with ENV=<name>.

ENV ?= production
DEPLOY_FILE_production := kubernetes/gke-aaa/elekto/deployment.yaml
DEPLOY_FILE = $(DEPLOY_FILE_$(ENV))

IMAGE := ghcr.io/elekto-dev/elekto
IMAGE_RE := ghcr\.io/elekto-dev/elekto
SHA ?= $(shell git rev-parse HEAD)
TAG = sha-$(shell echo $(SHA) | cut -c1-7)
BUILD_URL ?=
MANIFEST_TYPES := application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json

K8S_IO_URL ?= https://github.com/kubernetes/k8s.io.git
K8S_IO_DIR ?= .k8s.io
K8S_IO_FORK ?=
K8S_IO_PUSH_URL ?= https://github.com/$(K8S_IO_FORK).git
K8S_IO_BRANCH = elekto-$(ENV)-bump

# Read from the k8s.io checkout, so they are only valid in recipes that run after deploy-checkout.
CURRENT_TAG = $(shell grep -oE '$(IMAGE_RE):[^[:space:]"]+' $(K8S_IO_DIR)/$(DEPLOY_FILE) | head -n 1 | cut -d: -f2)
NEW_COMMITS = $(shell git -C $(K8S_IO_DIR) log --oneline origin/main..HEAD)
COMMIT_TITLE = $(shell git -C $(K8S_IO_DIR) log -1 --format=%s)
COMMIT_BODY = git -C $(K8S_IO_DIR) log -1 --format=%b | grep -v '^Signed-off-by:'
OPEN_PR = $(shell gh pr list -R kubernetes/k8s.io --head $(K8S_IO_BRANCH) --author @me --state open --json number -q '.[].number' | head -n 1)

COMMIT_MESSAGE = -m "Bump elekto $(ENV) to $(TAG)" \
	-m "Points $(ENV) at elekto-dev/elekto@$(SHA)." \
	-m "Changes since $(CURRENT_TAG): https://github.com/elekto-dev/elekto/compare/$(patsubst sha-%,%,$(CURRENT_TAG))...$(SHA)" \
	$(if $(BUILD_URL),-m "Tested and built by $(BUILD_URL)")

.PHONY: deploy-check deploy-checkout deploy-diff deploy deploy-require-fork deploy-push deploy-pr

# 1. Fail early on an unknown ENV or an image that was never pushed.
deploy-check:
	@test -n "$(DEPLOY_FILE)" || { echo "Unknown ENV=$(ENV). Add DEPLOY_FILE_$(ENV) to the Makefile."; exit 1; }
	@token=$$(curl -fsS "https://ghcr.io/token?scope=repository:elekto-dev/elekto:pull" | sed -E 's/.*"token":"([^"]+)".*/\1/') && \
	curl -fsSI -o /dev/null -H "Authorization: Bearer $$token" \
		-H "Accept: $(MANIFEST_TYPES)" \
		https://ghcr.io/v2/elekto-dev/elekto/manifests/$(TAG) \
	|| { echo "$(IMAGE):$(TAG) does not exist. Only main commits have images."; exit 1; }

# 2. Start from a fresh copy of k8s.io main.
deploy-checkout:
	rm -rf $(K8S_IO_DIR)
	git clone -q --filter=blob:none --single-branch -b main $(K8S_IO_URL) $(K8S_IO_DIR)

# 3. Point the manifest at TAG and commit it. No commit when ENV already runs TAG.
deploy-diff: deploy-check deploy-checkout
	sed -i.bak -E 's#($(IMAGE_RE)):[^[:space:]"]+#\1:$(TAG)#' $(K8S_IO_DIR)/$(DEPLOY_FILE)
	rm $(K8S_IO_DIR)/$(DEPLOY_FILE).bak
	@if git -C $(K8S_IO_DIR) diff --quiet; then echo "$(ENV) already runs $(TAG)"; \
	else git -C $(K8S_IO_DIR) commit -q -s -a $(COMMIT_MESSAGE) && git -C $(K8S_IO_DIR) show HEAD; fi

# 4. Push and open the PR, unless step 3 found nothing to change.
deploy: deploy-require-fork deploy-diff
	@$(if $(NEW_COMMITS),$(MAKE) --no-print-directory deploy-push deploy-pr,echo "Nothing to deploy")

deploy-require-fork:
	@test -n "$(K8S_IO_FORK)" || { echo "Set K8S_IO_FORK=<owner>/k8s.io"; exit 1; }

deploy-push:
	git -C $(K8S_IO_DIR) push -q -f $(K8S_IO_PUSH_URL) HEAD:$(K8S_IO_BRANCH)

deploy-pr:
	$(COMMIT_BODY) | $(if $(OPEN_PR),gh pr edit $(OPEN_PR) -R kubernetes/k8s.io,gh pr create -R kubernetes/k8s.io --base main --head $(firstword $(subst /, ,$(K8S_IO_FORK))):$(K8S_IO_BRANCH)) --title "$(COMMIT_TITLE)" --body-file -
