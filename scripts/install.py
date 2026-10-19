#!/usr/bin/env python3
"""Copy selected skills into an existing project without replacing its files."""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('ai-design-discovery', 'ai-design-direction', 'ai-design-implementation',
          'ai-design-review', 'break-ui', 'mobile-native', 'ai-design-elements')


def same_tree(source, target):
    if not target.is_dir() or target.is_symlink():
        return False
    def files(root):
        result = {}
        for item in root.rglob('*'):
            if item.is_symlink():
                return None
            if '__pycache__' in item.relative_to(root).parts or item.suffix in {'.pyc', '.pyo'}:
                continue
            if item.is_file():
                result[item.relative_to(root)] = item.read_bytes()
        return result
    a, b = files(source), files(target)
    return a is not None and a == b


def install(project, skills=SKILLS, dry_run=False):
    project = Path(project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError('Project directory must already exist: ' + str(project))
    destination = project / '.agents' / 'skills'
    for parent in [project / '.agents', destination]:
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError('Expected an ordinary directory, not a file or symlink: ' + str(parent))
    plan = []
    for name in dict.fromkeys(skills):
        if name not in SKILLS:
            raise ValueError('Unknown skill: ' + name)
        source, target = ROOT / '.agents/skills' / name, destination / name
        if not (source / 'SKILL.md').is_file():
            raise ValueError('Incomplete source package: ' + name)
        if target.is_symlink() or (target.exists() and not same_tree(source, target)):
            raise ValueError('Existing skill differs; nothing copied. Compare and back it up before updating: ' + str(target))
        plan.append((name, source, target, target.exists()))
    # Preflight all conflicts before writing any selected package.
    if dry_run:
        return [(name, 'unchanged' if exists else 'would-copy') for name, _, _, exists in plan]
    if all(exists for _, _, _, exists in plan):
        return [(name, 'unchanged') for name, _, _, _ in plan]
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='.ai-design-', dir=destination) as staging:
        for name, source, target, exists in plan:
            if exists:
                results.append((name, 'unchanged'))
                continue
            staged = Path(staging) / name
            shutil.copytree(source, staged, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
            if target.exists() or target.is_symlink():
                raise ValueError('Destination changed during installation: ' + str(target))
            staged.rename(target)
            results.append((name, 'copied'))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path, help='Existing website project directory')
    parser.add_argument('--skills', nargs='+', choices=SKILLS, default=list(SKILLS))
    parser.add_argument('--dry-run', action='store_true', help='Show the plan without creating files')
    args = parser.parse_args()
    try:
        results = install(args.project, args.skills, args.dry_run)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
    for name, state in results:
        print(f'{state}: {name}')
    print('Website code and AGENTS.md were not changed. See docs/GETTING-STARTED.md.')


if __name__ == '__main__':
    main()
