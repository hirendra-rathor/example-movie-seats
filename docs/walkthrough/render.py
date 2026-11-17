"""Build the offline reader from recorded Markdown; no third-party packages needed.

The small Markdown renderer supports the constructs used by these recordings.
All prose comes from the preserved files; navigation and source labels are editorial.
"""
from html import escape
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
RECORDINGS = HERE.parent / 'recordings'
MILESTONES = [('01-holds', 'Hold a complete selection', 'Atomic groups · durable identity'),
              ('02-booking', 'Finish bookings and recover replies', 'Terminal states · safe retries'),
              ('03-expiration', 'Release abandoned holds', 'Absolute deadlines · container recovery')]


def inline(value):
    tokens = []
    def save(content):
        tokens.append(content)
        return f'\x00{len(tokens)-1}\x00'
    value = re.sub(r'`([^`]+)`', lambda m: save('<code>'+escape(m[1])+'</code>'), value)
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: save(f'<a href="{escape(m[2],quote=True)}">{escape(m[1])}</a>'), value)
    value = escape(value)
    value = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', value)
    return re.sub(r'\x00(\d+)\x00', lambda m: tokens[int(m[1])], value)


def markdown(source, directory):
    source = source.replace('(assets/', f'(../recordings/{directory}/assets/')
    output = []; lines = source.splitlines(); i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip(): i += 1; continue
        if line.startswith('```'):
            code = []; i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]); i += 1
            output.append('<pre><code>'+escape('\n'.join(code))+'</code></pre>'); i += 1; continue
        picture = re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)', line)
        if picture:
            alt, uri = picture.groups()
            kind = 'Application screenshot' if 'Working application' in alt else 'Explanatory diagram'
            output.append(f'<figure><button class="image-button" data-figure="{escape(uri,quote=True)}" data-caption="{escape(alt,quote=True)}" aria-label="Inspect {escape(kind,quote=True)}"><img src="{escape(uri,quote=True)}" alt="{escape(alt,quote=True)}" loading="lazy"></button><figcaption><span>{kind}</span><button class="text-button" data-figure="{escape(uri,quote=True)}" data-caption="{escape(alt,quote=True)}">Inspect full size ↗</button></figcaption></figure>')
            i += 1; continue
        if line.startswith('|'):
            table = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', c) for c in cells): table.append(cells)
                i += 1
            output.append('<div class="table-scroll"><table><thead><tr>'+''.join('<th>'+inline(c)+'</th>' for c in table[0])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>' for row in table[1:])+'</tbody></table></div>')
            continue
        if line.startswith('>'):
            block=[]
            while i < len(lines) and lines[i].startswith('>'):
                block.append(lines[i].lstrip('> '));i+=1
            output.append('<blockquote>'+inline(' '.join(block))+'</blockquote>');continue
        heading = re.match(r'^(#{1,6}) (.*)', line)
        if heading:
            depth = min(len(heading[1])+1,6)
            output.append(f'<h{depth}>'+inline(heading[2])+f'</h{depth}>');i+=1;continue
        bullet = re.match(r'^(?:- |\d+\. )(.*)',line)
        if bullet:
            ordered=not line.startswith('- '); tag='ol' if ordered else 'ul'; items=[]
            while i<len(lines) and (item:=re.match(r'^(?:- |\d+\. )(.*)',lines[i])):
                items.append('<li>'+inline(item[1])+'</li>');i+=1
            output.append(f'<{tag}>'+''.join(items)+f'</{tag}>');continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(?:\||!\[|```|#|>|- |\d+\. )',lines[i]):
            paragraph.append(lines[i]);i+=1
        output.append('<p>'+inline(' '.join(paragraph))+'</p>')
    return '\n'.join(output)


def render():
    navigation=[];articles=[]
    for number,(directory,title,subtitle) in enumerate(MILESTONES,1):
        folder=RECORDINGS/directory
        checkpoint=json.loads((folder/'checkpoint.json').read_text())
        commit=checkpoint['implementation_commit']
        navigation.append(f'<a class="milestone-link" href="#m{number}-prompt" data-milestone="m{number}"><span class="step">0{number}</span><span><strong>{escape(title)}</strong><small>{escape(subtitle)}</small></span></a>')
        stages=['prompt','proposal','authorization','implementation','evidence']
        tabs=''.join(f'<a role="tab" id="m{number}-{stage}-tab" aria-controls="m{number}-{stage}" href="#m{number}-{stage}">{stage.title()}</a>' for stage in stages)
        panels=[]
        for stage in stages:
            heading={'prompt':'The request','proposal':'The design proposal','authorization':'Standing authorization','implementation':'The implemented result','evidence':'Verification and source records'}[stage]
            source=folder/(stage+'.md')
            if stage=='prompt':
                prompt=source.read_text()
                body='<p class="source-note">Recorded prompt · unchanged from the build guide</p><button class="copy-button" data-copy="m'+str(number)+'-prompt-text">Copy prompt</button><pre id="m'+str(number)+'-prompt-text" class="prompt"><code>'+escape(prompt.strip())+'</code></pre>'
            elif stage=='evidence':
                body=f'<p class="source-note">Editorial evidence index · recorded observations remain available below</p><div class="evidence-grid"><div><b>{checkpoint["tests"]["passed"]}</b><span>tests passed at this checkpoint</span></div><div><b>Passed</b><span>real-process acceptance</span></div></div>'
                body+='<p>Implementation checkpoint <code>'+commit+'</code>. These new commits are local until explicitly published.</p><pre><code>git switch --detach '+commit+'</code></pre>'
                files=['checkpoint.json','acceptance.json','screenshots.json','figures.json']
                files += [p.name for p in folder.glob('*regression.json')]
                if (folder/'previous-scenario.json').exists():files.append('previous-scenario.json')
                if (folder/'container-acceptance.json').exists():files.append('container-acceptance.json')
                body+='<ul class="file-list">'+''.join(f'<li><a href="../recordings/{directory}/{name}">{escape(name)}</a></li>' for name in files)+'</ul>'
                for name in ['acceptance.json','container-acceptance.json']:
                    if (folder/name).exists():
                        body+=f'<details><summary>{escape(name)} · observed results</summary><pre><code>'+escape((folder/name).read_text())+'</code></pre></details>'
                body+='<h3>All working-application screenshots</h3>'
                screenshots=json.loads((folder/'screenshots.json').read_text())
                for capture in screenshots['captures']:
                    body+=markdown(f'![Working application screenshot: GET {capture["route"]}, HTTP {capture["status"]}.]({capture["file"]})',directory)
            else:
                label='Recorded assistant response' if stage in ['proposal','implementation'] else 'Editorial note quoting the user’s standing instruction'
                body=f'<p class="source-note">{label}</p>'+markdown(source.read_text(),directory)
                if stage in ['proposal','implementation']:
                    body+=f'<p class="source-links"><a href="../recordings/{directory}/{stage}.md">Portable Markdown</a><a href="../recordings/{directory}/{stage}-response.txt">Exact response source</a></p>'
            panels.append(f'<section class="stage-panel" role="tabpanel" aria-labelledby="m{number}-{stage}-tab" id="m{number}-{stage}"><h2>{heading}</h2>{body}</section>')
        articles.append(f'<article class="milestone" id="m{number}"><header class="milestone-heading"><p class="eyebrow">Milestone 0{number}</p><h1>{escape(title)}</h1><p>{escape(subtitle)}</p><div class="checkpoint"><span>{checkpoint["tests"]["passed"]} tests passed</span><code>{commit[:7]}</code><a href="../recordings/{directory}/README.md">Markdown recording ↗</a></div></header><nav class="stage-tabs" role="tablist" aria-label="Milestone {number} recording stages">{tabs}</nav>'+''.join(panels)+'</article>')
    html=(HERE/'template.html').read_text().replace('{{NAVIGATION}}',''.join(navigation)).replace('{{ARTICLES}}',''.join(articles))
    (HERE/'index.html').write_text(html)
    print('Rendered offline walkthrough from all three recorded exchanges.')

if __name__=='__main__':render()
