from dataclasses import dataclass

import pytest
from tests.reporting import SyntheticClient

from rag.adapters import ExtractiveMock
from rag.api import create_app
from rag.corpus import DEMO_PASSWORD


class Probe(ExtractiveMock):
    def __init__(self):
        self.calls = []
        self.hook = None

    def generate(self, q, evidence):
        self.calls.append([dict(r) for r in evidence])
        if self.hook:
            self.hook()
        return super().generate(q, evidence)


@dataclass
class Rig:
    app: object
    probe: Probe
    events: list | None

    @property
    def store(self):
        return self.app.state.service.store

    def login(self, uid):
        c = SyntheticClient(self.app, uid, self.events)
        assert c.post("/api/login", json={"username": uid, "password": DEMO_PASSWORD}).status_code == 200
        return c


@pytest.fixture()
def rig(tmp_path, request):
    probe = Probe()
    app = create_app(tmp_path / "test.db", probe)
    app.state.service.store.initialize()
    return Rig(app, probe, [] if request.config.getoption("--case-report") else None)
