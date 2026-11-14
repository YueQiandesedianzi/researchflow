// ResearchFlow Workbench — Client 半：shell.overlay 悬浮球 + 轻量启动器抽屉。
// 完整功能在独立页面 /researchflow（五标签工作台）；抽屉提供状态摘要、
// 待办决策快捷操作与一键直达，避免双份 UI 维护。
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
.rfw-drawer{position:fixed;top:0;right:0;bottom:0;width:min(440px,92vw);z-index:901;display:flex;flex-direction:column;
  background:var(--dsw-alias-bg-base);border-left:1px solid var(--dsw-alias-border-l1);box-shadow:-8px 0 24px rgba(0,0,0,.4)}
.rfw-head{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--dsw-alias-border-l1)}
.rfw-head b{font-size:14px;margin-right:auto}
.rfw-x{border:none;background:none;color:var(--dsw-alias-label-secondary);font-size:18px;cursor:pointer}
.rfw-body{flex:1;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:12px}
.rfw-card{background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);border-radius:8px;padding:12px}
.rfw-card h3{font-size:12px;color:var(--dsw-alias-label-secondary);margin:0 0 8px;font-weight:500}
.rfw-input{width:100%;background:var(--dsw-alias-bg-base);border:1px solid var(--dsw-alias-border-l1);
  color:var(--dsw-alias-label-primary);border-radius:6px;padding:6px 9px;font-size:12px;margin-bottom:8px}
.rfw-btn{background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);color:var(--dsw-alias-label-primary);
  border-radius:6px;padding:5px 12px;cursor:pointer;font-size:12px}
.rfw-btn:hover{border-color:var(--dsw-alias-brand-primary)}
.rfw-btn.primary{border-color:var(--dsw-alias-brand-primary)}
.rfw-chips{display:flex;gap:6px;flex-wrap:wrap}
.rfw-chip{display:inline-flex;align-items:center;gap:5px;font-size:11px;border:1px solid var(--dsw-alias-border-l1);
  border-radius:10px;padding:1px 8px;color:var(--dsw-alias-label-secondary)}
.rfw-chip i{width:8px;height:8px;border-radius:50%;display:inline-block}
.rfw-dec{display:flex;align-items:center;gap:6px;padding:6px 0;border-top:1px solid var(--dsw-alias-border-l1);font-size:12px}
.rfw-dec span{flex:1;word-break:break-all}
.rfw-hint{font-size:11px;color:var(--dsw-alias-label-secondary)}
`;

    function statusCounts(data) {
      const counts = {};
      (data ? data.nodes : []).forEach((n) => { counts[n.status] = (counts[n.status] || 0) + 1; });
      return counts;
    }

    function Launcher() {
      const [project, setProject] = React.useState(
        () => window.localStorage.getItem('rf_project') || '');
      const [data, setData] = React.useState(null);
      const [hint, setHint] = React.useState('');
      const [busy, setBusy] = React.useState(false);

      const load = React.useCallback((p) => {
        const proj = (p ?? project);
        if (!proj) { setHint('请输入项目目录'); return; }
        fetch('/researchflow/api/tree?project=' + encodeURIComponent(proj))
          .then((r) => r.json())
          .then((d) => {
            if (d.error || d.ok === false) { setHint('加载失败：' + (d.error || '未知')); return; }
            setData(d); setHint(d.project + ' · ' + d.generated_at.slice(5, 19));
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

      const decide = (node, pass) => {
        setBusy(true);
        fetch('/researchflow/api/decide', {
          method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ project, node, pass, comment: '' }),
        }).then((r) => r.json()).then(() => { setBusy(false); load(); });
      };

      const counts = statusCounts(data);
      const awaiting = data ? data.nodes.filter(
        (n) => n.kind === 'decision' && n.status === 'awaiting') : [];

      return h(React.Fragment, null,
        h('style', null, CSS),
        h('div', { className: 'rfw-head' },
          h('b', null, 'ResearchFlow'),
          h('button', {
            className: 'rfw-btn primary',
            onClick: () => window.open('/researchflow', '_blank'),
          }, '打开完整工作台 ↗'),
          h('button', { className: 'rfw-x', onClick: () => window.dispatchEvent(new CustomEvent('rfw-close')) }, '×')),
        h('div', { className: 'rfw-body' },
          h('div', { className: 'rfw-card' },
            h('h3', null, '项目'),
            h('input', {
              className: 'rfw-input', value: project,
              placeholder: '项目目录（含 researchflow.yaml）',
              onChange: (e) => setProject(e.target.value),
              onBlur: () => { window.localStorage.setItem('rf_project', project); load(); },
            }),
            h('button', { className: 'rfw-btn', onClick: () => load() }, '刷新'),
            ' ',
            h('span', { className: 'rfw-hint' }, hint)),
          h('div', { className: 'rfw-card' },
            h('h3', null, '节点状态'),
            h('div', { className: 'rfw-chips' },
              Object.keys(STATUS_COLOR).filter((s) => counts[s]).map((s) =>
                h('span', { key: s, className: 'rfw-chip' },
                  h('i', { style: { background: STATUS_COLOR[s] } }), `${s} ${counts[s]}`)),
              !data ? h('span', { className: 'rfw-hint' }, '未加载') : null)),
          awaiting.length ? h('div', { className: 'rfw-card' },
            h('h3', null, `待办决策（${awaiting.length}）`),
            awaiting.map((n) => h('div', { key: n.id, className: 'rfw-dec' },
              h('span', null, `${n.id} ${n.title || ''}`),
              h('button', { className: 'rfw-btn primary', disabled: busy, onClick: () => decide(n.id, true) }, '通过'),
              h('button', { className: 'rfw-btn', disabled: busy, onClick: () => decide(n.id, false) }, '驳回'))))
            : null,
          h('div', { className: 'rfw-card' },
            h('h3', null, '完整功能'),
            h('div', { className: 'rfw-hint' },
              '实验树操作、指标对照、图表、运行记录、决策日志与复现包导出，',
              '均在独立页面中：点右上角「打开完整工作台」。'))));
    }

    function Fab() {
      const [open, setOpen] = React.useState(false);
      React.useEffect(() => {
        const close = () => setOpen(false);
        window.addEventListener('rfw-close', close);
        return () => window.removeEventListener('rfw-close', close);
      }, []);
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
        open ? h('div', { className: 'rfw-drawer' }, h(Launcher)) : null);
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
