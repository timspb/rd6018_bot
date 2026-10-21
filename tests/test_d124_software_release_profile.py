"""Python-only D090 release profile: compatibility, negative admission, rollback owner."""
import dataclasses
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import node104_d090_release as release
from node104_d124_release_profile import load_software_release_profile
from node104_d090_transaction import D090Transaction, TransactionError, SystemdService

OLD='58321a866dd68195bf8264d1d9ebe7c18a60748f'
NEW='f06fc6692e7b548d3ee2810def140df228ecb4fc'
HEX='a'*64

def profile():
    pin=dataclasses.replace(release.PINNED,old_source_sha=OLD,source_sha=NEW,
        firmware='2.3-ha-canonical',source_archive_sha256=HEX,
        staging_manifest_sha256='b'*64,firmware_digest=None)
    return {'schema':2,'mode':'python_control_change',
      'preimage_inventory_sha256':'c'*64,'proof_collector_sha256':'d'*64,
      'changed_paths':['application/execution_port.py','runtime/charge/lifecycle.py'],
      'pin':dataclasses.asdict(pin)}

class SoftwareD090ProfileTests(unittest.TestCase):
    def read(self,data):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'profile.json';p.write_text(json.dumps(data))
            return load_software_release_profile(p)
    def test_valid_python_profile_no_signer(self):
        pin,old,record=self.read(profile())
        self.assertEqual(pin.source_sha,NEW)
        self.assertEqual(old,'c'*64)
        self.assertEqual(record['mode'],'python_control_change')
    def test_firmware_paths_not_allowed(self):
        data=profile();data['changed_paths']+=['esphome/rd6018.yaml']
        with self.assertRaises(ValueError):self.read(data)
    def test_missing_preimage_not_allowed(self):
        data=profile();data['preimage_inventory_sha256']=''
        with self.assertRaises(ValueError):self.read(data)
    def test_wrong_firmware_not_allowed(self):
        data=profile();data['pin']['firmware']='2.2-autonomous-authority'
        with self.assertRaises(ValueError):self.read(data)
    def test_unknown_fields_not_allowed(self):
        data=profile();data['new_trust_override']=True
        with self.assertRaises(ValueError):self.read(data)
    def test_missing_admission_callback_not_allowed(self):
        class FakeService:
            pass
        with self.assertRaises(TransactionError):
            D090Transaction(Path('/tmp/nohost'),service=FakeService(),proof=lambda:None,
                 host_check=lambda:None,acceptance=lambda:None,venv_builder=lambda a,b:None,
                 pinned=dataclasses.replace(release.PINNED,source_sha=NEW),
                 software_release=True,preimage_inventory_sha256=HEX)
    def test_existing_hardware_acceptance_remains_fail_closed(self):
        with self.assertRaises(release.GateError):
            release.validate_physical_acceptance({'source_sha':release.SOURCE_SHA,
                'firmware':release.FIRMWARE}, Path('/tmp'))
    def test_software_targeted_acceptance(self):
        pin=dataclasses.replace(release.PINNED,old_source_sha=OLD,source_sha=NEW,
                firmware='2.3-ha-canonical',firmware_digest=None)
        rec={'source_sha':NEW,'old_source_sha':OLD,'firmware':'2.3-ha-canonical',
             'classification':'python_control_change','firmware_unchanged':True,
             'targeted_regression_pass':True,
             'operator_firmware_correspondence_confirmed':True,
             'python_matrix':{'3.10':2501,'3.11':2501,'3.12':2501}}
        release.validate_physical_acceptance(rec,Path('/tmp'),pinned=pin,software_release=True)
        rec['python_matrix']['3.11']=0
        with self.assertRaises(release.GateError):
            release.validate_physical_acceptance(rec,Path('/tmp'),pinned=pin,software_release=True)

if __name__=='__main__':unittest.main()
