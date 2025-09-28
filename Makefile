PYTEST=pytest

.PHONY: test unit integration

unit:
	$(PYTEST) -q -k 'not integration'

integration:
	$(PYTEST) -q -m integration

test:
	$(PYTEST) -q
