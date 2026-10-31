import json
import tempfile
import unittest
from pathlib import Path
from tools.node104_d090_transaction import digest, inventory
from tools.d144_state_preserving_transition import OwnerTransition, TransitionError

class FakeService:
    def __init__(self): self.running=True; self.stops=0
    def active(self): return self.running
    def main_pid(self): return 123 if self.running else 0
    def stop(self): self.running=False; self.stops+=1
    def start(self): self.running=True
    def stable(self): return self.running

class D144Tests(unittest.TestCase):
    def test_engine_has_separate_journal(self):
        self.assertEqual(__import__("tools.d144_state_preserving_transition",fromlist=["JOURNAL"]).JOURNAL,"D144_TRANSACTION.json")

    def test_stub(self):
        self.assertTrue(True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.candidate=self.root/"candidate"
        for p in ("app","venv","state","candidate/app","candidate/venv"):
            (self.root/p).mkdir(parents=True)
        for p,v in (("app/x","old"),("venv/x","old"),("candidate/app/x","new"),("candidate/venv/x","new"),("state/session","RETIRED"),("D090_TRANSACTION.json",'{"phase":"STARTED"}'),(".deploy_sha","legacy")):
            (self.root/p).write_text(v)

        self.old={p:inventory(self.root/p) for p in ("app","venv")}
        self.new={p:inventory(self.candidate/p) for p in ("app","venv")}
        self.service=FakeService()

    def proof(self, *, require_stopped):
        if require_stopped and self.service.main_pid()!=0:
            raise TransitionError('service unexpectedly active')
