// ResearchFlow Workbench（V1.0）— Host 半：同源路由 + 独立页面。
// 路由：
//   GET  /researchflow            → 独立实验工作台页面（浏览器直开）
//   GET  /researchflow/api/config → 插件配置（默认项目）
//   GET  /researchflow/api/tree?project=…  → rf report --data --json
//   POST /researchflow/api/decide {project,node,pass,comment}
//   POST /researchflow/api/run    {project,node|all,no_cache}
// 安全注记：监听仅 127.0.0.1；V1.0 接受同源页面直接调用，后续可加校验头。
import { execFile } from 'node:child_process'

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
body{margin:0;background:#0f1419;color:#d7e0ea;font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}
header{display:flex;gap:10px;align-items:center;padding:12px 18px;border-bottom:1px solid #2a3542;flex-wrap:wrap}
header h1{font-size:16px;margin:0 10px 0 0}
input{background:#171e26;border:1px solid #2a3542;color:#d7e0ea;border-radius:6px;padding:6px 10px;width:420px}
button{background:#1a2330;border:1px solid #4f9cf9;color:#d7e0ea;border-radius:6px;padding:6px 14px;cursor:pointer}
button.sub{border-color:#2a3542}
#hint{color:#8494a7;font-size:12px;padding:4px 18px}
#main{display:flex;gap:14px;padding:14px 18px;align-items:flex-start}
#treebox{flex:1;overflow:auto;background:#171e26;border:1px solid #2a3542;border-radius:8px}
#detail{width:360px;flex:none;background:#171e26;border:1px solid #2a3542;border-radius:8px;padding:14px;font-size:13px;max-height:82vh;overflow:auto}
.kv{display:grid;grid-template-columns:92px 1fr;gap:2px 8px;word-break:break-all}
.k{color:#8494a7}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;color:#fff}
.node{cursor:pointer}.node rect{fill:#1c2733;stroke:#2a3542}.node polygon{fill:#26313f;stroke:#2a3542}
.node text{fill:#d7e0ea;font-size:12px;pointer-events:none}.node .sub{fill:#8494a7;font-size:10px}
.node:hover rect,.node:hover polygon{stroke:#4f9cf9}
.edge{stroke:#3b4a5c;fill:none;stroke-width:1.5}.edge.gate{stroke:#fb8c00;stroke-dasharray:5,4}
.elabel{fill:#fb8c00;font-size:10px}
.empty{color:#8494a7;padding:20px;text-align:center}
h3{font-size:13px;color:#8494a7;margin:12px 0 4px}
</style>
</head>
<body>
<header>
  <h1>ResearchFlow 实验工作台</h1>
  <input id="project" placeholder="项目目录（含 researchflow.yaml）">
  <button id="reload">刷新</button>
  <button id="runall" class="sub">全部运行</button>
</header>
<div id="hint"></div>
<div id="main"><div id="treebox"><svg id="tree"></svg></div><aside id="detail"><div class="empty">点击节点查看详情</div></aside></div>
<script>
var DATA = null, STATUS_COLOR = {validated:"#34a853",completed:"#34a853",passed:"#34a853",
  failed:"#ea4335",failed_validation:"#ea4335",rejected:"#ea4335",interrupted:"#ea4335",
  awaiting:"#fb8c00",running:"#fb8c00",planned:"#5f7285"};
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function fmt(v){return v==null?"—":(typeof v==="number"?(Number.isInteger(v)?v:v.toPrecision(6)):String(v))}
function project(){return document.getElementById("project").value.trim()}
function hint(t){document.getElementById("hint").textContent=t||""}
function api(path, body){
  if(body){return fetch(path,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)}).then(function(r){return r.json()})}
  return fetch(path).then(function(r){return r.json()})
}
function load(){
  var p = project(); if(!p){hint("请输入项目目录");return}
  hint("加载中…")
  api("/researchflow/api/tree?project="+encodeURIComponent(p)).then(function(d){
    if(d.error||d.ok===false){hint("加载失败："+(d.error||"未知错误"));return}
    DATA=d; hint(d.project+" · 更新于 "+d.generated_at+" · 节点 "+d.nodes.length+" · 决策 "+d.decisions.length)
    render(); 
  }).catch(function(e){hint("请求失败："+e)})
}
function render(){
  if(!DATA)return
  var c=DATA.canvas,W=c.width,H=c.height,NW=c.node_w,NH=c.node_h,pos={}
  DATA.nodes.forEach(function(n){pos[n.id]=n})
  var s='<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#3b4a5c"/></marker><marker id="arrg" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#fb8c00"/></marker></defs>'
  DATA.edges.forEach(function(e){var a=pos[e.from],b=pos[e.to];if(!a||!b)return
    var x1=a.x+NW/2,y1=a.y+NH,x2=b.x+NW/2,y2=b.y,my=(y1+y2)/2
    s+='<path class="edge'+(e.gate?' gate':'')+'" d="M'+x1+','+y1+' C'+x1+','+my+' '+x2+','+my+' '+x2+','+(y2-3)+'" marker-end="url(#'+(e.gate?'arrg':'arr')+')"/>'
    if(e.gate)s+='<text class="elabel" x="'+((x1+x2)/2+6)+'" y="'+my+'">on_'+e.gate+'</text>'})
  DATA.nodes.forEach(function(n){var color=STATUS_COLOR[n.status]||"#5f7285",cx=n.x+NW/2,cy=n.y+NH/2
    var shape=n.kind==="decision"?'<polygon points="'+cx+','+n.y+' '+(n.x+NW)+','+cy+' '+cx+','+(n.y+NH)+' '+n.x+','+cy+'"/>':'<rect x="'+n.x+'" y="'+n.y+'" width="'+NW+'" height="'+NH+'" rx="8"/>'
    s+='<g class="node" data-id="'+esc(n.id)+'">'+shape+'<circle cx="'+(n.x+12)+'" cy="'+(n.y+12)+'" r="4" fill="'+color+'"/><text x="'+cx+'" y="'+(cy-4)+'" text-anchor="middle">'+esc(n.id)+'</text><text class="sub" x="'+cx+'" y="'+(cy+13)+'" text-anchor="middle">'+esc(n.kind==="decision"?"decision":n.block)+'</text></g>'})
  var tree=document.getElementById("tree");tree.setAttribute("width",W);tree.setAttribute("height",H);tree.innerHTML=s
}
document.getElementById("tree").addEventListener("click",function(ev){
  var g=ev.target.closest?ev.target.closest(".node"):null;if(g)detail(g.getAttribute("data-id"))
})
function detail(id){
  if(!DATA)return
  var n=DATA.nodes.filter(function(x){return x.id===id})[0];if(!n)return
  var h='<h2 style="font-size:15px">'+esc(n.id)+' <span class="badge" style="background:'+(STATUS_COLOR[n.status]||"#5f7285")+'">'+esc(n.status)+'</span></h2><div class="kv">'
  if(n.title)h+='<span class="k">标题</span><span>'+esc(n.title)+'</span>'
  h+='<span class="k">类型</span><span>'+esc(n.kind)+'</span>'
  if(n.block)h+='<span class="k">积木</span><span>'+esc(n.block)+'</span>'
  h+='</div>'
  if(n.kind==="decision"&&n.status==="awaiting"){
    h+='<h3>决策</h3><button onclick="decide(\''+esc(id)+'\',true)">通过 PASS</button> <button class="sub" onclick="decide(\''+esc(id)+'\',false)">驳回 FAIL</button>'
  }
  if(n.kind==="execution"){
    h+='<h3>操作</h3><button class="sub" onclick="runNode(\''+esc(id)+'\')">运行此节点</button>'
  }
  if(n.run){var r=n.run
    h+='<h3>最新运行</h3><div class="kv"><span class="k">run_id</span><span>'+esc(r.run_id)+'</span><span class="k">开始</span><span>'+esc(r.started_at||"—")+'</span><span class="k">耗时</span><span>'+fmt(r.duration_s)+' s</span>'
    if(r.error)h+='<span class="k">错误</span><span>'+esc(r.error)+'</span>'
    h+='</div>'
    if(Object.keys(r.metrics).length){h+='<h3>指标</h3><div class="kv">'
      for(var k in r.metrics)h+='<span class="k">'+esc(k)+'</span><span>'+fmt(r.metrics[k])+'</span>'
      h+='</div>'}
    if(r.validations.length){h+='<h3>验证</h3><div class="kv">'
      r.validations.forEach(function(v){h+='<span class="k">'+(v.passed?"✓":"✗")+' '+esc(v.name)+'</span><span>'+esc(v.detail||"")+'</span>'})
      h+='</div>'}
    if(r.artifacts.length){h+='<h3>产物</h3><div class="kv">'
      r.artifacts.forEach(function(a){h+='<span class="k">'+esc(a.port)+'</span><span>'+esc(a.path)+'<br><small>'+esc(a.type)+' · '+esc(a.sha256)+'…</small></span>'})
      h+='</div>'}
  } else if(n.kind==="execution"){h+='<div class="empty">尚无运行记录</div>'}
  document.getElementById("detail").innerHTML=h
}
function decide(id,pass){
  var comment=window.prompt("决策备注（可空）","")||""
  api("/researchflow/api/decide",{project:project(),node:id,pass:pass,comment:comment}).then(function(d){load()})
}
function runNode(id){hint("运行 "+id+" …");api("/researchflow/api/run",{project:project(),node:id}).then(function(d){load()})}
document.getElementById("reload").onclick=load
document.getElementById("runall").onclick=function(){hint("运行整棵树…");api("/researchflow/api/run",{project:project(),all:true}).then(function(d){load()})}
document.getElementById("project").onchange=function(){localStorage.setItem("rf_project",project());load()}
api("/researchflow/api/config").then(function(c){
  var saved=localStorage.getItem("rf_project")
  document.getElementById("project").value=saved||c.defaultProject||""
  if(document.getElementById("project").value)load()
})
setInterval(function(){if(DATA&&!document.hidden)load()},8000)
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
