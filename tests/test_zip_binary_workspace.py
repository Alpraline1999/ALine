"""ZipBinaryWorkspace 单元测试"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path


class TestZipBinaryWorkspace(unittest.TestCase):

    def setUp(self):
        from core.zip_binary_workspace import ZipBinaryWorkspace
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_aline_"))
        # 创建一个测试用的 .aline ZIP 文件
        self.zip_path = str(self.temp_dir / "test.aline")
        with zipfile.ZipFile(self.zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('project.json', '{"name": "test"}')
            zf.writestr('files/images/test.png', b'fake_png_content')
            zf.writestr('files/source_files/data.csv', b'a,b\n1,2')
        self.ws = ZipBinaryWorkspace(self.zip_path)

    def tearDown(self):
        self.ws.cleanup()
        shutil.rmtree(str(self.temp_dir), ignore_errors=True)

    def test_initial_temp_dir_created(self):
        self.assertTrue(self.ws.temp_dir.exists())
        self.assertTrue(self.ws.temp_dir.is_dir())

    # ── resolve (懒提取) ───────────────────────────────────

    def test_resolve_lazy_extract_from_zip(self):
        """resolve() 应在文件不存在时从 ZIP 懒提取。"""
        result = self.ws.resolve('files/images/test.png')
        self.assertTrue(os.path.exists(result))
        with open(result, 'rb') as f:
            self.assertEqual(f.read(), b'fake_png_content')

    def test_resolve_returns_existing_file(self):
        """resolve() 应返回已提取文件的路径（不重复提取）。"""
        path1 = self.ws.resolve('files/images/test.png')
        path2 = self.ws.resolve('files/images/test.png')
        self.assertEqual(path1, path2)
        self.assertTrue(os.path.exists(path1))

    def test_resolve_non_existent_file(self):
        """resolve() 对 ZIP 中不存在的文件应返回不存在的路径。"""
        result = self.ws.resolve('files/images/nonexistent.png')
        self.assertFalse(os.path.exists(result))

    # ── store ──────────────────────────────────────────────

    def test_store_copies_file_to_workspace(self):
        source = self.temp_dir / "new_file.txt"
        source.write_text("hello")
        result = self.ws.store(str(source), 'files/source_files/new_file.txt')
        self.assertTrue(os.path.exists(result))
        self.assertEqual(Path(result).read_text(), "hello")

    def test_store_creates_intermediate_dirs(self):
        source = self.temp_dir / "deep_file.txt"
        source.write_text("deep")
        result = self.ws.store(str(source), 'files/source_files/a/b/c/deep_file.txt')
        self.assertTrue(os.path.exists(result))

    # ── remove ─────────────────────────────────────────────

    def test_remove_deletes_file(self):
        source = self.temp_dir / "to_remove.txt"
        source.write_text("remove me")
        self.ws.store(str(source), 'files/source_files/to_remove.txt')
        stored = self.ws.resolve('files/source_files/to_remove.txt')
        self.assertTrue(os.path.exists(stored))
        self.ws.remove('files/source_files/to_remove.txt')
        self.assertFalse(os.path.exists(stored))

    def test_remove_nonexistent_does_not_raise(self):
        self.ws.remove('files/source_files/ghost.txt')

    # ── move ───────────────────────────────────────────────

    def test_move_relocates_file(self):
        source = self.temp_dir / "movable.txt"
        source.write_text("move me")
        self.ws.store(str(source), 'files/source_files/movable.txt')
        self.ws.move('files/source_files/movable.txt', 'files/source_files/moved.txt')
        self.assertFalse(os.path.exists(self.ws.resolve('files/source_files/movable.txt')))
        self.assertTrue(os.path.exists(self.ws.resolve('files/source_files/moved.txt')))

    # ── exists_in_zip ─────────────────────────────────────

    def test_exists_in_zip_true(self):
        self.assertTrue(self.ws.exists_in_zip('files/images/test.png'))

    def test_exists_in_zip_false(self):
        self.assertFalse(self.ws.exists_in_zip('files/images/nope.png'))

    # ── modified_paths ────────────────────────────────────

    def test_modified_paths_after_store(self):
        source = self.temp_dir / "added.txt"
        source.write_text("added")
        self.ws.store(str(source), 'files/source_files/added.txt')
        paths = self.ws.modified_paths()
        self.assertIn('files/source_files/added.txt', paths)

    def test_modified_paths_after_extract(self):
        self.ws.resolve('files/images/test.png')
        paths = self.ws.modified_paths()
        self.assertIn('files/images/test.png', paths)

    # ── pack_to_zip ───────────────────────────────────────

    def test_pack_to_zip_writes_files(self):
        source = self.temp_dir / "packed.txt"
        source.write_text("packed data")
        self.ws.store(str(source), 'files/source_files/packed.txt')
        out_path = str(self.temp_dir / "output.aline")
        with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            self.ws.pack_to_zip(zf, {'files/source_files/packed.txt'})
        with zipfile.ZipFile(out_path, 'r') as zf:
            self.assertIn('files/source_files/packed.txt', zf.namelist())
            self.assertEqual(zf.read('files/source_files/packed.txt').decode(), "packed data")

    # ── cleanup ───────────────────────────────────────────

    def test_cleanup_removes_temp_dir(self):
        tmp = self.ws.temp_dir
        self.assertTrue(tmp.exists())
        self.ws.cleanup()
        self.assertFalse(tmp.exists())

    def test_multiple_cleanup_is_safe(self):
        self.ws.cleanup()
        self.ws.cleanup()  # Should not raise


if __name__ == '__main__':
    unittest.main()
