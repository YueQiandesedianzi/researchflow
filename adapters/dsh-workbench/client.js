// ResearchFlow Workbench — Client 半：shell.overlay 悬浮球 + 抽屉式实验树面板。
// 数据经同源 /researchflow/api/*（Host 半 → rf CLI）。样式用宿主主题 token。
window.__ModuleLoader__.load({
  id: '@researchflow/dsh-workbench',
  factory(require) {
    const React = require('react');
    const h = React.createElement;
    const STATUS_COLOR = {
      validated: '#34a853', completed: '#34a853', passed: '#34a853',
      failed: '#ea4335', failed_validation: '#ea4335', rejected: '#ea4335', interrupted: '#ea4335',
      awaiting: '#fb8c00', running: '#fb8c00', planned: '#5f7285',
    };
    const CSS = `
.rfw-fab{position:fixed;right:22px;bottom:86px;z-index:900;width:44px;height:44px;border-radius:50%;
  border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-overlay);cursor:pointer;
  display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(0,0,0,.35)}
.rfw-fab:hover{border-color:var(--dsw-alias-brand-primary)}
.rfw-drawer{position:fixed;top:0;right:0;bottom:0;width:min(680px,92vw);z-index:901;display:flex;flex-direction:column;
  background:var(--dsw-alias-bg-base);border-left:1px solid var(--dsw-alias-border-l1);box-shadow:-8px 0 24px rgba(0,0,0,.4)}
.rfw-head{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--dsw-alias-border-l1);flex-wrap:wrap}
.rfw-head b{font-size:14px;margin-right:auto}
.rfw-head input{flex:1;min-width:200px;background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);
  color:var(--dsw-alias-label-primary);border-radius:6px;padding:5px 9px;font-size:12px}
.rfw-btn{background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);color:var(--dsw-alias-label-primary);
  border-radius:6px;padding:5px 10px;cursor:pointer;font-size:12px}
.rfw-btn:hover{border-color:var(--dsw-alias-brand-primary)}
.rfw-btn.primary{border-color:var(--dsw-alias-brand-primary)}
.rfw-x{border:none;background:none;color:var(--dsw-alias-label-secondary);font-size:18px;cursor:pointer}
.rfw-hint{padding:4px 14px;font-size:11px;color:var(--dsw-alias-label-secondary)}
.rfw-main{flex:1;display:flex;min-height:0}
.rfw-tree{flex:1;overflow:auto;padding:10px}
.rfw-detail{width:300px;flex:none;overflow:auto;border-left:1px solid var(--dsw-alias-border-l1);padding:12px;font-size:12px}
.rfw-kv{display:grid;grid-template-columns:84px 1fr;gap:2px 8px;word-break:break-all;margin-bottom:8px}
.rfw-k{color:var(--dsw-alias-label-secondary)}
.rfw-badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;color:#fff}
.rfw-node{cursor:pointer}.rfw-node rect{fill:var(--dsw-alias-bg-layer-1);stroke:var(--dsw-alias-border-l1)}
.rfw-node polygon{fill:var(--dsw-alias-bg-layer-2);stroke:var(--dsw-alias-border-l1)}
.rfw-node text{fill:var(--dsw-alias-label-primary);font-size:12px;pointer-events:none}
.rfw-node .sub{fill:var(--dsw-alias-label-secondary);font-size:10px}
.rfw-node:hover rect,.rfw-node:hover polygon{stroke:var(--dsw-alias-brand-primary)}
.rfw-edge{stroke:var(--dsw-alias-border-l2);fill:none;stroke-width:1.5}
.rfw-edge.gate{stroke:#fb8c00;stroke-dasharray:5,4}
.rfw-elabel{fill:#fb8c00;font-size:10px}
.rfw-empty{color:var(--dsw-alias-label-secondary);padding:24px;text-align:center;font-size:12px}
.rfw-h3{font-size:12px;color:var(--dsw-alias-label-secondary);margin:10px 0 4px}
`;

    function TreeSvg(props) {
      const data = props.data;
      const c = data.canvas, NW = c.node_w, NH = c.node_h;
      const pos = {};
      data.nodes.forEach((n) => { pos[n.id] = n; });
      const edges = data.edges.map((e, i) => {
        const a = pos[e.from], b = pos[e.to];
        if (!a || !b) return null;
        const x1 = a.x + NW / 2, y1 = a.y + NH, x2 = b.x + NW / 2, y2 = b.y;
        const my = (y1 + y2) / 2;
        return h('g', { key: 'e' + i },
          h('path', {
            className: 'rfw-edge' + (e.gate ? ' gate' : ''),
            d: `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2 - 3}`,
            markerEnd: `url(#${e.gate ? 'rfw-arrg' : 'rfw-arr'})`,
          }),
          e.gate ? h('text', { className: 'rfw-elabel', x: (x1 + x2) / 2 + 6, y: my }, 'on_' + e.gate) : null);
      });
      const nodes = data.nodes.map((n) => {
        const color = STATUS_COLOR[n.status] || '#5f7285';
        const cx = n.x + NW / 2, cy = n.y + NH / 2;
        const shape = n.kind === 'decision'
          ? h('polygon', { points: `${cx},${n.y} ${n.x + NW},${cy} ${cx},${n.y + NH} ${n.x},${cy}` })
          : h('rect', { x: n.x, y: n.y, width: NW, height: NH, rx: 8 });
        return h('g', {
          key: n.id, className: 'rfw-node',
          onClick: () => props.onSelect(n.id),
        },
          shape,
          h('circle', { cx: n.x + 12, cy: n.y + 12, r: 4, fill: color }),
          h('text', { x: cx, y: cy - 4, textAnchor: 'middle' }, n.id),
          h('text', { className: 'sub', x: cx, y: cy + 13, textAnchor: 'middle' },
            n.kind === 'decision' ? 'decision' : n.block));
      });
      return h('svg', { width: c.width, height: c.height },
        h('defs', null,
          h('marker', { id: 'rfw-arr', markerWidth: 8, markerHeight: 8, refX: 7, refY: 3, orient: 'auto' },
            h('path', { d: 'M0,0 L7,3 L0,6 z', fill: '#3b4a5c' })),
          h('marker', { id: 'rfw-arrg', markerWidth: 8, markerHeight: 8, refX: 7, refY: 3, orient: 'auto' },
            h('path', { d: 'M0,0 L7,3 L0,6 z', fill: '#fb8c00' }))),
        edges, nodes);
    }

    function Kv(props) {
      return h('div', { className: 'rfw-kv' },
        h('span', { className: 'rfw-k' }, props.k), h('span', null, props.children));
    }

    function Detail(props) {
      const n = props.node;
      if (!n) return h('div', { className: 'rfw-empty' }, '点击节点查看详情');
      const rows = [];
      if (n.title) rows.push(h(Kv, { key: 't', k: '标题' }, n.title));
      rows.push(h(Kv, { key: 'k', k: '类型' }, n.kind));
      if (n.block) rows.push(h(Kv, { key: 'b', k: '积木' }, n.block));
      const parts = [
        h('div', { key: 'h' },
          h('b', null, n.id, ' '),
          h('span', { className: 'rfw-badge', style: { background: STATUS_COLOR[n.status] || '#5f7285' } }, n.status)),
        h('div', { key: 'kv', className: 'rfw-kv' }, rows),
      ];
      if (n.kind === 'decision' && n.status === 'awaiting') {
        parts.push(h('div', { key: 'dec' },
          h('div', { className: 'rfw-h3' }, '决策'),
          h('button', { className: 'rfw-btn primary', onClick: () => props.onDecide(n.id, true) }, '通过 PASS'),
          ' ',
          h('button', { className: 'rfw-btn', onClick: () => props.onDecide(n.id, false) }, '驳回 FAIL')));
      }
      if (n.kind === 'execution') {
        parts.push(h('div', { key: 'act' },
          h('div', { className: 'rfw-h3' }, '操作'),
          h('button', { className: 'rfw-btn', onClick: () => props.onRun(n.id) }, '运行此节点')));
      }
      if (n.run) {
        const r = n.run;
        parts.push(h('div', { key: 'run' },
          h('div', { className: 'rfw-h3' }, '最新运行'),
          h('div', { className: 'rfw-kv' },
            h('span', { className: 'rfw-k' }, 'run_id'), h('span', null, r.run_id),
            h('span', { className: 'rfw-k' }, '开始'), h('span', null, r.started_at || '—'),
            h('span', { className: 'rfw-k' }, '耗时'), h('span', null, `${r.duration_s ?? '—'} s`),
            r.error ? h('span', { className: 'rfw-k' }, '错误') : null,
            r.error ? h('span', null, r.error) : null)));
        const metrics = Object.entries(r.metrics || {});
        if (metrics.length) {
          parts.push(h('div', { key: 'm' },
            h('div', { className: 'rfw-h3' }, '指标'),
            h('div', { className: 'rfw-kv' },
              metrics.map(([k, v]) => [
                h('span', { key: k + 'k', className: 'rfw-k' }, k),
                h('span', { key: k + 'v' }, typeof v === 'number' ? v.toPrecision(6) : String(v)),
              ]))));
        }
        if ((r.validations || []).length) {
          parts.push(h('div', { key: 'v' },
            h('div', { className: 'rfw-h3' }, '验证'),
            h('div', { className: 'rfw-kv' },
              r.validations.map((v, i) => [
                h('span', { key: i + 'k', className: 'rfw-k' }, `${v.passed ? '✓' : '✗'} ${v.name}`),
                h('span', { key: i + 'v' }, v.detail || ''),
              ]))));
        }
        if ((r.artifacts || []).length) {
          parts.push(h('div', { key: 'a' },
            h('div', { className: 'rfw-h3' }, '产物'),
            h('div', { className: 'rfw-kv' },
              r.artifacts.map((a) => [
                h('span', { key: a.port + 'k', className: 'rfw-k' }, a.port),
                h('span', { key: a.port + 'v' }, `${a.path}（${a.type} · ${a.sha256}…）`),
              ]))));
        }
      } else if (n.kind === 'execution') {
        parts.push(h('div', { key: 'none', className: 'rfw-empty' }, '尚无运行记录'));
      }
      return h('div', null, parts);
    }

    function Workbench() {
      const [project, setProject] = React.useState(
        () => window.localStorage.getItem('rf_project') || '');
      const [data, setData] = React.useState(null);
      const [selected, setSelected] = React.useState(null);
      const [hint, setHint] = React.useState('');

      const load = React.useCallback((p) => {
        const proj = (p ?? project);
        if (!proj) { setHint('请输入项目目录'); return; }
        fetch('/researchflow/api/tree?project=' + encodeURIComponent(proj))
          .then((r) => r.json())
          .then((d) => {
            if (d.error || d.ok === false) { setHint('加载失败：' + (d.error || '未知错误')); return; }
            setData(d);
            setHint(`${d.project} · 更新于 ${d.generated_at}`);
          })
          .catch((e) => setHint('请求失败：' + e));
      }, [project]);

      React.useEffect(() => {
        fetch('/researchflow/api/config').then((r) => r.json()).then((c) => {
          const saved = window.localStorage.getItem('rf_project');
          const initial = saved || c.defaultProject || '';
          setProject(initial);
          if (initial) load(initial);
        }).catch(() => {});
      }, []);
      React.useEffect(() => {
        const timer = setInterval(() => { if (data && !document.hidden) load(); }, 8000);
        return () => clearInterval(timer);
      }, [data, load]);

      const act = (path, body) => fetch(path, {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
      }).then((r) => r.json()).then(() => load());
      const onDecide = (node, pass) => {
        const comment = window.prompt('决策备注（可空）', '') || '';
        act('/researchflow/api/decide', { project, node, pass, comment });
      };
      const onRun = (node) => act('/researchflow/api/run', { project, node });
      const runAll = () => act('/researchflow/api/run', { project, all: true });
      const selectedNode = data && selected
        ? data.nodes.find((n) => n.id === selected) : null;

      return h(React.Fragment, null,
        h('style', null, CSS),
        h('div', { className: 'rfw-head' },
          h('b', null, 'ResearchFlow 实验工作台'),
          h('input', {
            value: project, placeholder: '项目目录（含 researchflow.yaml）',
            onChange: (e) => setProject(e.target.value),
            onBlur: () => { window.localStorage.setItem('rf_project', project); load(); },
          }),
          h('button', { className: 'rfw-btn primary', onClick: () => load() }, '刷新'),
          h('button', { className: 'rfw-btn', onClick: runAll }, '全部运行')),
        h('div', { className: 'rfw-hint' }, hint || ' '),
        h('div', { className: 'rfw-main' },
          h('div', { className: 'rfw-tree' },
            data ? h(TreeSvg, { data, onSelect: setSelected })
                 : h('div', { className: 'rfw-empty' }, '加载中…（或请输入项目目录后回车）')),
          h('div', { className: 'rfw-detail' },
            h(Detail, { node: selectedNode, onDecide, onRun }))));
    }

    function Fab() {
      const [open, setOpen] = React.useState(false);
      return h(React.Fragment, null,
        h('button', {
          className: 'rfw-fab', title: 'ResearchFlow 实验工作台',
          onClick: () => setOpen(!open),
        }, h('svg', { viewBox: '0 0 64 64', width: 22, height: 22 },
          h('circle', { cx: 20, cy: 18, r: 6, fill: '#4f9cf9' }),
          h('circle', { cx: 44, cy: 18, r: 6, fill: '#34a853' }),
          h('path', {
            d: 'M20 24v6c0 4.4 3.6 6.4 12 8.4M44 24v6c0 4.4-3.6 6.4-12 8.4',
            stroke: '#d7e0ea', strokeWidth: 3, fill: 'none', strokeLinecap: 'round',
          }),
          h('polygon', { points: '32,36 41,44 32,52 23,44', fill: '#fb8c00' }))),
        open ? h('div', { className: 'rfw-drawer' },
          h('button', { className: 'rfw-x', style: { position: 'absolute', right: 10, top: 8, zIndex: 2 }, onClick: () => setOpen(false) }, '×'),
          h(Workbench)) : null);
    }

    return {
      inject: ['slots'],
      apply(ctx) {
        ctx.slots.inject('shell.overlay', () => ctx.slots.register({
          name: 'shell.overlay', id: 'researchflow-workbench', order: 60,
          label: 'ResearchFlow 实验工作台',
        }, Fab));
      },
    };
  },
});
