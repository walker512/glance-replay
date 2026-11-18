"""Creation-time modes are POSIX protection, not a Windows ACL claim."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from glance_replay import core
ROOT=Path(__file__).resolve().parents[1]
SOURCES=[ROOT/'examples'/n for n in ('notification-day.json','platform-day.json')]

class PrivateOutput(unittest.TestCase):
    def test_both_schemas_byte_compatible(self):
        for source in SOURCES:
            with tempfile.TemporaryDirectory() as t:
                out=Path(t)/'bundle';r=core.build(source,out);expected=core.replay(source.read_bytes())
                self.assertEqual(r,expected);self.assertEqual(core.verify(out),expected)
                self.assertEqual((out/'source.json').read_bytes(),source.read_bytes())
                self.assertEqual((out/'report.json').read_bytes(),core.canonical(expected))
                self.assertEqual((out/'frames.txt').read_bytes(),core.text_frames(expected))
    @unittest.skipUnless(os.name=='posix','POSIX bits, not Windows ACL')
    def test_creation_private_umask000_022(self):
        original=os.open;mkdir=Path.mkdir
        for mask in (0,0o22):
            with tempfile.TemporaryDirectory() as t:
                out=Path(t)/'out';seen=[]
                def create(path,*args,**kw):
                    result=mkdir(path,*args,**kw)
                    if path==out:self.assertEqual(path.stat().st_mode & 0o777,0o700)
                    return result
                def opened(path,flags,mode=0o777,**kw):
                    fd=original(path,flags,mode,**kw)
                    if flags & os.O_CREAT:
                        self.assertTrue(flags & os.O_EXCL);self.assertEqual(os.fstat(fd).st_mode & 0o777,0o600)
                        self.assertEqual(os.fstat(fd).st_size,0);seen.append(path)
                    return fd
                old=os.umask(mask)
                try:
                    with patch.object(core.os,'open',opened),patch.object(Path,'mkdir',create):core.build(SOURCES[0],out)
                finally:os.umask(old)
                self.assertEqual(len(seen),3)
    def test_existing_output_and_file_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);out=root/'out';core.build(SOURCES[0],out)
            before={p.name:p.read_bytes() for p in out.iterdir()}
            with self.assertRaises(OSError):core.build(SOURCES[1],out)
            self.assertEqual(before,{p.name:p.read_bytes() for p in out.iterdir()})
            f=root/'file';f.write_bytes(b'KEEP')
            with self.assertRaises(OSError):core.build(SOURCES[0],f)
            self.assertEqual(f.read_bytes(),b'KEEP')
    def test_symlink_destination_existing_and_dangling(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'target';target.mkdir()
            for n,dest in enumerate((target,root/'missing')):
                link=root/str(n)
                try:link.symlink_to(dest,target_is_directory=True)
                except (OSError,NotImplementedError):self.skipTest('symlink creation unavailable')
                with self.assertRaises(OSError):core.build(SOURCES[0],link)
            self.assertEqual(list(target.iterdir()),[]);self.assertFalse((root/'missing').exists())
    def test_member_injection_not_overwritten(self):
        original=os.open
        for link in (False,True):
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);out=root/'out';target=root/'target';target.write_bytes(b'KEEP');seen=[]
                def opened(path,flags,mode=0o777,**kw):
                    if flags & os.O_CREAT and not seen:
                        seen.append(path)
                        if link:
                            try:Path(path).symlink_to(target)
                            except (OSError,NotImplementedError):self.skipTest('symlink creation unavailable')
                        else:Path(path).write_bytes(b'KEEP')
                    return original(path,flags,mode,**kw)
                with patch.object(core.os,'open',opened):
                    with self.assertRaises(OSError):core.build(SOURCES[0],out)
                self.assertEqual(Path(seen[0]).read_bytes(),b'KEEP');self.assertEqual(target.read_bytes(),b'KEEP')
                with self.assertRaises(core.Invalid):core.verify(out)
    def test_partial_failure_remains_invalid_and_exclusive(self):
        original=os.open
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'out';calls=[]
            def opened(path,flags,mode=0o777,**kw):
                if flags & os.O_CREAT:
                    calls.append(path)
                    if len(calls)==2:raise OSError('injected')
                return original(path,flags,mode,**kw)
            with patch.object(core.os,'open',opened):
                with self.assertRaises(OSError):core.build(SOURCES[0],out)
            self.assertEqual({p.name for p in out.iterdir()},{'source.json'})
            if os.name=='posix':
                self.assertEqual(out.stat().st_mode & 0o777,0o700)
                self.assertEqual((out/'source.json').stat().st_mode & 0o777,0o600)
            with self.assertRaises(core.Invalid):core.verify(out)
            with self.assertRaises(OSError):core.build(SOURCES[0],out)
    def test_concurrent_creators_one_winner(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'out'
            def create(_):
                try:core.build(SOURCES[0],out);return True
                except FileExistsError:return False
            with ThreadPoolExecutor(max_workers=8) as pool:self.assertEqual(sum(pool.map(create,range(16))),1)
            core.verify(out)
    def test_real_cli_and_legacy_permissions_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'out'
            def cli(*args):return subprocess.run([sys.executable,'-m','glance_replay',*map(str,args)],cwd=ROOT,capture_output=True)
            r=cli('replay',SOURCES[0],'--out',out,'--require-pass');self.assertEqual(r.returncode,0,r.stderr)
            out.chmod(0o755)
            for p in out.iterdir():p.chmod(0o644)
            before={p.name:(p.read_bytes(),p.stat().st_mode) for p in out.iterdir()};mode=out.stat().st_mode
            r=cli('verify',out,'--require-pass');self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_mode) for p in out.iterdir()})
            self.assertEqual(mode,out.stat().st_mode)

if __name__=='__main__':unittest.main()
