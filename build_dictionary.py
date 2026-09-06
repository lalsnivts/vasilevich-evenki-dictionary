#!/usr/bin/env python3
"""
build_dictionary.py — turn MUDIDI stage-2 MDF output into a single
self-contained, searchable HTML dictionary.

Usage:
    python3 build_dictionary.py MDF_DIR [-o OUTPUT.html]

MDF_DIR is the folder containing per-page subfolders, each with a
`*.mdf.txt` file (the layout produced by MUDIDI stage 2). Pages are
merged in numeric order; every entry begins with \\lx.

The result is one HTML file with no external dependencies: embedded
data, client-side instant search (diacritic-insensitive), an А–Я
browse index, clickable `см.` cross-references, dialect-label
tooltips, and a light/dark theme. Open it directly or drop it on
GitHub Pages.

No third-party packages required (standard library only).
"""
import os, re, glob, json, argparse, sys

# ---------------------------------------------------------------------------
# Source citation shown in the page header. Edit here if you rebuild from a
# different edition.
# ---------------------------------------------------------------------------
TITLE = "Эвенкийско-русский словарь"
CITATION = ("Сост. Г. М. Василевич. — М.: Гос. изд-во иностранных и "
            "национальных словарей, 1958. — 576 с.")

# ---------------------------------------------------------------------------
# Abbreviation table (from the MUDIDI mdf_parsing_guide.json, extended).
# Shown as hover tooltips on \ps dialect/usage labels.
# ---------------------------------------------------------------------------
ABBR = {
  "мн.":"множественное число","ед.":"единственное число","3 л.":"3-е лицо ед. ч. наст. вр.",
  "букв.":"буквально","см.":"смотри (перекрёстная ссылка)","Ср.":"сравни",
  "межд.":"междометие","глаг.":"глагол","сущ.":"существительное","прил.":"прилагательное",
  "нареч.":"наречие","вин. п.":"винительный падеж","дат.-местн. п.":"дательно-местный падеж",
  "полит.":"политический термин","кого-л.":"кого-либо","что-л.":"что-либо","кому-л.":"кому-либо",
  "лингв.":"лингвистика","этн.":"этнография","эвф.":"эвфемизм","уст.":"устаревшее",
  "перен.":"переносное значение","собир.":"собирательное","усил.":"усилительное",
  "П-Т":"подкаменнотунгусский (литературный) говор","Як":"якутский","Сол":"солонский",
  "Нег":"негидальский","Ороч":"орочский","Орок":"орокский","Ульч":"ульчский",
  "Нан":"нанайский","Удэ":"удэгейский","Бур":"бурятский","Монг":"монгольский","Ман":"маньчжурский",
  "Эвсн":"эвенский",
}

# ---------------------------------------------------------------------------
# 1. Parse the MDF files into structured entries.
# ---------------------------------------------------------------------------
def page_num(path):
    m = re.search(r'page_(\d+)', os.path.basename(path))
    return int(m.group(1)) if m else 0

def read_records(MDF_DIR):
    files = sorted(glob.glob(os.path.join(MDF_DIR, "*", "*.mdf.txt")), key=page_num)
    if not files:
        # also try a flat directory of .mdf.txt files
        files = sorted(glob.glob(os.path.join(MDF_DIR, "*.mdf.txt")), key=page_num)
    if not files:
        sys.exit(f"No *.mdf.txt files found under {MDF_DIR!r}")
    records = []
    for f in files:
        pg = page_num(f)
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        cur = None
        for line in text.splitlines():
            if line.startswith("\\lx"):
                if cur is not None:
                    records.append(cur)
                cur = {"page": pg, "fields": []}
            if cur is None:
                continue
            m = re.match(r'\\([a-zA-Z-]+)\s?(.*)$', line)
            if m:
                cur["fields"].append([m.group(1), m.group(2).rstrip()])
            elif cur["fields"]:  # continuation line
                cur["fields"][-1][1] = (cur["fields"][-1][1] + " " + line.strip()).strip()
        if cur is not None:
            records.append(cur)
    return records, len(files)

def build_entry(rec):
    e = {"lx": None, "hm": None, "va": [], "ps": None, "page": rec["page"],
         "senses": [], "et": [], "eg": [], "mr": None, "notes": []}
    def new_sense(sn=None):
        return {"sn": sn, "gn": [], "ge": [], "un": [], "lt": [], "cf": [], "ex": []}
    cur_sense = None
    top = new_sense(None)
    for marker, val in rec["fields"]:
        if marker == "lx": e["lx"] = val
        elif marker == "hm": e["hm"] = val
        elif marker == "va": e["va"].append(val)
        elif marker == "ps":
            e["ps"] = val if e["ps"] is None else e["ps"] + "; " + val
        elif marker == "mr": e["mr"] = val
        elif marker == "sn":
            if cur_sense is not None: e["senses"].append(cur_sense)
            cur_sense = new_sense(val)
        elif marker in ("gn", "ge", "un", "lt", "cf"):
            (cur_sense or top)[marker].append(val)
        elif marker == "gv":
            (cur_sense or top)["gn"].append(val)
        elif marker == "xv":
            (cur_sense or top)["ex"].append({"xv": val, "xn": None})
        elif marker == "xn":
            tgt = (cur_sense or top)
            if tgt["ex"] and tgt["ex"][-1]["xn"] is None:
                tgt["ex"][-1]["xn"] = val
            else:
                tgt["ex"].append({"xv": None, "xn": val})
        elif marker == "et": e["et"].append(val)
        elif marker == "eg": e["eg"].append(val)
        elif marker in ("se", "xref"): top["cf"].append(val)
        else: e["notes"].append(f"{marker}: {val}")
    if cur_sense is not None: e["senses"].append(cur_sense)
    if not e["senses"]:
        if any(top[k] for k in ("gn","ge","un","lt","cf","ex")):
            e["senses"].append(top)
    elif any(top[k] for k in ("gn","ge","un","lt","cf","ex")):
        e["head_gloss"] = top
    return e

# ---------------------------------------------------------------------------
# 2. HTML template (data + abbreviations injected at the end).
#    Placeholders: __DATA__ __ABBR__ __TITLE__ __CITATION__ __COUNT__
# ---------------------------------------------------------------------------
HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{
    --paper:#f3efe6; --paper2:#ece6d9; --ink:#23201a; --ink-soft:#5a5346;
    --taiga:#3f5e46; --taiga-deep:#2b4531; --rubric:#9c3b2e; --line:#d8d0c0;
    --hi:#e8dcae; --shadow:rgba(40,34,22,.10);
  }
  :root[data-theme="dark"]{
    --paper:#181712; --paper2:#211f18; --ink:#e9e3d5; --ink-soft:#a49c8a;
    --taiga:#8fb08c; --taiga-deep:#a9c6a4; --rubric:#d98576; --line:#33302650;
    --hi:#4a4327; --shadow:rgba(0,0,0,.4);
  }
  @media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
    --paper:#181712; --paper2:#211f18; --ink:#e9e3d5; --ink-soft:#a49c8a;
    --taiga:#8fb08c; --taiga-deep:#a9c6a4; --rubric:#d98576; --line:#3330264d;
    --hi:#4a4327; --shadow:rgba(0,0,0,.4);
  }}
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{background:var(--paper);color:var(--ink);
    font-family:"PT Serif",Georgia,"Times New Roman",serif;
    font-size:18px;line-height:1.5;-webkit-font-smoothing:antialiased;}
  .wrap{max-width:820px;margin:0 auto;padding:0 20px 120px}
  header.top{position:sticky;top:0;z-index:20;background:var(--paper);
    border-bottom:1px solid var(--line);padding:14px 0 12px;margin-bottom:8px;}
  .titlerow{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
  h1{font-size:22px;font-weight:700;margin:0;letter-spacing:.2px}
  h1 .sub{color:var(--ink-soft);font-weight:400;font-size:15px;margin-left:8px}
  .cite{margin:6px 0 0;color:var(--ink-soft);font-size:13.5px;font-style:italic;line-height:1.35}
  .theme-btn{background:none;border:1px solid var(--line);color:var(--ink-soft);
    border-radius:4px;padding:4px 9px;cursor:pointer;font-family:inherit;font-size:13px;}
  .theme-btn:hover{color:var(--ink);border-color:var(--ink-soft)}
  .searchbox{position:relative;margin-top:12px}
  #q{width:100%;font-family:inherit;font-size:19px;color:var(--ink);
    background:var(--paper2);border:1px solid var(--line);border-radius:6px;
    padding:12px 44px 12px 14px;outline:none;}
  #q:focus{border-color:var(--taiga)}
  .clear{position:absolute;right:8px;top:50%;transform:translateY(-50%);
    border:none;background:none;color:var(--ink-soft);font-size:22px;cursor:pointer;
    line-height:1;padding:4px 8px;display:none}
  .controls{display:flex;gap:14px;align-items:center;margin-top:9px;flex-wrap:wrap;
    font-size:13px;color:var(--ink-soft)}
  .controls label{display:flex;align-items:center;gap:5px;cursor:pointer}
  .controls input[type=checkbox]{accent-color:var(--taiga)}
  .count{margin-left:auto;font-variant-numeric:tabular-nums}
  .scope{display:flex;gap:0;border:1px solid var(--line);border-radius:5px;overflow:hidden}
  .scope button{border:none;background:var(--paper2);color:var(--ink-soft);
    font-family:inherit;font-size:12.5px;padding:4px 10px;cursor:pointer}
  .scope button[aria-pressed=true]{background:var(--taiga);color:var(--paper)}
  .indexbar{display:flex;flex-wrap:wrap;gap:2px;margin-top:10px}
  .indexbar button{font-family:inherit;font-size:15px;min-width:28px;padding:3px 6px;
    border:1px solid var(--line);background:var(--paper2);color:var(--taiga-deep);
    border-radius:4px;cursor:pointer;font-weight:700;}
  .indexbar button:hover{background:var(--hi)}
  .indexbar button[aria-pressed=true]{background:var(--taiga);color:var(--paper);border-color:var(--taiga)}
  .indexbar button.hash{color:var(--ink-soft);font-weight:400}
  .browse-head{font-size:26px;font-weight:700;color:var(--rubric);
    padding:16px 0 4px;border-bottom:2px solid var(--line);margin-bottom:4px}
  .browse-cols{columns:2;column-gap:34px;padding-top:6px}
  .browse-cols a{display:block;break-inside:avoid;color:var(--taiga-deep);
    text-decoration:none;padding:2px 0;font-size:17px;border-bottom:1px solid transparent}
  .browse-cols a:hover{border-bottom-color:var(--taiga);color:var(--taiga)}
  .browse-cols a .bhm{color:var(--rubric);font-size:12px;vertical-align:super;margin-left:2px}
  .browse-cols a .bgloss{color:var(--ink-soft);font-size:14px;font-style:italic}
  @media(max-width:600px){.browse-cols{columns:1}}
  .entry{padding:15px 0 14px;border-bottom:1px solid var(--line);scroll-margin-top:150px}
  .entry:target{background:linear-gradient(90deg,var(--hi),transparent 65%);
    border-radius:4px;padding-left:10px;margin-left:-10px}
  .hw{font-size:21px;font-weight:700;color:var(--taiga-deep)}
  .hm{color:var(--rubric);font-weight:700;font-size:15px;vertical-align:super;margin-left:3px}
  .va{color:var(--ink-soft);font-style:italic;font-size:16px}
  .va::before{content:"вар. ";font-style:normal;font-size:12px;color:var(--ink-soft);opacity:.7}
  .ps{color:var(--ink-soft);font-style:italic;font-size:15px}
  .mr{color:var(--ink-soft);font-size:15px}
  .senses{margin-top:5px}
  .sense{margin:3px 0;padding-left:2px}
  .snnum{color:var(--rubric);font-weight:700;font-variant-numeric:tabular-nums;margin-right:5px}
  .gn{color:var(--ink)}
  .ge{color:var(--ink-soft);font-style:italic}
  .un{color:var(--ink-soft);font-size:15px}
  .lt{color:var(--ink-soft);font-size:15px}
  .lt::before{content:"букв. ";font-style:italic}
  .ex{margin:3px 0 3px 14px;font-size:16px}
  .xv{font-style:italic;color:var(--taiga-deep)}
  .xn{color:var(--ink-soft)}
  .xv::after{content:" — "}
  .cf{font-size:15px}
  .cf .cflabel{font-style:italic;color:var(--ink-soft)}
  a.ref{color:var(--taiga);text-decoration:none;border-bottom:1px dotted var(--taiga);cursor:pointer}
  a.ref:hover{background:var(--hi)}
  .et{margin-top:5px;font-size:15px;color:var(--ink-soft);
    border-left:2px solid var(--line);padding-left:9px}
  .page{float:right;color:var(--ink-soft);font-size:12px;opacity:.65;
    font-variant-numeric:tabular-nums}
  mark{background:var(--hi);color:inherit;border-radius:2px;padding:0 1px}
  abbr{border-bottom:1px dotted var(--ink-soft);cursor:help;text-decoration:none}
  .empty{text-align:center;color:var(--ink-soft);padding:60px 20px;font-size:17px}
  .empty b{color:var(--ink)}
  .sentinel{height:1px}
  .hint{color:var(--ink-soft);font-size:14px;text-align:center;padding:40px 0 10px}
  .kbd{font-family:inherit;border:1px solid var(--line);border-radius:3px;padding:0 5px;
    background:var(--paper2);font-size:13px}
  @media(max-width:600px){body{font-size:17px}.wrap{padding:0 14px 100px}
    h1{font-size:19px}.hw{font-size:20px}}
</style>
</head>
<body>
<header class="top">
  <div class="wrap" style="padding-bottom:0">
    <div class="titlerow">
      <h1>__TITLE__<span class="sub">__COUNT__ статей</span></h1>
      <button class="theme-btn" id="theme" title="Сменить тему">☾ тема</button>
    </div>
    <p class="cite">__CITATION__</p>
    <div class="searchbox">
      <input id="q" type="search" autocomplete="off" spellcheck="false"
             placeholder="Поиск слова, перевода, говора…" aria-label="Поиск">
      <button class="clear" id="clear" aria-label="Очистить">×</button>
    </div>
    <div class="controls">
      <div class="scope" role="group" aria-label="Область поиска">
        <button data-scope="all" aria-pressed="true">везде</button>
        <button data-scope="lx" aria-pressed="false">эвенкийский</button>
        <button data-scope="gn" aria-pressed="false">перевод</button>
        <button data-scope="ps" aria-pressed="false">говор/помета</button>
      </div>
      <label><input type="checkbox" id="starts"> с начала слова</label>
      <span class="count" id="count"></span>
    </div>
    <div class="indexbar" id="indexbar" role="group" aria-label="Алфавитный указатель"></div>
  </div>
</header>
<div class="wrap">
  <div id="results"></div>
  <div class="sentinel" id="sentinel"></div>
  <div class="hint" id="hint">
    Начните вводить запрос или выберите букву. Поиск идёт по заголовкам,
    переводам, примерам, этимологии и пометам. Нажмите <span class="kbd">/</span>
    для перехода к строке поиска.
  </div>
</div>
<script id="dict" type="application/json">__DATA__</script>
<script>
const ABBR = __ABBR__;
const DATA = JSON.parse(document.getElementById('dict').textContent);
function norm(s){
  if(!s) return "";
  s=s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  s=s.replace(/ā/g,'а').replace(/ō/g,'о').replace(/ē/g,'э')
     .replace(/ӣ/g,'и').replace(/ӯ/g,'у').replace(/ә/g,'э').replace(/ё/g,'е');
  return s;
}
const CYR_ORDER="АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ";
function firstLetter(lx){
  const s=(lx||'').trim();
  for(const ch of s){
    if(/[a-zа-яёā-ӿ]/i.test(ch)){
      const fold={'ā':'А','ō':'О','ē':'Э','ӣ':'И','ӯ':'У','ә':'Э'}[ch.toLowerCase()];
      if(fold) return fold;
      const base=ch.normalize('NFD')[0].toUpperCase();
      return CYR_ORDER.includes(base)?base:'#';
    }
  }
  return '#';
}
for(const e of DATA){
  e._L=firstLetter(e.lx);
  let gn=[],rest=[];
  for(const s of e.senses){
    for(const g of s.gn) gn.push(norm(g));
    for(const g of s.ge) rest.push(norm(g));
    for(const u of s.un) rest.push(norm(u));
    for(const l of s.lt) rest.push(norm(l));
    for(const x of s.ex){ if(x.xv)rest.push(norm(x.xv)); if(x.xn)rest.push(norm(x.xn)); }
    for(const c of s.cf) rest.push(norm(c));
  }
  for(const t of (e.et||[])) rest.push(norm(t));
  e._lx=norm(e.lx); e._va=(e.va||[]).map(norm).join(' ');
  e._gn=gn.join(' '); e._ps=norm(e.ps||'');
  e._all=[e._lx,e._va,e._gn,e._ps,rest.join(' ')].join(' ');
}
const LXMAP=new Map();
DATA.forEach((e,i)=>{ if(!LXMAP.has(e.lx)) LXMAP.set(e.lx,i); });
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function hl(s,q){
  if(!s) return ''; s=esc(s); if(!q) return s;
  const nq=norm(q); if(!nq) return s;
  const nn=norm(s); let out='',i=0;
  while(i<s.length){
    const idx=nn.indexOf(nq,i);
    if(idx<0){ out+=s.slice(i); break; }
    out+=s.slice(i,idx)+'<mark>'+s.slice(idx,idx+nq.length)+'</mark>';
    i=idx+nq.length;
  }
  return out;
}
function abbrify(s){
  if(!s) return '';
  return esc(s).split(/(,\s*|;\s*|\s+)/).map(tok=>{
    const key=tok.trim();
    if(ABBR[key]) return '<abbr title="'+esc(ABBR[key])+'">'+esc(tok)+'</abbr>';
    if(ABBR[key+'.']) return '<abbr title="'+esc(ABBR[key+'.'])+'">'+esc(tok)+'</abbr>';
    return esc(tok);
  }).join('');
}
function refLink(target){
  const base=target.replace(/\s+[IVX0-9]+\s*$/,'').trim();
  const id=LXMAP.has(target)?LXMAP.get(target):(LXMAP.has(base)?LXMAP.get(base):null);
  if(id!=null) return '<a class="ref" data-goto="'+id+'">'+esc(target)+'</a>';
  return esc(target);
}
function renderSense(s,q){
  let h='<div class="sense">';
  if(s.sn) h+='<span class="snnum">'+esc(s.sn)+')</span>';
  const g=[];
  s.gn.forEach(x=>g.push('<span class="gn">'+hl(x,q)+'</span>'));
  s.ge.forEach(x=>g.push('<span class="ge">'+hl(x,q)+'</span>'));
  h+=g.join('; ');
  s.un.forEach(u=>h+=' <span class="un">('+hl(u,q)+')</span>');
  s.lt.forEach(l=>h+=' <span class="lt">'+hl(l,q)+'</span>');
  s.cf.forEach(c=>h+=' <span class="cf"><span class="cflabel">см. </span>'+refLink(c)+'</span>');
  for(const x of s.ex){
    h+='<div class="ex">';
    if(x.xv) h+='<span class="xv">'+hl(x.xv,q)+'</span>';
    if(x.xn) h+='<span class="xn">'+hl(x.xn,q)+'</span>';
    h+='</div>';
  }
  return h+'</div>';
}
function renderEntry(e,q){
  let h='<article class="entry" id="e'+e.id+'">';
  h+='<span class="page" title="страница оригинала">с. '+e.page+'</span>';
  h+='<span class="hw">'+hl(e.lx,q)+'</span>';
  if(e.hm) h+='<span class="hm">'+esc(e.hm)+'</span>';
  (e.va||[]).forEach(v=>h+=' <span class="va">'+hl(v,q)+'</span>');
  if(e.ps) h+=' <span class="ps">'+abbrify(e.ps)+'</span>';
  if(e.mr) h+=' <span class="mr">'+esc(e.mr)+'</span>';
  if(e.head_gloss && (e.head_gloss.gn.length||e.head_gloss.cf.length))
    h+=renderSense(e.head_gloss,q);
  h+='<div class="senses">';
  for(const s of e.senses) h+=renderSense(s,q);
  h+='</div>';
  for(const t of (e.et||[])) h+='<div class="et">'+hl(t,q)+'</div>';
  for(const n of (e.notes||[])) h+='<div class="et">'+esc(n)+'</div>';
  return h+'</article>';
}
const qEl=document.getElementById('q'),resEl=document.getElementById('results'),
      countEl=document.getElementById('count'),hintEl=document.getElementById('hint'),
      clearEl=document.getElementById('clear'),sentinel=document.getElementById('sentinel'),
      indexbar=document.getElementById('indexbar');
let scope='all',starts=false,matches=[],shown=0,curQ='',browseLetter=null;
const PAGE=80;
const present=new Set(DATA.map(e=>e._L));
const letters=CYR_ORDER.split('').filter(l=>present.has(l));
if(present.has('#')) letters.push('#');
for(const L of letters){
  const b=document.createElement('button');
  b.textContent=L; if(L==='#'){b.className='hash';b.title='прочие';}
  b.setAttribute('aria-pressed','false');
  b.addEventListener('click',()=>toggleBrowse(L,b));
  indexbar.appendChild(b);
}
function clearIndexPressed(){indexbar.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed','false'));}
function toggleBrowse(L,btn){
  if(browseLetter===L){browseLetter=null;clearIndexPressed();
    resEl.innerHTML='';countEl.textContent='';hintEl.style.display='block';return;}
  browseLetter=L;qEl.value='';curQ='';clearEl.style.display='none';
  clearIndexPressed();btn.setAttribute('aria-pressed','true');hintEl.style.display='none';
  renderBrowse(L);window.scrollTo({top:0,behavior:'smooth'});
}
function renderBrowse(L){
  const list=DATA.filter(e=>e._L===L).sort((a,b)=>a._lx<b._lx?-1:a._lx>b._lx?1:(a.id-b.id));
  countEl.textContent=list.length.toLocaleString('ru')+' '+plural(list.length);
  let html='<div class="browse-head">'+(L==='#'?'Прочие':L)+'</div><div class="browse-cols">';
  for(const e of list){
    let g=''; const s=e.senses[0];
    if(s){ if(s.gn[0])g=s.gn[0]; else if(s.ge[0])g=s.ge[0]; }
    if(g.length>42) g=g.slice(0,40)+'…';
    html+='<a data-goto="'+e.id+'">'+esc(e.lx)+
      (e.hm?'<span class="bhm">'+esc(e.hm)+'</span>':'')+
      (g?' <span class="bgloss">'+esc(g)+'</span>':'')+'</a>';
  }
  resEl.innerHTML=html+'</div>';
}
function search(){
  const raw=qEl.value.trim(); curQ=raw;
  if(raw){browseLetter=null;clearIndexPressed();}
  clearEl.style.display=raw?'block':'none';
  const nq=norm(raw);
  if(!nq){matches=[];resEl.innerHTML='';countEl.textContent='';hintEl.style.display='block';return;}
  hintEl.style.display='none';
  const field=scope==='all'?'_all':scope==='lx'?'_lx':scope==='gn'?'_gn':'_ps';
  const res=[];
  for(const e of DATA){
    const hay=scope==='lx'?(e._lx+' '+e._va):e[field];
    if(hay.includes(nq)) res.push(e);
  }
  res.sort((a,b)=>{const ap=rank(a,nq),bp=rank(b,nq);
    return ap!==bp?ap-bp:(a._lx<b._lx?-1:a._lx>b._lx?1:0);});
  matches=res;shown=0;
  countEl.textContent=res.length?(res.length.toLocaleString('ru')+' '+plural(res.length)):'';
  resEl.innerHTML='';
  if(!res.length){
    resEl.innerHTML='<div class="empty">Ничего не найдено по запросу <b>'+esc(raw)+
      '</b>.<br>Попробуйте другое написание или уберите ограничение «с начала слова».</div>';
    return;
  }
  more();
}
function rank(e,nq){
  if(e._lx===nq) return 0;
  if(e._lx.startsWith(nq)) return 1;
  if((' '+e._lx).includes(' '+nq)) return 2;
  if(e._gn.startsWith(nq)) return 3;
  return 4;
}
function plural(n){
  const a=n%10,b=n%100;
  if(a===1&&b!==11) return 'статья';
  if(a>=2&&a<=4&&(b<10||b>=20)) return 'статьи';
  return 'статей';
}
function more(){
  const frag=matches.slice(shown,shown+PAGE);
  let html=''; for(const e of frag) html+=renderEntry(e,curQ);
  resEl.insertAdjacentHTML('beforeend',html); shown+=frag.length;
}
new IntersectionObserver(es=>{if(es[0].isIntersecting&&shown<matches.length)more();},
  {rootMargin:'600px'}).observe(sentinel);
let t; qEl.addEventListener('input',()=>{clearTimeout(t);t=setTimeout(search,110);});
clearEl.addEventListener('click',()=>{qEl.value='';qEl.focus();search();});
document.querySelectorAll('.scope button').forEach(b=>{
  b.addEventListener('click',()=>{
    document.querySelectorAll('.scope button').forEach(x=>x.setAttribute('aria-pressed','false'));
    b.setAttribute('aria-pressed','true');scope=b.dataset.scope;
    if(!browseLetter)search();
  });
});
document.getElementById('starts').addEventListener('change',e=>{starts=e.target.checked;
  // "starts" now handled inside search ranking; re-run search
  if(!browseLetter)search();});
resEl.addEventListener('click',ev=>{
  const a=ev.target.closest('[data-goto]'); if(!a)return;
  ev.preventDefault();
  const id=+a.dataset.goto,e=DATA[id]; if(!e)return;
  if(a.classList.contains('ref')){
    browseLetter=null;clearIndexPressed();
    qEl.value=e.lx;scope='all';
    document.querySelectorAll('.scope button').forEach(x=>x.setAttribute('aria-pressed',x.dataset.scope==='all'?'true':'false'));
    search();window.scrollTo({top:0,behavior:'smooth'});
  } else {
    hintEl.style.display='none';countEl.textContent='';
    resEl.innerHTML=renderEntry(e,'');window.scrollTo({top:0,behavior:'smooth'});
  }
});
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&document.activeElement!==qEl){e.preventDefault();qEl.focus();}
  if(e.key==='Escape'&&document.activeElement===qEl){qEl.value='';search();qEl.blur();}
});
const themeBtn=document.getElementById('theme'),root=document.documentElement;
function applyTheme(t){ if(t)root.setAttribute('data-theme',t); else root.removeAttribute('data-theme');
  themeBtn.textContent=(getComputedStyle(root).getPropertyValue('--paper').trim().startsWith('#1'))?'☀ тема':'☾ тема'; }
let saved=null; try{saved=localStorage.getItem('theme');}catch(e){}
applyTheme(saved);
themeBtn.addEventListener('click',()=>{
  const cur=root.getAttribute('data-theme');
  const next=cur==='dark'?'light':cur==='light'?'dark':
    (matchMedia('(prefers-color-scheme:dark)').matches?'light':'dark');
  applyTheme(next); try{localStorage.setItem('theme',next);}catch(e){}
});
qEl.focus();
</script>
</body>
</html>'''

def build(MDF_DIR, out_path):
    records, npages = read_records(MDF_DIR)
    entries = [build_entry(r) for r in records]
    entries = [e for e in entries if e["lx"]]
    for i, e in enumerate(entries):
        e["id"] = i
    data = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    html = (HTML_TEMPLATE
            .replace("__DATA__", data)
            .replace("__ABBR__", json.dumps(ABBR, ensure_ascii=False))
            .replace("__TITLE__", TITLE)
            .replace("__CITATION__", CITATION)
            .replace("__COUNT__", f"{len(entries):,}".replace(",", "\u00a0")))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Read {npages} pages -> {len(entries):,} entries")
    print(f"Wrote {out_path} ({os.path.getsize(out_path)/1024/1024:.2f} MB)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build a searchable HTML dictionary from MUDIDI stage-2 MDF output.")
    ap.add_argument("MDF_DIR", help="Directory containing per-page */*.mdf.txt files")
    ap.add_argument("-o", "--output", default="dictionary.html", help="Output HTML path (default: dictionary.html)")
    args = ap.parse_args()
    build(args.MDF_DIR, args.output)
