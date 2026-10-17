"""Offline exact-main source pairing and approved D061 overlay tamper tests."""
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import d061_transport_windows as staging
from tools import run_d061_takeover_smoke as runner
from tools.acceptance_guard import pairing

ROOT=Path(__file__).resolve().parents[1]


# These archive-reconstruction tests require the Git object database of the
# historical D061 commit. The production D090 source.tar intentionally contains
# only tracked source bytes, not .git. Git checkout CI must still execute all
# of these tests; a byte-verified release archive must not fail merely because
# it lacks its repository history or the Git executable.
@unittest.skipUnless(
    (ROOT / ".git").exists() and shutil.which("git") is not None,
    "historical D061 git-archive pairing requires a VCS checkout (runs in CI)",
)
class D061StagePairingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=runner.read_pinned_manifest(ROOT/'tools/acceptance_guard/source-manifest.json')
        raw=subprocess.check_output(['git','archive','--format=tar',staging.SHA],cwd=ROOT)
        cls.canonical_tar=runner.normalize_git_archive(raw,cls.manifest)
        cls.overlay_tar=runner.make_takeover_overlay(cls.manifest)

    def _stage(self,root,overlay=None):
        canonical=root/'.canonical-source'
        canonical.mkdir(mode=0o700)
        with tarfile.open(fileobj=io.BytesIO(self.canonical_tar),mode='r:') as tf:
            tf.extractall(canonical,filter='data')
        shutil.copytree(canonical,root,dirs_exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(overlay or self.overlay_tar),mode='r:gz') as tf:
            tf.extractall(root,filter='data')
        return canonical,root

    def test_exact_main_and_attested_supplemental_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical,active=self._stage(Path(tmp))
            self.assertEqual(pairing.verify_pairing(canonical,active,active/'source-manifest.json',
                                                    active/'overlay-attestation.json'),875)

    def test_canonical_or_supplemental_tamper_rejected(self):
        for kind in ('canonical','supplemental'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                canonical,active=self._stage(Path(tmp))
                target=canonical/'README.md' if kind=='canonical' else active/'tools/acceptance_guard/guard.py'
                target.write_bytes(target.read_bytes()+b'\n# modification')
                with self.assertRaises(RuntimeError):
                    pairing.verify_pairing(canonical,active,active/'source-manifest.json',
                                           active/'overlay-attestation.json')

    def test_overlay_missing_duplicate_extra_member_rejected(self):
        for kind in ('missing','duplicate','extra'):
            with self.subTest(kind=kind):
                result=io.BytesIO()
                with tarfile.open(fileobj=io.BytesIO(self.overlay_tar),mode='r:gz') as src,tarfile.open(fileobj=result,mode='w:gz') as dst:
                    members=src.getmembers()
                    if kind=='missing':members=members[:-1]
                    for item in members:dst.addfile(item,src.extractfile(item))
                    if kind=='duplicate':dst.addfile(members[0],src.extractfile(members[0]))
                    if kind=='extra':
                        member=tarfile.TarInfo('unreviewed.py');member.size=2
                        dst.addfile(member,io.BytesIO(b'x\n'))
                payload=result.getvalue()
                with self.assertRaises(RuntimeError):
                    runner.validate_takeover_overlay(payload,hashlib.sha256(payload).hexdigest())

    def test_exact_source_archive_missing_duplicate_extra_rejected(self):
        original=subprocess.check_output(['git','archive','--format=tar',staging.SHA],cwd=ROOT)
        for kind in ('missing','duplicate','extra'):
            with self.subTest(kind=kind):
                dstbytes=io.BytesIO()
                with tarfile.open(fileobj=io.BytesIO(original),mode='r:') as src,tarfile.open(fileobj=dstbytes,mode='w:') as dst:
                    members=src.getmembers()
                    if kind=='missing':members=members[:-1]
                    for member in members:dst.addfile(member,src.extractfile(member) if member.isfile() else None)
                    if kind=='duplicate':
                        member=next(x for x in members if x.isfile())
                        dst.addfile(member,src.extractfile(member))
                    if kind=='extra':
                        member=tarfile.TarInfo('unapproved.txt');member.size=1
                        dst.addfile(member,io.BytesIO(b'x'))
                with self.assertRaises(RuntimeError):
                    runner.normalize_git_archive(dstbytes.getvalue(),self.manifest)

    def test_archive_digest_and_root_owned_receipt(self):
        blob=self.overlay_tar
        digest=hashlib.sha256(blob).hexdigest()
        self.assertEqual(runner.validate_takeover_overlay(blob,digest)['source-manifest.json'],
                         runner.MANIFEST_SHA256)
        self.assertNotEqual(hashlib.sha256(blob+b'tamper').hexdigest(),digest)
        stage=staging.STAGE_ROOT+'/rd6018-d061-takeover-a1234'
        receipt={'result':'PASS','containment_complete':True}
        with patch.object(staging,'remote_exec',return_value=json.dumps(receipt)) as execute:
            self.assertEqual(runner.read_root_owned_transaction(object(),stage),receipt)
            self.assertIn('sudo -n cat --',execute.call_args.args[1])
        with self.assertRaises(RuntimeError):
            runner.read_root_owned_transaction(object(),'/tmp/untrusted')
