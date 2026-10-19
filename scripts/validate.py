#!/usr/bin/env python3
"""Offline structural validation of this distribution; not a behavioral evaluation."""
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('ai-design-discovery', 'ai-design-direction', 'ai-design-implementation',
          'ai-design-review', 'break-ui', 'mobile-native', 'ai-design-elements')


def validate(root=ROOT):
    root = Path(root)
    errors = []
    manifest = json.loads((root / 'package-manifest.json').read_text(encoding='utf-8'))
    expected = manifest['skill_files']
    actual = {p.relative_to(root).as_posix(): p for p in (root / '.agents/skills').rglob('*')
              if p.is_file() and '__pycache__' not in p.relative_to(root).parts
              and p.suffix not in {'.pyc', '.pyo'}}
    version = root / 'VERSION'
    if not version.is_file() or version.read_text(encoding='utf-8').strip() != manifest['framework_version']:
        errors.append('VERSION differs from package-manifest.json')
    if set(actual) != set(expected):
        errors.append('Skill file inventory differs from package-manifest.json')
    for name, digest in expected.items():
        p = root / name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            errors.append('Skill checksum mismatch: ' + name)
    for name in SKILLS:
        path = root / '.agents/skills' / name / 'SKILL.md'
        if not path.is_file():
            errors.append('Missing SKILL.md: ' + name)
            continue
        text = path.read_text(encoding='utf-8')
        if not text.startswith('---\n') or '\n---\n' not in text[4:]:
            errors.append('Missing skill frontmatter: ' + name)
            continue
        head, body = text[4:].split('\n---\n', 1)
        fields = dict(re.findall(r'^([a-z_]+):\s*(.+)$', head, re.M))
        if fields.get('name') != name or not fields.get('description') or not body.strip():
            errors.append('Invalid name, description or body: ' + name)
        ui = root / '.agents/skills' / name / 'agents/openai.yaml'
        if not ui.is_file() or any(key + ':' not in ui.read_text(encoding='utf-8') for key in ['display_name','short_description','default_prompt']):
            errors.append('Missing UI metadata fields: ' + name)
    for name in ['break-ui','mobile-native']:
        folder = root / '.agents/skills' / name
        if 'Emil Kowalski' not in (folder / 'LICENSE').read_text(encoding='utf-8') or not (folder / 'SOURCE.md').is_file():
            errors.append('Missing upstream attribution: ' + name)
    markdown = [p for p in root.rglob('*.md') if not any(part in {'.git','__pycache__','.validation'} for part in p.relative_to(root).parts)]
    for path in markdown:
        text = path.read_text(encoding='utf-8')
        if re.search(r'/Users/|/home/[a-z][\w-]*/|My-Job|Nextcloud|irinaevgrafova|\bИрин[а-яё]*\b', text, re.I):
            errors.append('Private development context in ' + path.relative_to(root).as_posix())
        for target in re.findall(r'\]\(([^\n]+?)\)', text):
            target = target.strip().strip('<>')
            if target.startswith(('https://','http://','mailto:','#')):
                continue
            target = unquote(target.split('#', 1)[0])
            if not target or not (path.parent / target).exists():
                errors.append('Broken local link: ' + path.relative_to(root).as_posix() + ' -> ' + target)
    for required in ['README.md','LICENSE','CONTRIBUTING.md','CREDITS.md','CHANGELOG.md','SECURITY.md']:
        if not (root / required).is_file():
            errors.append('Missing distribution document: ' + required)
    return {'pass': not errors, 'skills': len(SKILLS), 'skill_files': len(actual), 'markdown_files': len(markdown), 'errors': errors,
            'scope': 'Offline structure, inventory, checksums, local links and known private-context patterns. Not full YAML/schema, visual, behavioral or secret validation.'}


if __name__ == '__main__':
    try:
        result = validate()
    except (OSError, ValueError, KeyError) as error:
        result = {'pass': False, 'errors': [str(error)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['pass'] else 1)
