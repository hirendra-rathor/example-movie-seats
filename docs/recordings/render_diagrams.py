"""Render the recorded proposal data as editable, self-contained SVG figures.

Usage: python docs/recordings/render_diagrams.py docs/recordings/01-holds
PNG exports are presentation copies; the SVG files are the editable originals.
"""
from html import escape
import json
from pathlib import Path
import sys
import textwrap

COLORS = {'new': '#16845b', 'changed': '#2563c9', 'context': '#7d8795', 'deleted': '#c83030'}

def lines(x, y, value, width=46, size=19, color='#14283f', bold=False):
    wrapped = textwrap.wrap(value, width, break_long_words=False) or ['']
    output = ''.join(f'<text x="{x}" y="{y+i*(size+7)}" font-family="Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(line)}</text>' for i,line in enumerate(wrapped))
    return output, len(wrapped)*(size+7)

def base(title, subtitle, width, height, statuses):
    out=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img"><title>{escape(title)}</title><desc>{escape(subtitle)}</desc><defs>'
    for status,color in COLORS.items():
        out+=f'<marker id="{status}" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="{color}"/></marker>'
    out+='</defs><rect width="100%" height="100%" fill="#f3f6fa"/>'
    out+=lines(50,45,title,100,28,bold=True)[0]+lines(50,82,subtitle,160,18)[0]
    for i,status in enumerate(statuses):
        x=width-120*(len(statuses)-i)-25
        out+=f'<rect x="{x}" y="20" width="108" height="30" rx="6" fill="{COLORS[status]}"/><text x="{x+54}" y="41" font-family="Arial" font-size="16" text-anchor="middle" fill="white">{status}</text>'
    return out

def card(node, x, y, w, h):
    status=node['status']; color=COLORS[status]
    out=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" stroke="{color}" stroke-width="3" fill="white"/>'
    out+=f'<rect x="{x+w-112}" y="{y-12}" width="100" height="27" rx="5" fill="{color}"/><text x="{x+w-62}" y="{y+7}" font-family="Arial" font-size="15" text-anchor="middle" fill="white">{status}</text>'
    cursor=y+34
    for value,size,color_,bold in [(node['title'],23,'#14283f',True),(node['facet'],15,'#435873',False)]:
        text,height=lines(x+20,cursor,value,int((w-40)/(size*.51)),size,color_,bold); out+=text; cursor+=height+5
    if node.get('today'):
        text,height=lines(x+20,cursor,'Today: '+node['today'],int((w-40)/9.8),19,'#586778');out+=text;cursor+=height+5
    value=('Proposed: ' if status!='context' else '')+node['detail']
    text,height=lines(x+20,cursor,value,int((w-40)/9.8),19);out+=text;cursor+=height
    if cursor>y+h-8: raise ValueError(f"Overflow in {node['id']}: {cursor-y}>{h}")
    return out

def edge(start,end,label,status='new',side=0):
    x,y,w,h=start;xx,yy,ww,hh=end;color=COLORS[status]
    if xx>x:
        x1,y1,x2,y2=x+w,y+h/2,xx,yy+hh/2
        route=f'M{x1},{y1} L{x2},{y2}'
        tx,ty=(x1+x2)/2,(y1+y2)/2-18
        text="".join(f'<text x="{tx}" y="{ty-(len(parts)-1-i)*16}" text-anchor="middle" font-family="Arial" font-size="13" fill="{color}">{escape(part)}</text>' for parts in [textwrap.wrap(label,10)] for i,part in enumerate(parts))
    elif xx==x:
        rail=x-16-side*19
        route=f'M{x},{y+h/2} H{rail} V{yy+hh/2} H{xx}'
        text=f'<text transform="translate({rail-5},{(y+yy+h)/2}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="14" fill="{color}">{escape(label)}</text>'
    else:
        # Collaboration uses explicitly placed vertical participants.
        route=f'M{x+w/2},{y+h} L{xx+ww/2},{yy}'
        text=lines((x+w/2+xx+ww/2)/2+10,(y+h+yy)/2,label,30,16,color)[0]
    return f'<path d="{route}" stroke="{color}" stroke-width="2.5" fill="none" marker-end="url(#{status})"/>'+text

def render(directory):
    data=json.loads((directory/'figures.json').read_text()); assets=directory/'assets';assets.mkdir(exist_ok=True)
    cols=data['columns']; n=max(map(len,cols));w=3360;h=200+n*310+100
    statuses=[s for s in COLORS if any(nod and nod['status']==s for col in cols for nod in col)]
    out=base(data['title']+' · Six perspectives',data['baseline']+' · Node and arrow colors compare the proposal with this baseline. Tests shown here are proposed.',w,h,statuses)
    headings=['Domain','Architecture','Subsystem Design','Subsystem Interfaces','State Management','Verification']
    pos={};cards=''
    for c,col in enumerate(cols):
        x=85+c*545
        out+=f'<rect x="{x-12}" y="115" width="494" height="{h-150}" rx="10" fill="{("#eaf0f7" if c%2==0 else "#edf2f7")}"/>'
        out+=lines(x,151,headings[c],30,25,bold=True)[0]
        for r,node in enumerate(col):
            if node is None: continue
            y=190+r*310;pos[node['id']]=(x,y,470,260);cards+=card(node,x,y,470,260)
    for e in data['links']:
        out+=edge(pos[e[0]],pos[e[1]],*e[2:])
    out+=cards
    out+=lines(65,h-42,data['summary'],200,19)[0]
    (assets/'overview.svg').write_text(out+'</svg>')
    nodes=data['collaboration']['nodes'];w,h=1900,1330
    statuses=[s for s in COLORS if any(nod['status']==s for nod in nodes)]
    out=base(data['title']+' · Collaboration',data['baseline']+' · Actual callers, decisions, transaction boundary and recovery.',w,h,statuses)
    pos={};cards=''
    for node in nodes:
        x,y,bw,bh=node['box'];pos[node['id']]=(x,y,bw,bh);cards+=card(node,x,y,bw,bh)
    for e in data['collaboration']['links']:
        out+=edge(pos[e[0]],pos[e[1]],*e[2:])
    out+=cards
    y=1030
    for note in data['collaboration']['notes']:
        text,height=lines(50,y,note,155,20);out+=text;y+=height+18
    (assets/'collaboration.svg').write_text(out+'</svg>')

if __name__=='__main__':
    render(Path(sys.argv[1]))
