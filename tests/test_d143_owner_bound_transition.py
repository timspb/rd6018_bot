"""D143 owner integration tests. All paths are isolated; no device I/O."""
from pathlib import Path
import tempfile
import unittest
from tools.node104_d090_transaction import D090Transaction, TransactionError
from tools.d139_offline_transaction import SENTINEL


class FakeService:
    d139_offline_fixture=True
    def __init__(self): self.active=True; self.stops=0; self.starts=0
    def stop(self): self.active=False; self.stops+=1
    def start(self): self.active=True; self.starts+=1


class D143OwnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="d143-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/SENTINEL).write_text("fixture")
        for name in ("app","venv","state","d139-candidate/app","d139-candidate/venv"):
            (self.root/name).mkdir(parents=True)
        for path,val in (("app/version","oldapp"),("venv/version","oldvenv"),
                         ("d139-candidate/app/version","newapp"),
                         ("d139-candidate/venv/version","newvenv"),
                         ("state/session.json","RETIRED"),
                         ("D090_TRANSACTION.json","STARTED"),
                         (".deploy_sha","oldsha")):
            (self.root/path).write_text(val)
        self.svc=FakeService()
        self.owner=object.__new__(D090Transaction)
        self.owner.root=self.root
        self.owner.offline=True
        self.owner.service=self.svc
        self.owner._lock_depth=0

    def test_shared_owner_activation_and_restore(self):
        self.assertEqual(self.owner.d143_offline_cutover()["phase"],"CANDIDATE_RUNNING")
        self.assertEqual((self.root/"app/version").read_text(),"newapp")
        self.assertEqual(self.owner.d143_offline_recover()["phase"],"RESTORED")
        self.assertEqual((self.root/"app/version").read_text(),"oldapp")
        self.assertEqual((self.root/"venv/version").read_text(),"oldvenv")
        self.assertEqual((self.root/"state/session.json").read_text(),"RETIRED")
        self.assertEqual((self.root/"D090_TRANSACTION.json").read_text(),"STARTED")

    def test_production_mode_refuses_before_stop(self):
        self.owner.offline=False
        with self.assertRaisesRegex(TransactionError,"production disabled"):
            self.owner.d143_offline_cutover()
        self.assertEqual(self.svc.stops,0)

    def test_nonfixture_service_refused(self):
        self.svc.d139_offline_fixture=False
        with self.assertRaisesRegex(TransactionError,"production disabled"):
            self.owner.d143_offline_cutover()
        self.assertEqual(self.svc.stops,0)

    def test_crash_recovery_through_shared_lock(self):
        def fault(name):
            if name=="AFTER_NEW_APP_RENAME_BEFORE_JOURNAL":
                raise RuntimeError("injected")
        with self.assertRaisesRegex(RuntimeError,"injected"):
            self.owner.d143_offline_cutover(failpoint=fault)
        self.assertEqual(self.owner.d143_offline_recover()["phase"],"RESTORED")
        self.assertEqual((self.root/"venv/version").read_text(),"oldvenv")
        self.assertEqual((self.root/"state/session.json").read_text(),"RETIRED")

    def test_old_d090_lock_serializes_operations(self):
        # Acquisition of the existing lock remains the only lock owner.
        with self.owner._locked():
            self.assertEqual(self.owner._lock_depth,1)
            self.assertEqual(self.owner.d143_offline_cutover()["phase"],"CANDIDATE_RUNNING")
            self.assertEqual(self.owner._lock_depth,1)
        self.assertEqual(self.owner._lock_depth,0)


if __name__=="__main__":
    unittest.main()
