.PHONY: status plan-foundation apply-foundation dwd-checklist plan-connectors apply-connectors licenses-dryrun licenses licenses-list verify test help

WAIT ?= 15m

help:
	@echo "Available targets:"
	@echo "  status            - Check deployment status & live phase"
	@echo "  plan-foundation   - Generate Stage 1 Foundation plan with plan guard"
	@echo "  apply-foundation  - Apply Stage 1 Foundation plan (0 deletes/replaces)"
	@echo "  dwd-checklist     - Print Google Workspace Domain-Wide Delegation authorization checklist"
	@echo "  plan-connectors   - Generate Stage 3 Connectors & Engines plan with plan guard"
	@echo "  apply-connectors  - Apply Stage 3 Connectors & Engines plan"
	@echo "  licenses-dryrun   - Dry-run license distribution preflight assertions"
	@echo "  licenses          - Distribute subscription seats to customer environment projects"
	@echo "  licenses-list     - List active license allocations and seat quotas"
	@echo "  verify            - Run post-deployment verification (WAIT=$(WAIT))"
	@echo "  test              - Run test harness and Terraform validation"

status:
	python3 scripts/status.py $(ARGS)

plan-foundation:
	@mkdir -p .plans
	terraform plan -input=false -var="enable_connectors=false" -out=.plans/foundation.tfplan
	python3 scripts/plan_guard.py .plans/foundation.tfplan

apply-foundation:
	python3 scripts/plan_guard.py .plans/foundation.tfplan
	terraform apply -input=false .plans/foundation.tfplan

dwd-checklist:
	@python3 scripts/status.py --dwd-checklist

plan-connectors:
	@mkdir -p .plans
	terraform plan -input=false -var="enable_connectors=true" -out=.plans/connectors.tfplan
	python3 scripts/plan_guard.py .plans/connectors.tfplan

apply-connectors:
	python3 scripts/plan_guard.py .plans/connectors.tfplan
	terraform apply -input=false .plans/connectors.tfplan

licenses-dryrun:
	python3 scripts/allocate_licenses.py --distribute --dry-run

licenses: licenses-dryrun
	python3 scripts/allocate_licenses.py --distribute

licenses-list:
	python3 scripts/allocate_licenses.py --list

verify:
	python3 scripts/verify.py --wait $(WAIT)

test:
	python3 scripts/test_red.py
	terraform fmt -check
	terraform validate
