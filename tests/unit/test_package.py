import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


installer, validator = module('install'), module('validate')


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ai-design-test-')
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / 'website with spaces'
        self.project.mkdir()
        (self.project / 'AGENTS.md').write_text('Existing project policy\n')

    def test_install_and_repeat_preserve_existing_project(self):
        self.assertTrue(all(s == 'copied' for _, s in installer.install(self.project)))
        self.assertTrue(all(s == 'unchanged' for _, s in installer.install(self.project)))
        self.assertEqual((self.project / 'AGENTS.md').read_text(), 'Existing project policy\n')
        for name in installer.SKILLS:
            self.assertTrue(installer.same_tree(ROOT / '.agents/skills' / name, self.project / '.agents/skills' / name))

    def test_conflict_preflight_prevents_partial_install(self):
        folder = self.project / '.agents/skills/ai-design-review'
        folder.mkdir(parents=True)
        (folder / 'SKILL.md').write_text('Owner changes')
        with self.assertRaises(ValueError):
            installer.install(self.project)
        self.assertEqual((folder / 'SKILL.md').read_text(), 'Owner changes')
        self.assertFalse((folder.parent / 'ai-design-discovery').exists())

    def test_dry_run_creates_nothing(self):
        states = installer.install(self.project, dry_run=True)
        self.assertEqual(len(states), 6)
        self.assertFalse((self.project / '.agents').exists())

    def test_subset_installs_only_requested_package(self):
        installer.install(self.project, ['ai-design-review'])
        self.assertEqual([p.name for p in (self.project / '.agents/skills').iterdir()], ['ai-design-review'])

    def test_missing_project_refused(self):
        with self.assertRaises(ValueError):
            installer.install(self.project / 'missing')

    def test_symlink_destination_refused(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (self.project / '.agents').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            installer.install(self.project)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_package_refused(self):
        destination = self.project / '.agents/skills'
        destination.mkdir(parents=True)
        (destination / 'ai-design-review').symlink_to(ROOT / '.agents/skills/ai-design-review', target_is_directory=True)
        with self.assertRaises(ValueError):
            installer.install(self.project)


class ValidationTests(unittest.TestCase):
    def test_distribution_is_valid(self):
        result = validator.validate()
        self.assertEqual(result['errors'], [])

    def test_missing_and_changed_skill_detected(self):
        import shutil
        with tempfile.TemporaryDirectory(prefix='ai-design-validator-') as temp:
            destination = Path(temp)
            shutil.copytree(ROOT / '.agents', destination / '.agents')
            shutil.copy2(ROOT / 'package-manifest.json', destination / 'package-manifest.json')
            skill = destination / '.agents/skills/ai-design-review/SKILL.md'
            skill.write_text(skill.read_text() + '\nChanged\n')
            self.assertTrue(any('checksum mismatch' in e for e in validator.validate(destination)['errors']))
            skill.unlink()
            self.assertTrue(any('Missing SKILL.md' in e for e in validator.validate(destination)['errors']))


if __name__ == '__main__':
    unittest.main()
