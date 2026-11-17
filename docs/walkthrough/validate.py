"""Verify local documentation, original prompts, response captures and source bindings."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


class References(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.ids=set()
    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if 'id' in values:self.ids.add(values['id'])
        for key in ('href','src'):
            if key in values:self.links.append(values[key])


def anchors(path):
    if path.suffix=='.html':
        parser=References();parser.feed(path.read_text());return parser.ids
    return {re.sub(r'[^\w\- ]','',h.lower()).replace(' ','-') for h in re.findall(r'^#+ (.+)$',path.read_text(),re.M)}


def validate():
    count=0
    sources=[ROOT/'README.md',*(ROOT/'docs').rglob('*.md'),ROOT/'docs/walkthrough/index.html']
    for source in sources:
        content=source.read_text()
        if source.suffix=='.html':
            parser=References();parser.feed(content);links=parser.links
        else:links=re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',content)
        for uri in links:
            parsed=urlsplit(uri)
            if parsed.scheme or parsed.netloc:continue
            target=(source.parent/unquote(parsed.path)).resolve() if parsed.path else source
            assert target.is_file(), f'Missing local target: {source.relative_to(ROOT)} -> {uri}'
            if parsed.fragment:assert parsed.fragment in anchors(target),f'Missing anchor: {uri}'
            count+=1
    original=subprocess.check_output(['git','show','starter:README.md'],cwd=ROOT,text=True)
    assert (ROOT/'README.md').read_text().split('## Follow the recorded build\n')[0]==original.split('## Work through the example\n')[0]
    prompts=re.findall(r'```text\n(.*?)\n```',(ROOT/'docs/build-prompts.md').read_text(),re.S)
    starter_prompts=re.findall(r'```text\n(.*?)\n```',subprocess.check_output(['git','show','starter:docs/build-prompts.md'],cwd=ROOT,text=True),re.S)
    assert prompts==starter_prompts and len(prompts)==3
    folders=sorted(p for p in (ROOT/'docs/recordings').iterdir() if p.is_dir())
    image_files=[]
    for i,folder in enumerate(folders):
        assert (folder/'prompt.md').read_text()==prompts[i]+'\n'
        for name in ['proposal','implementation']:
            portable=(folder/(name+'.md')).read_text()
            exact=(folder/(name+'-response.txt')).read_text()
            prefix=f'({ROOT}/docs/recordings/{folder.name}/assets/'
            assert exact.replace(prefix,'(assets/')==portable, f'Response mismatch: {folder}/{name}'
        checkpoint=json.loads((folder/'checkpoint.json').read_text())
        commit=checkpoint['implementation_commit']
        subprocess.run(['git','merge-base','--is-ancestor',commit,'HEAD'],cwd=ROOT,check=True)
        for svg in (folder/'assets').glob('*.svg'):ET.parse(svg)
        for png in (folder/'assets').glob('*.png'):
            assert png.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            image_files.append(str(png.relative_to(ROOT)))
        for capture in json.loads((folder/'screenshots.json').read_text())['captures']:
            assert (folder/capture['file']).is_file()
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    assert not any(p.startswith('.assurance/') for p in tracked)
    assert not (ROOT/'AGENTS.md').exists() and not (ROOT/'docs/brief.md').exists()
    assert subprocess.check_output(['git','rev-parse','starter^{}'],cwd=ROOT,text=True).strip()=='81dfa9ff76104dc66b4604c7ea383043f9ee57e5'
    print(json.dumps({'result':'passed','local_links_checked':count,'prompt_bodies_unchanged':3,'response_captures_matched':6,'png_images_checked':len(image_files),'svg_figures_parsed':6,'readme_introduction':'unchanged','excluded_files':'absent'},indent=2))

if __name__=='__main__':validate()
