// ResearchFlow Workbench（V1.0）— Host 半：同源路由 + 独立工作台页面。
// 路由：
//   GET  /researchflow            → 五标签实验工作台（浏览器直开）
//   GET  /researchflow/api/config → 插件配置（默认项目）
//   GET  /researchflow/api/tree?project=…  → rf report --data --json
//   GET  /researchflow/api/run_show?project&run_id → rf runs show --json
//   GET  /researchflow/api/artifact?project&run_id&port → Registry 产物字节流
//   POST /researchflow/api/decide {project,node,pass,comment}
//   POST /researchflow/api/run    {project,node|all,no_cache}
//   POST /researchflow/api/export {project,nodes,out,verify}
// 安全注记：监听仅 127.0.0.1；V1.0 接受同源页面直接调用，公网部署需补鉴权。
import { execFile } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

export const inject = ['webServer']

function rf(config, args, timeoutMs) {
  return new Promise((resolve) => {
    execFile(config.pythonPath || 'python', ['-m', 'researchflow', ...args], {
      timeout: timeoutMs || 2 * 60 * 1000,
      maxBuffer: 32 * 1024 * 1024,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    }, (error, stdout, stderr) => {
      if (stdout) {
        try { resolve(JSON.parse(stdout)); return } catch { /* fallthrough */ }
      }
      resolve({
        ok: false,
        error: error ? String(error.message || error) : 'rf CLI 未返回 JSON',
        stderr: String(stderr || '').slice(-2000) || undefined,
      })
    })
  })
}

function sendJson(res, code, obj) {
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  res.end(JSON.stringify(obj))
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    req.on('data', (c) => chunks.push(c))
    req.on('end', () => {
      try { resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf-8')) : {}) }
      catch (e) { reject(e) }
    })
    req.on('error', reject)
  })
}

const PAGE = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ResearchFlow 实验工作台</title>
<style>
:root{--bg:#0f1419;--panel:#171e26;--panel2:#1c2733;--border:#2a3542;--fg:#d7e0ea;--dim:#8494a7;
--ok:#34a853;--bad:#ea4335;--wait:#fb8c00;--todo:#5f7285;--accent:#4f9cf9}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}
header{display:flex;gap:8px;align-items:center;padding:10px 18px;border-bottom:1px solid var(--border);flex-wrap:wrap}
header h1{font-size:15px;display:flex;align-items:center;gap:8px;margin-right:8px}
input,select{background:var(--panel);border:1px solid var(--border);color:var(--fg);border-radius:6px;padding:5px 9px;font-size:13px}
input:focus,select:focus{outline:none;border-color:var(--accent)}
button{background:var(--panel);border:1px solid var(--border);color:var(--fg);border-radius:6px;padding:5px 12px;cursor:pointer;font-size:13px}
button:hover{border-color:var(--accent)}
button.primary{border-color:var(--accent);background:#1a2330}
button:disabled{opacity:.5;cursor:default}
nav{display:flex;gap:4px;padding:6px 18px;border-bottom:1px solid var(--border)}
nav button{border:1px solid transparent;color:var(--dim);background:none}
nav button.active{color:var(--fg);border-color:var(--accent);background:#1a2330}
section{display:none;padding:14px 18px}
section.active{display:block}
#hint{color:var(--dim);font-size:12px;padding:2px 18px}
#hint .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--ok);margin-right:6px}
.toolbar{display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--dim);border:1px solid var(--border);border-radius:10px;padding:1px 8px}
.chip i{width:8px;height:8px;border-radius:50%;display:inline-block}
#treewrap{display:flex;gap:14px;align-items:flex-start}
#treebox{flex:1;overflow:auto;background:var(--panel);border:1px solid var(--border);border-radius:8px;max-height:78vh}
#treebox svg{transform-origin:0 0}
#detail{width:380px;flex:none;background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:14px;font-size:13px;max-height:78vh;overflow:auto}
.kv{display:grid;grid-template-columns:92px 1fr;gap:2px 8px;word-break:break-all}
.k{color:var(--dim)}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;color:#fff}
.node{cursor:pointer}.node rect{fill:var(--panel2);stroke:var(--border)}.node polygon{fill:#26313f;stroke:var(--border)}
.node text{fill:var(--fg);font-size:12px;pointer-events:none}.node .sub{fill:var(--dim);font-size:10px}
.node:hover rect,.node:hover polygon{stroke:var(--accent)}
.node.sel rect,.node.sel polygon{stroke:var(--accent);stroke-width:2}
.edge{stroke:#3b4a5c;fill:none;stroke-width:1.5}.edge.gate{stroke:var(--wait);stroke-dasharray:5,4}
.elabel{fill:var(--wait);font-size:10px}
.empty{color:var(--dim);padding:24px;text-align:center}
h3{font-size:13px;color:var(--dim);margin:12px 0 4px}
table{border-collapse:collapse;width:100%;font-size:13px;background:var(--panel);border-radius:8px;overflow:hidden}
th,td{border:1px solid var(--border);padding:6px 10px;text-align:left}
th{background:#1a2330;color:var(--dim);font-weight:500}
td.num{font-variant-numeric:tabular-nums}
tr.clickable{cursor:pointer}tr.clickable:hover td{background:#1c2733}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px}
.card h4{font-size:13px;margin-bottom:8px;font-weight:500}
.card img{width:100%;border-radius:4px;background:#fff;cursor:zoom-in}
#toast{position:fixed;right:18px;bottom:18px;z-index:99;display:flex;flex-direction:column;gap:8px}
.toast{background:var(--panel);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:6px;padding:10px 14px;max-width:420px;font-size:13px;box-shadow:0 4px 16px rgba(0,0,0,.4)}
.toast.err{border-left-color:var(--bad)}
#modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:98}
#modal.open{display:flex}
#modalbox{background:var(--bg);border:1px solid var(--border);border-radius:10px;width:min(760px,92vw);max-height:84vh;overflow:auto;padding:18px;position:relative}
#modalx{position:absolute;right:12px;top:8px;border:none;background:none;color:var(--dim);font-size:20px;cursor:pointer}
pre{background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:10px;font-size:12px;overflow:auto;max-height:300px}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--dim);border-top-color:transparent;border-radius:50%;animation:sp .7s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes sp{to{transform:rotate(360deg)}}
.decidebar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.decidebar input{flex:1;min-width:160px}
a{color:var(--accent)}
</style>
</head>
<body>
<header>
  <h1><svg width="20" height="20" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#17324f"/><circle cx="20" cy="18" r="6" fill="#4f9cf9"/><circle cx="44" cy="18" r="6" fill="#34a853"/><path d="M20 24v6c0 4.4 3.6 6.4 12 8.4M44 24v6c0 4.4-3.6 6.4-12 8.4" stroke="#d7e0ea" stroke-width="3" fill="none" stroke-linecap="round"/><polygon points="32,36 41,44 32,52 23,44" fill="#fb8c00"/></svg>ResearchFlow 实验工作台</h1>
  <input id="project" placeholder="项目目录（含 researchflow.yaml）" style="width:380px">
  <button id="reload" class="primary">刷新</button>
  <button id="runall">全部运行</button>
  <button id="exportbtn">导出复现包</button>
</header>
<div id="hint"></div>
<nav id="tabs">
  <button data-tab="tree" class="active">实验树</button>
  <button data-tab="metrics">指标对照</button>
  <button data-tab="figures">图表</button>
  <button data-tab="runs">运行记录</button>
  <button data-tab="decisions">决策记录</button>
</nav>

<section id="tab-tree" class="active">
  <div class="toolbar">
    <span class="chip"><i style="background:var(--ok)"></i>validated / passed</span>
    <span class="chip"><i style="background:var(--bad)"></i>failed / rejected</span>
    <span class="chip"><i style="background:var(--wait)"></i>awaiting / running</span>
    <span class="chip"><i style="background:var(--todo)"></i>planned</span>
    <span style="flex:1"></span>
    <button id="zoomout">−</button><button id="zoomin">＋</button><button id="zoomreset">复位</button>
  </div>
  <div id="treewrap">
    <div id="treebox"><svg id="tree"></svg></div>
    <aside id="detail"><div class="empty">点击节点查看详情与操作</div></aside>
  </div>
</section>
<section id="tab-metrics"><div class="toolbar">基线：<select id="baseline"></select></div><div id="metricstable"></div></section>
<section id="tab-figures"><div class="cards" id="figurecards"></div></section>
<section id="tab-runs"><div id="runstable"></div></section>
<section id="tab-decisions"><div id="decisionstable"></div></section>

<div id="modal"><div id="modalbox"><button id="modalx">×</button><div id="modalcontent"></div></div></div>
<div id="toast"></div>

<script>
var DATA=null,SELECTED=null,ZOOM=1,POLL=null;
var STATUS_COLOR={validated:"#34a853",completed:"#34a853",passed:"#34a853",
  failed:"#ea4335",failed_validation:"#ea4335",rejected:"#ea4335",interrupted:"#ea4335",
  awaiting:"#fb8c00",running:"#fb8c00",planned:"#5f7285"};
var EXIT_TEXT={0:"成功",2:"契约/校验失败（请先修 plan 或参数）",3:"运行/验证失败（看运行记录与日志）",4:"等待人工审批或决策"};
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function fmt(v){return v==null?"—":(typeof v==="number"?(Number.isInteger(v)?v:v.toPrecision(6)):String(v))}
function project(){return document.getElementById("project").value.trim()}
function hint(t,ok){var d=document.getElementById("hint");d.innerHTML=t?('<span class="dot" style="background:'+(ok===false?"var(--bad)":"var(--ok)")+'"></span>'+esc(t)):""}
function toast(msg,isErr){var t=document.createElement("div");t.className="toast"+(isErr?" err":"");t.textContent=msg;document.getElementById("toast").appendChild(t);setTimeout(function(){t.remove()},6000)}
function api(path,body){
  if(body)return fetch(path,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)}).then(function(r){return r.json()});
  return fetch(path).then(function(r){return r.json()})
}
function checkErr(d,what){
  if(d&&(d.error||d.ok===false)){
    var code=typeof d.exit_code==="number"?d.exit_code:null;
    toast(what+"失败："+(d.error||"未知错误")+(code!=null&&EXIT_TEXT[code]?"（"+EXIT_TEXT[code]+"）":""),true);
    return true;
  }return false;
}
function load(){
  var p=project();if(!p){hint("请输入项目目录",false);return}
  api("/researchflow/api/tree?project="+encodeURIComponent(p)).then(function(d){
    if(checkErr(d,"加载"))return;
    DATA=d;hint(d.project+" · 更新于 "+d.generated_at+" · 节点 "+d.nodes.length+" · 决策 "+d.decisions.length);
    renderTree();renderMetrics();renderFigures();renderRuns();renderDecisions();
    if(SELECTED)renderDetail(SELECTED);
  }).catch(function(e){hint("请求失败："+e,false)});
}
// ---------- 实验树 ----------
function renderTree(){
  if(!DATA)return;
  var c=DATA.canvas,NW=c.node_w,NH=c.node_h,pos={};
  DATA.nodes.forEach(function(n){pos[n.id]=n});
  var s='<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#3b4a5c"/></marker><marker id="arrg" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#fb8c00"/></marker></defs>';
  DATA.edges.forEach(function(e){var a=pos[e.from],b=pos[e.to];if(!a||!b)return;
    var x1=a.x+NW/2,y1=a.y+NH,x2=b.x+NW/2,y2=b.y,my=(y1+y2)/2;
    s+='<path class="edge'+(e.gate?' gate':'')+'" d="M'+x1+','+y1+' C'+x1+','+my+' '+x2+','+my+' '+x2+','+(y2-3)+'" marker-end="url(#'+(e.gate?'arrg':'arr')+')"/>';
    if(e.gate)s+='<text class="elabel" x="'+((x1+x2)/2+6)+'" y="'+my+'">on_'+e.gate+'</text>'});
  DATA.nodes.forEach(function(n){var color=STATUS_COLOR[n.status]||"#5f7285",cx=n.x+NW/2,cy=n.y+NH/2;
    var shape=n.kind==="decision"?'<polygon points="'+cx+','+n.y+' '+(n.x+NW)+','+cy+' '+cx+','+(n.y+NH)+' '+n.x+','+cy+'"/>':'<rect x="'+n.x+'" y="'+n.y+'" width="'+NW+'" height="'+NH+'" rx="8"/>';
    s+='<g class="node'+(n.id===SELECTED?' sel':'')+'" data-id="'+esc(n.id)+'">'+shape+'<circle cx="'+(n.x+12)+'" cy="'+(n.y+12)+'" r="4" fill="'+color+'"/><text x="'+cx+'" y="'+(cy-4)+'" text-anchor="middle">'+esc(n.id)+'</text><text class="sub" x="'+cx+'" y="'+(cy+13)+'" text-anchor="middle">'+esc(n.kind==="decision"?"decision":n.block)+'</text></g>'});
  var tree=document.getElementById("tree");
  tree.setAttribute("width",c.width);tree.setAttribute("height",c.height);tree.innerHTML=s;
  applyZoom();
}
function applyZoom(){document.getElementById("tree").style.transform="scale("+ZOOM+")"}
document.getElementById("zoomin").onclick=function(){ZOOM=Math.min(2.5,ZOOM*1.2);applyZoom()};
document.getElementById("zoomout").onclick=function(){ZOOM=Math.max(0.3,ZOOM/1.2);applyZoom()};
document.getElementById("zoomreset").onclick=function(){ZOOM=1;applyZoom()};
document.getElementById("tree").addEventListener("click",function(ev){
  var g=ev.target.closest?ev.target.closest(".node"):null;
  if(g){SELECTED=g.getAttribute("data-id");renderTree();renderDetail(SELECTED)}
});
function artifactUrl(runId,port){return "/researchflow/api/artifact?project="+encodeURIComponent(project())+"&run_id="+encodeURIComponent(runId)+"&port="+encodeURIComponent(port)}
function renderDetail(id){
  var n=DATA.nodes.filter(function(x){return x.id===id})[0];if(!n)return;
  var h='<h2 style="font-size:15px;margin-bottom:6px">'+esc(n.id)+' <span class="badge" style="background:'+(STATUS_COLOR[n.status]||"#5f7285")+'">'+esc(n.status)+'</span></h2><div class="kv">';
  if(n.title)h+='<span class="k">标题</span><span>'+esc(n.title)+'</span>';
  h+='<span class="k">类型</span><span>'+esc(n.kind)+'</span>';
  if(n.block)h+='<span class="k">积木</span><span>'+esc(n.block)+'</span>';
  h+='</div>';
  if(n.kind==="decision"&&n.status==="awaiting"){
    h+='<h3>决策（写决策记录，含决策者与时间）</h3><div class="decidebar"><input id="dcomment" placeholder="决策备注（可空）"><button class="primary" onclick="decide(\\''+esc(id)+'\\',true)">通过 PASS</button><button onclick="decide(\\''+esc(id)+'\\',false)">驳回 FAIL</button></div>';
  }
  if(n.kind==="execution"){
    h+='<h3>操作</h3><button id="runbtn" onclick="runNode(\\''+esc(id)+'\\')">运行此节点</button>';
  }
  if(n.run){var r=n.run;
    h+='<h3>最新运行</h3><div class="kv"><span class="k">run_id</span><span><a href="javascript:runModal(\\''+esc(r.run_id)+'\\')">'+esc(r.run_id)+'</a></span><span class="k">开始</span><span>'+esc(r.started_at||"—")+'</span><span class="k">耗时</span><span>'+fmt(r.duration_s)+' s</span>';
    if(r.error)h+='<span class="k">错误</span><span>'+esc(r.error)+'</span>';
    h+='</div>';
    if(Object.keys(r.metrics).length){h+='<h3>指标</h3><div class="kv">';
      for(var k in r.metrics)h+='<span class="k">'+esc(k)+'</span><span class="num">'+fmt(r.metrics[k])+'</span>';
      h+='</div>'}
    if(r.validations.length){h+='<h3>验证</h3><div class="kv">';
      r.validations.forEach(function(v){h+='<span class="k">'+(v.passed?"✓":"✗")+' '+esc(v.name)+'</span><span>'+esc(v.detail||"")+'</span>'});
      h+='</div>'}
    if(r.artifacts.length){h+='<h3>产物</h3><div class="kv">';
      r.artifacts.forEach(function(a){h+='<span class="k">'+esc(a.port)+'</span><span><a href="'+artifactUrl(r.run_id,a.port)+'" target="_blank">'+esc(a.path)+'</a><br><small>'+esc(a.type)+' · '+esc(a.sha256)+'…</small></span>'});
      h+='</div>'}
  } else if(n.kind==="execution"){h+='<div class="empty">尚无运行记录</div>'}
  document.getElementById("detail").innerHTML=h;
}
function decide(id,pass){
  var c=document.getElementById("dcomment");
  api("/researchflow/api/decide",{project:project(),node:id,pass:pass,comment:c?c.value:""}).then(function(d){
    if(!checkErr(d,"决策"))toast("决策已记录："+id+" → "+(pass?"PASS":"FAIL"));
    load();
  });
}
function runNode(id){
  var b=document.getElementById("runbtn");if(b){b.disabled=true;b.innerHTML='<span class="spin"></span>运行中'}
  api("/researchflow/api/run",{project:project(),node:id}).then(function(d){
    if(!checkErr(d,"运行"))toast("运行完成："+id);
    load();
  });
}
// ---------- 指标对照 ----------
function renderMetrics(){
  var sel=document.getElementById("baseline"),tb=document.getElementById("metricstable");
  if(!DATA.metric_rows.length){tb.innerHTML='<div class="empty">暂无指标</div>';return}
  var rows=DATA.metric_rows,names=DATA.metric_names;
  var keep=sel.value;
  sel.innerHTML=rows.map(function(r){return '<option value="'+esc(r.node_id)+'">'+esc(r.node_id)+'（'+esc(r.run_id)+'）</option>'}).join("");
  if(keep&&rows.some(function(r){return r.node_id===keep}))sel.value=keep;
  var base=rows.filter(function(r){return r.node_id===sel.value})[0]||rows[0];
  var h='<table><tr><th>节点</th><th>run_id</th>';
  names.forEach(function(m){h+='<th>'+esc(m)+'</th>'});
  names.forEach(function(m){h+='<th>Δ'+esc(m)+'%</th>'});
  h+='</tr>';
  rows.forEach(function(r){
    h+='<tr class="clickable" onclick="gotoNode(\\''+esc(r.node_id)+'\\')"><td>'+esc(r.node_id)+'</td><td>'+esc(r.run_id)+'</td>';
    names.forEach(function(m){h+='<td class="num">'+fmt(r.metrics[m])+'</td>'});
    names.forEach(function(m){var v=r.metrics[m],bv=base.metrics[m];
      h+='<td class="num">'+((v==null||!bv||r.node_id===base.node_id)?"—":(((v-bv)/Math.abs(bv)*100).toFixed(2)+"%"))+'</td>'});
    h+='</tr>'});
  tb.innerHTML=h+'</table>';
}
document.getElementById("baseline").onchange=renderMetrics;
function gotoNode(id){document.querySelector('nav button[data-tab="tree"]').click();SELECTED=id;renderTree();renderDetail(id)}
// ---------- 图表 ----------
function renderFigures(){
  var box=document.getElementById("figurecards");
  if(!DATA.figures.length){box.innerHTML='<div class="empty">暂无图表（运行 visualize 积木后生成）</div>';return}
  box.innerHTML=DATA.figures.map(function(f){
    return '<div class="card"><h4>'+esc(f.node_id)+' · '+esc(f.name)+'<br><small>'+esc(f.run_id)+'</small></h4><img src="data:image/png;base64,'+f.data+'" onclick="window.open(artifactUrl(\\''+esc(f.run_id)+'\\',\\'figure\\'))"></div>';
  }).join("");
}
// ---------- 运行记录 ----------
function renderRuns(){
  var tb=document.getElementById("runstable");
  if(!DATA.runs.length){tb.innerHTML='<div class="empty">暂无运行</div>';return}
  var h='<table><tr><th>run_id</th><th>节点</th><th>状态</th><th>开始</th><th>结束</th></tr>';
  DATA.runs.forEach(function(r){
    h+='<tr class="clickable" onclick="runModal(\\''+esc(r.run_id)+'\\')"><td>'+esc(r.run_id)+'</td><td>'+esc(r.node_id)+'</td><td><span class="badge" style="background:'+(STATUS_COLOR[r.status]||"#5f7285")+'">'+esc(r.status)+'</span></td><td>'+esc(r.started_at||"—")+'</td><td>'+esc(r.finished_at||"—")+'</td></tr>'});
  tb.innerHTML=h+'</table>';
}
function runModal(runId){
  api("/researchflow/api/run_show?project="+encodeURIComponent(project())+"&run_id="+encodeURIComponent(runId)).then(function(d){
    if(checkErr(d,"读取运行"))return;
    var h='<h2 style="font-size:15px;margin-bottom:8px">'+esc(d.run_id||runId)+' <span class="badge" style="background:'+(STATUS_COLOR[d.status]||"#5f7285")+'">'+esc(d.status||"")+'</span></h2>';
    h+='<div class="kv"><span class="k">节点</span><span>'+esc(d.node_id)+'</span><span class="k">积木</span><span>'+esc(d.block&&d.block.id)+'@'+esc(d.block&&d.block.version)+'</span><span class="k">源码哈希</span><span>'+esc((d.block&&d.block.source_sha256||"").slice(0,16))+'…</span><span class="k">开始</span><span>'+esc(d.started_at)+'</span><span class="k">耗时</span><span>'+fmt(d.duration_s)+' s</span></div>';
    if(d.error)h+='<h3>错误</h3><pre>'+esc(d.error)+'</pre>';
    var ik=Object.keys(d.inputs||{});
    if(ik.length){h+='<h3>输入</h3><div class="kv">';ik.forEach(function(p){var r=d.inputs[p];h+='<span class="k">'+esc(p)+'</span><span>'+esc(r.path)+'<br><small>'+esc(r.sha256).slice(0,16)+'…</small></span>'});h+='</div>'}
    var ak=Object.keys(d.artifacts||{});
    if(ak.length){h+='<h3>产物</h3><div class="kv">';ak.forEach(function(p){var r=d.artifacts[p];h+='<span class="k">'+esc(p)+'</span><span><a href="'+artifactUrl(runId,p)+'" target="_blank">'+esc(r.path)+'</a><br><small>'+esc(r.type)+' · '+esc(r.sha256).slice(0,16)+'…</small></span>'});h+='</div>'}
    if((d.validations||[]).length){h+='<h3>验证</h3><div class="kv">';d.validations.forEach(function(v){h+='<span class="k">'+(v.passed?"✓":"✗")+' '+esc(v.name)+'</span><span>'+esc(v.detail||"")+'</span>'});h+='</div>'}
    var mk=Object.keys(d.metrics||{});
    if(mk.length){h+='<h3>指标</h3><div class="kv">';mk.forEach(function(k){h+='<span class="k">'+esc(k)+'</span><span class="num">'+fmt(d.metrics[k])+'</span>'});h+='</div>'}
    if(d.env){h+='<h3>环境</h3><div class="kv"><span class="k">python</span><span>'+esc(d.env.python)+'</span><span class="k">platform</span><span>'+esc(d.env.platform)+'</span><span class="k">core</span><span>'+esc(d.env.core_version)+'</span></div>'}
    h+='<h3>原始 run.json</h3><pre>'+esc(JSON.stringify(d,null,2))+'</pre>';
    document.getElementById("modalcontent").innerHTML=h;
    document.getElementById("modal").classList.add("open");
  });
}
document.getElementById("modalx").onclick=function(){document.getElementById("modal").classList.remove("open")};
document.getElementById("modal").onclick=function(e){if(e.target===this)this.classList.remove("open")};
// ---------- 决策记录 ----------
function renderDecisions(){
  var tb=document.getElementById("decisionstable");
  if(!DATA.decisions.length){tb.innerHTML='<div class="empty">暂无决策</div>';return}
  var h='<table><tr><th>节点</th><th>结果</th><th>模式</th><th>判据</th><th>建议</th><th>决策者</th><th>备注</th><th>时间</th></tr>';
  DATA.decisions.forEach(function(d){
    var res=d.final_result?"PASS":"FAIL",sug=(d.auto_result==null?"—":(d.auto_result?"PASS":"FAIL"));
    h+='<tr class="clickable" onclick="gotoNode(\\''+esc(d.node_id)+'\\')"><td>'+esc(d.node_id)+'</td><td><span class="badge" style="background:'+(d.final_result?"var(--ok)":"var(--bad)")+'">'+res+'</span></td><td>'+esc(d.mode)+'</td><td>'+esc(d.expression||"—")+'</td><td>'+sug+'</td><td>'+esc(d.actor)+'</td><td>'+esc(d.comment||"")+'</td><td>'+esc(d.decided_at)+'</td></tr>'});
  tb.innerHTML=h+'</table>';
}
// ---------- 导出 ----------
document.getElementById("exportbtn").onclick=function(){
  if(!DATA){toast("请先加载项目",true);return}
  var evals=DATA.nodes.filter(function(n){return n.run&&Object.keys(n.run.metrics||{}).length>1}).map(function(n){return n.id});
  var h='<h2 style="font-size:15px;margin-bottom:10px">导出研究复现包</h2><div class="kv"><span class="k">节点</span><span><input id="enodes" style="width:100%" value="'+esc(evals.join(","))+'"></span><span class="k">目录</span><span><input id="eout" style="width:100%" value="'+esc(project()+'\\\\dist\\\\export')+'"></span><span class="k">verify</span><span><input id="everify" type="checkbox" checked> 在导出目录内重跑并比对指标</span></div><br><button class="primary" onclick="doExport()">开始导出</button>';
  document.getElementById("modalcontent").innerHTML=h;
  document.getElementById("modal").classList.add("open");
};
function doExport(){
  var nodes=document.getElementById("enodes").value,out=document.getElementById("eout").value,verify=document.getElementById("everify").checked;
  document.getElementById("modal").classList.remove("open");
  toast("导出中（verify 会重跑实验链，请稍候）…");
  api("/researchflow/api/export",{project:project(),nodes:nodes,out:out,verify:verify}).then(function(d){
    if(checkErr(d,"导出"))return;
    toast("导出完成："+(d.out_dir||out)+(d.verified?"（verify ✓）":""));
  });
}
// ---------- 通用 ----------
document.querySelectorAll("#tabs button").forEach(function(b){b.onclick=function(){
  document.querySelectorAll("#tabs button").forEach(function(x){x.classList.toggle("active",x===b)});
  document.querySelectorAll("section").forEach(function(s){s.classList.toggle("active",s.id==="tab-"+b.dataset.tab)});
}});
document.getElementById("reload").onclick=load;
document.getElementById("runall").onclick=function(){
  this.disabled=true;this.innerHTML='<span class="spin"></span>运行中';var btn=this;
  api("/researchflow/api/run",{project:project(),all:true}).then(function(d){
    btn.disabled=false;btn.textContent="全部运行";
    if(!checkErr(d,"全部运行"))toast("整树运行完成");
    load();
  });
};
document.getElementById("project").onchange=function(){localStorage.setItem("rf_project",project());DATA=null;SELECTED=null;load()};
api("/researchflow/api/config").then(function(c){
  var saved=localStorage.getItem("rf_project");
  document.getElementById("project").value=saved||c.defaultProject||"";
  if(document.getElementById("project").value)load();
});
POLL=setInterval(function(){if(DATA&&!document.hidden)load()},8000);
</script>
</body>
</html>`

export function apply(ctx, config) {
  const cfg = { pythonPath: 'python', defaultProject: '', ...(config || {}) }
  const disposers = []

  disposers.push(ctx.webServer.register({
    kind: 'exact',
    path: '/researchflow',
    handler: (_req, res) => {
      res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' })
      res.end(PAGE)
    },
  }))

  disposers.push(ctx.webServer.register({
    kind: 'prefix',
    path: '/researchflow/api',
    handler: async (req, res) => {
      try {
        const url = new URL(req.url || '/', 'http://localhost')
        const sub = url.pathname.startsWith('/researchflow/api/')
          ? url.pathname.slice('/researchflow/api/'.length) : ''
        if (sub === 'config') {
          sendJson(res, 200, { defaultProject: cfg.defaultProject })
          return
        }
        if (sub === 'tree') {
          const project = url.searchParams.get('project') || cfg.defaultProject
          sendJson(res, 200, await rf(cfg, ['report', '--data', '--json', '-C', project]))
          return
        }
        if (sub === 'run_show') {
          const project = url.searchParams.get('project') || cfg.defaultProject
          const runId = url.searchParams.get('run_id') || ''
          sendJson(res, 200, await rf(cfg, ['runs', 'show', runId, '--json', '-C', project]))
          return
        }
        if (sub === 'artifact') {
          // 只按 Registry 记录解析产物（防路径穿越：绝不直接使用查询路径）
          const project = url.searchParams.get('project') || cfg.defaultProject
          const runId = url.searchParams.get('run_id') || ''
          const port = url.searchParams.get('port') || ''
          const show = await rf(cfg, ['runs', 'show', runId, '--json', '-C', project])
          const ref = show && show.artifacts && show.artifacts[port]
          if (!ref || typeof ref.path !== 'string' ||
              ref.path.includes('..') || path.isAbsolute(ref.path)) {
            sendJson(res, 400, { error: 'invalid artifact reference' })
            return
          }
          const file = path.resolve(project, ref.path)
          if (!file.startsWith(path.resolve(project)) || !fs.existsSync(file)) {
            sendJson(res, 404, { error: 'artifact not found' })
            return
          }
          const types = {
            '.png': 'image/png', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg',
            '.csv': 'text/csv; charset=utf-8', '.json': 'application/json; charset=utf-8',
          }
          res.writeHead(200, { 'content-type': types[path.extname(file)] || 'application/octet-stream' })
          fs.createReadStream(file).pipe(res)
          return
        }
        if (sub === 'decide' && req.method === 'POST') {
          const body = await readBody(req)
          const args = ['decide', body.node, body.pass ? '--pass' : '--fail', '--json',
            '-C', body.project || cfg.defaultProject]
          if (body.comment) args.push('--comment', body.comment)
          sendJson(res, 200, await rf(cfg, args))
          return
        }
        if (sub === 'run' && req.method === 'POST') {
          const body = await readBody(req)
          const args = ['run', ...(body.all ? ['--all'] : []), ...(body.node ? [body.node] : []),
            '--yes', '--json', '-C', body.project || cfg.defaultProject]
          if (body.no_cache) args.push('--no-cache')
          sendJson(res, 200, await rf(cfg, args, 30 * 60 * 1000))
          return
        }
        if (sub === 'export' && req.method === 'POST') {
          const body = await readBody(req)
          const args = ['export', '--nodes', body.nodes, '--out', body.out, '--json',
            '-C', body.project || cfg.defaultProject]
          if (body.verify) args.push('--verify')
          sendJson(res, 200, await rf(cfg, args, 30 * 60 * 1000))
          return
        }
        sendJson(res, 404, { error: 'not found' })
      } catch (e) {
        sendJson(res, 500, { error: String((e && e.message) || e) })
      }
    },
  }))

  const cleanup = () => disposers.forEach((dispose) => dispose())
  ctx.effect(() => cleanup)
  return cleanup
}
