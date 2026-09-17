IMAGE     ?= internal-tools:dev
NS        ?= internal-tools
PROFILE   ?= minikube
# Docker Hub mirror for the base images; set BASE_REGISTRY=mirror.gcr.io/library if Hub rate-limits you
BASE_REGISTRY ?= docker.io/library
K         := kubectl -n $(NS)

.PHONY: minikube up image namespace secret deploy redeploy status logs url reseed down destroy

## One shot: start minikube, build the image, load secrets, deploy, print the URL
minikube: up image namespace secret deploy url

up:
	minikube status -p $(PROFILE) >/dev/null 2>&1 || minikube start -p $(PROFILE) --driver=docker

## Build locally and load into the cluster (works for docker and containerd runtimes, no registry needed)
image:
	docker build --build-arg BASE_REGISTRY=$(BASE_REGISTRY) -t $(IMAGE) .
	minikube -p $(PROFILE) image load $(IMAGE) --overwrite

namespace:
	kubectl apply -f deploy/k8s/namespace.yaml

deploy:
	kubectl apply -k deploy/k8s
	$(K) rollout status deploy/internal-tools --timeout=180s

## After a code change: rebuild the image and roll the pod (same tag, so force a restart)
redeploy: image
	$(K) rollout restart deploy/internal-tools
	$(K) rollout status deploy/internal-tools --timeout=180s

## Create/refresh the secret from your shell env; skipped when OPENAI_API_KEY is unset (offline mode)
secret:
	@if [ -n "$$OPENAI_API_KEY" ]; then \
	  $(K) create secret generic internal-tools-secrets \
	    --from-literal=OPENAI_API_KEY="$$OPENAI_API_KEY" \
	    --from-literal=WEBHOOK_SIGNING_SECRET="$${WEBHOOK_SIGNING_SECRET:-}" \
	    --dry-run=client -o yaml | $(K) apply -f - \
	  && { $(K) get deploy internal-tools >/dev/null 2>&1 && $(K) rollout restart deploy/internal-tools || true; }; \
	else echo "OPENAI_API_KEY not set - running in offline rules/lexical mode"; fi

status:
	$(K) get pods,svc,pvc

logs:
	$(K) logs -f deploy/internal-tools

url:
	@echo "App: $$(minikube -p $(PROFILE) service internal-tools -n $(NS) --url)"

## Wipe demo data and reseed
reseed:
	$(K) exec deploy/internal-tools -- sh -c 'rm -f $$DB_PATH' && $(K) rollout restart deploy/internal-tools

down:
	kubectl delete -k deploy/k8s --ignore-not-found

destroy:
	minikube delete -p $(PROFILE)
