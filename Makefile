# Which instance a target acts on. TOOL=all is the all-in-one image (every tools/*.yaml, port 30080);
# TOOL=kyc|refunds|flags builds/deploys an image that ships and serves just that board
# (internal-tools-<tool>:dev, its own Deployment/Service/PVC, ports 30081/30082/30083).
# `make split` runs the per-tool targets for every tool in SPLIT_TOOLS.
TOOL        ?= all
SPLIT_TOOLS ?= kyc refunds flags
ifeq ($(TOOL),all)
IMAGE     ?= internal-tools:dev
NAME      := internal-tools
TOOLS_ARG :=
else
IMAGE     ?= internal-tools-$(TOOL):dev
NAME      := internal-tools-$(TOOL)
TOOLS_ARG := $(TOOL)
endif
# localhost port that `make forward` maps to each instance (NodePorts are not reachable from the host
# with the Docker driver on macOS / Windows, so this is the portable way in)
LOCAL_PORT_all         ?= 8080
LOCAL_PORT_kyc         ?= 8081
LOCAL_PORT_refunds     ?= 8082
LOCAL_PORT_flags       ?= 8083
LOCAL_PORT_chargebacks ?= 8084
LOCAL_PORT ?= $(LOCAL_PORT_$(TOOL))
NS        ?= internal-tools
PROFILE   ?= minikube
# Docker Hub mirror for the base images; set BASE_REGISTRY=mirror.gcr.io/library if Hub rate-limits you
BASE_REGISTRY ?= docker.io/library
K         := kubectl -n $(NS)
OVERLAY   := deploy/k8s/overlays/$(TOOL)

.PHONY: minikube up image namespace secret deploy redeploy status logs url reseed down destroy \
        forward unforward split split-image split-deploy split-redeploy split-reseed split-down split-forward urls

## One shot: start minikube, build the image, load secrets, deploy, print the URL (TOOL=all|kyc|refunds|flags)
minikube: up image namespace secret deploy url

## One shot for the three per-tool instances
split: up split-image namespace secret split-deploy urls

up:
	minikube status -p $(PROFILE) >/dev/null 2>&1 || minikube start -p $(PROFILE) --driver=docker

## Build locally and load into the cluster (works for docker and containerd runtimes, no registry needed)
image:
	docker build --build-arg BASE_REGISTRY=$(BASE_REGISTRY) --build-arg TOOLS=$(TOOLS_ARG) -t $(IMAGE) .
	minikube -p $(PROFILE) image load $(IMAGE) --overwrite

namespace:
	kubectl apply -f deploy/k8s/namespace.yaml

deploy:
	kubectl apply -k $(OVERLAY)
	$(K) rollout status deploy/$(NAME) --timeout=180s

## After a code change: rebuild the image and roll the pod (same tag, so force a restart)
redeploy: image
	$(K) rollout restart deploy/$(NAME)
	$(K) rollout status deploy/$(NAME) --timeout=180s

## Create/refresh the secret from your shell env; skipped when OPENAI_API_KEY is unset (offline mode).
## One secret is shared by every instance in the namespace; running deployments are restarted to pick it up.
secret:
	@if [ -n "$$OPENAI_API_KEY" ]; then \
	  $(K) create secret generic internal-tools-secrets \
	    --from-literal=OPENAI_API_KEY="$$OPENAI_API_KEY" \
	    --from-literal=WEBHOOK_SIGNING_SECRET="$${WEBHOOK_SIGNING_SECRET:-}" \
	    --dry-run=client -o yaml | $(K) apply -f - \
	  && for d in $$($(K) get deploy -l app.kubernetes.io/name=internal-tools -o name); do $(K) rollout restart $$d; done; \
	else echo "OPENAI_API_KEY not set - running in offline rules/lexical mode"; fi

status:
	$(K) get pods,svc,pvc

logs:
	$(K) logs -f deploy/$(NAME)

url:
	@echo "$(NAME): NodePort http://$$(minikube -p $(PROFILE) ip):$$($(K) get svc $(NAME) -o jsonpath='{.spec.ports[0].nodePort}')  (Linux)"
	@echo "$(NAME): or run 'make forward TOOL=$(TOOL)' -> http://localhost:$(LOCAL_PORT)  (any OS)"

## Map an instance to http://localhost:<LOCAL_PORT> (blocks; Ctrl-C to stop). all=8080 kyc=8081 refunds=8082 flags=8083
forward:
	@echo "$(NAME) -> http://localhost:$(LOCAL_PORT)"
	$(K) port-forward svc/$(NAME) $(LOCAL_PORT):80

## Stop every background port-forward started by `make split-forward`
unforward:
	-pkill -f 'kubectl -n $(NS) port-forward svc/internal-tool[s]' 2>/dev/null || true

## Wipe demo data and reseed
reseed:
	$(K) exec deploy/$(NAME) -- sh -c 'rm -f $$DB_PATH' && $(K) rollout restart deploy/$(NAME)

down:
	kubectl delete -k $(OVERLAY) --ignore-not-found

destroy:
	minikube delete -p $(PROFILE)

# ---- per-tool fan-out ------------------------------------------------------------------
split-image split-deploy split-redeploy split-reseed split-down:
	@for t in $(SPLIT_TOOLS); do $(MAKE) --no-print-directory $(subst split-,,$@) TOOL=$$t || exit 1; done

## Background port-forwards for the three per-tool instances -> localhost:8081/8082/8083
split-forward:
	@for t in $(SPLIT_TOOLS); do \
	  p=$$($(MAKE) --no-print-directory -s print-port TOOL=$$t); \
	  nohup $(K) port-forward svc/internal-tools-$$t $$p:80 >/dev/null 2>&1 & \
	  echo "internal-tools-$$t -> http://localhost:$$p"; \
	done; sleep 2; echo "forwards running in the background; 'make unforward' stops them"

print-port:
	@echo $(LOCAL_PORT)

urls:
	@for t in $(SPLIT_TOOLS); do $(MAKE) --no-print-directory url TOOL=$$t; done
