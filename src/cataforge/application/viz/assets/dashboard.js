window.__viz = window.__viz || { cy: {}, ec: {}, pending: {} };
window.__viz.register = function (pid, fn) {
  (window.__viz.pending[pid] = window.__viz.pending[pid] || []).push(fn);
};
window.__viz.stateKey = 'cataforge-viz:' + location.pathname;
window.__viz.state = (function () {
  try {
    return (
      JSON.parse(localStorage.getItem(window.__viz.stateKey) || '{}') || {}
    );
  } catch (e) {
    return {};
  }
})();
window.__viz.saveState = function (k, v) {
  window.__viz.state[k] = v;
  try {
    localStorage.setItem(
      window.__viz.stateKey,
      JSON.stringify(window.__viz.state),
    );
  } catch (e) {}
  var i = k.lastIndexOf(':');
  if (i > 0) {
    syncReset(k.slice(0, i));
  }
};
function clearViewState(id) {
  var st = window.__viz.state;
  for (var k in st) {
    if (k.indexOf(id + ':') === 0) {
      delete st[k];
    }
  }
  try {
    localStorage.setItem(window.__viz.stateKey, JSON.stringify(st));
  } catch (e) {}
}
function syncReset(id) {
  /* the reset button only shows once this view actually persisted something */
  var btns = document.querySelectorAll('.vreset[data-target="' + id + '"]');
  if (!btns.length) return;
  var show = false,
    st = window.__viz.state;
  for (var k in st) {
    if (k.indexOf(id + ':') === 0) {
      show = true;
      break;
    }
  }
  for (var i = 0; i < btns.length; i++) {
    btns[i].hidden = !show;
  }
}
function setPressed(el, on) {
  el.classList.toggle('on', !!on);
  el.setAttribute('aria-pressed', on ? 'true' : 'false');
}
function flashCopy(el, ok, msg) {
  var live = document.getElementById('copy_status');
  if (live) {
    live.textContent = msg;
  }
  el.classList.add(ok ? 'copied' : 'copy-failed');
  el.setAttribute('data-copymsg', msg);
  setTimeout(function () {
    el.classList.remove('copied', 'copy-failed');
    el.removeAttribute('data-copymsg');
  }, 1600);
}
function fallbackCopy(el) {
  /* file:// or a denied clipboard: select the text for a manual copy */
  try {
    var sel = window.getSelection(),
      range = document.createRange();
    range.selectNodeContents(el);
    sel.removeAllRanges();
    sel.addRange(range);
  } catch (e) {}
  flashCopy(el, false, '按 Ctrl+C 复制');
}
function copyText(el, text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(
      function () {
        flashCopy(el, true, '已复制');
      },
      function () {
        fallbackCopy(el);
      },
    );
  } else {
    fallbackCopy(el);
  }
}
window.__viz.stateArr = function (k) {
  var v = window.__viz.state[k];
  return Array.isArray(v)
    ? v
    : []; /* a corrupted persisted value must not crash init */
};
window.__viz.setIndex = function (entries) {
  for (var i = 0; i < entries.length; i++) {
    entries[i].k = (
      (entries[i].id || '') +
      ' ' +
      (entries[i].l || '')
    ).toLowerCase();
  }
  window.__viz.entityIndex = entries;
};
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function closeInspector() {
  var box = document.getElementById('inspector');
  if (!box || box.hidden) return;
  box.hidden = true;
  var op = window.__viz._insOpener;
  window.__viz._insOpener = null;
  if (op && op.focus) {
    op.focus();
  }
}
window.__viz.inspect = function (d, srcDom) {
  var box = document.getElementById('inspector');
  if (!box) return;
  /* remember the opener only on open, not on in-place re-render, so closing
     returns focus to where the user actually came from */
  if (box.hidden) {
    window.__viz._insOpener = document.activeElement;
  }
  var h =
    '<div class="ins-head"><strong>' +
    escHtml(d.label || d.id) +
    '</strong>' +
    '<button class="ins-close" aria-label="关闭">×</button></div>';
  if (d.status) {
    h += '<div class="ins-status">' + escHtml(d.status) + '</div>';
  }
  var meta = d.meta || {};
  var rows = '';
  for (var k in meta) {
    rows +=
      '<tr><th>' + escHtml(k) + '</th><td>' + escHtml(meta[k]) + '</td></tr>';
  }
  if (rows) {
    h += '<table class="ins-meta">' + rows + '</table>';
  }
  var idx = window.__viz.entityIndex || [];
  var cur = srcDom ? srcDom.replace(/_v$/, '') : null;
  var jumps = '';
  for (var i = 0; i < idx.length; i++) {
    if (idx[i].id === d.id && idx[i].p !== cur) {
      jumps +=
        '<button class="ins-jump" data-p="' +
        escHtml(idx[i].p) +
        '" data-n="' +
        escHtml(d.id) +
        '">' +
        escHtml(idx[i].p.slice(6)) +
        '</button>';
    }
  }
  if (jumps) {
    h += '<div class="ins-xref">在其他视图: ' + jumps + '</div>';
  }
  box.innerHTML = h;
  box.hidden = false;
  box.focus();
  box.querySelector('.ins-close').addEventListener('click', closeInspector);
  var js = box.querySelectorAll('.ins-jump');
  for (var j = 0; j < js.length; j++) {
    js[j].addEventListener('click', function () {
      window.__viz.focus(
        this.getAttribute('data-p'),
        this.getAttribute('data-n'),
      );
    });
  }
};
function vizTheme() {
  /* the CSS custom properties are the single colour source; the static
     fallbacks only cover environments without getComputedStyle support */
  var cs = getComputedStyle(document.documentElement);
  var v = function (name, fb) {
    var x = cs.getPropertyValue(name).trim();
    return x || fb;
  };
  return {
    nodeFill: v('--viz-node-fill', '#dfe6ee'),
    nodeBorder: v('--viz-node-border', '#7f8fa6'),
    nodeLabel: v('--viz-node-label', '#1f2d3d'),
    edge: v('--viz-edge', '#848e9b'),
    muted: v('--muted', '#637288'),
    canvas: v('--canvas', '#fff'),
    accent: v('--accent', '#36648b'),
    chipLine: v('--chip-line', '#ccd2da'),
  };
}
function graphStyle() {
  var t = vizTheme();
  return [
    {
      selector: 'node',
      style: {
        'background-color': t.nodeFill,
        'border-color': t.nodeBorder,
        'border-width': 1,
        label: 'data(label)',
        'font-size': 10,
        'text-valign': 'center',
        'text-halign': 'center',
        width: 'label',
        height: 'label',
        padding: '6px',
        shape: 'round-rectangle',
        color: t.nodeLabel,
      },
    },
    { selector: 'node[bg]', style: { 'background-color': 'data(bg)' } },
    {
      selector: 'node[border]',
      style: { 'border-color': 'data(border)', 'border-width': 2 },
    },
    {
      selector: 'edge',
      style: {
        width: 1,
        'line-color': t.edge,
        'target-arrow-color': t.edge,
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
      },
    },
    {
      selector: 'edge[label]',
      style: {
        label: 'data(label)',
        'font-size': 8,
        color: t.muted,
        'text-background-color': t.canvas,
        'text-background-opacity': 1,
      },
    },
    {
      selector: ':parent',
      style: {
        'background-opacity': 0.06,
        'background-color': t.accent,
        'border-color': t.chipLine,
        'border-width': 1,
        label: 'data(label)',
        'font-size': 11,
        color: t.muted,
        'text-valign': 'top',
        'text-halign': 'center',
        padding: '10px',
        shape: 'round-rectangle',
      },
    },
    { selector: '.dim', style: { opacity: 0.12 } },
    { selector: '.folded', style: { display: 'none' } },
    { selector: '.offstage', style: { display: 'none' } },
    {
      selector: '.focus',
      style: { 'border-width': 3, 'border-color': t.accent },
    },
  ];
}
function chipVals(chips, attr, on) {
  /* data-attr values of the chips whose pressed state matches `on` */
  var out = [];
  for (var i = 0; i < chips.length; i++) {
    if (chips[i].classList.contains('on') === on) {
      out.push(chips[i].getAttribute(attr));
    }
  }
  return out;
}
function restoreChips(chips, attr, offs) {
  /* re-apply a persisted `off` list: unpress every chip it names */
  for (var i = 0; i < chips.length; i++) {
    if (offs.indexOf(chips[i].getAttribute(attr)) >= 0) {
      setPressed(chips[i], false);
    }
  }
}
function edgesFromNodes(cy, cls) {
  /* an edge carries a node class when either endpoint has it */
  cy.edges().forEach(function (e) {
    e.toggleClass(cls, e.source().hasClass(cls) || e.target().hasClass(cls));
  });
}
function graphLayout(compound, opts) {
  /* defer: the catalogue graph inits inside a hidden 0-size wrapper where any
     real layout degenerates (and cose runs async, racing later re-layouts) —
     hold positions until the first show lays out at real size */
  if (opts.defer) return { name: 'preset' };
  if (compound) {
    return {
      name: 'cose',
      padding: 14,
      fit: true,
      nodeDimensionsIncludeLabels: true,
      idealEdgeLength: 60,
    };
  }
  return {
    name: 'breadthfirst',
    directed: true,
    spacingFactor: 1.1,
    padding: 12,
    fit: true,
  };
}
function graphTranspose(cy) {
  /* breadthfirst lays top-down; a horizontal graph transposes its ranks */
  cy.startBatch();
  cy.nodes().forEach(function (n) {
    var p = n.position();
    n.position({ x: p.y, y: p.x });
  });
  cy.endBatch();
  cy.fit(undefined, 12);
}
function wireViewport(cy, id) {
  var vp = window.__viz.state[id + ':vp'];
  if (vp && vp.zoom) {
    cy.viewport({ zoom: vp.zoom, pan: vp.pan });
  }
  var vt;
  cy.on('viewport', function () {
    clearTimeout(vt);
    vt = setTimeout(function () {
      window.__viz.saveState(id + ':vp', { zoom: cy.zoom(), pan: cy.pan() });
    }, 200);
  });
}
function graphApplyFold(cy, tchips, id, save) {
  var off = chipVals(tchips, 'data-type', false);
  cy.batch(function () {
    cy.nodes().forEach(function (n) {
      n.toggleClass('folded', off.indexOf(n.data('type') || '') >= 0);
    });
    edgesFromNodes(cy, 'folded');
  });
  if (save) {
    window.__viz.saveState(id + ':fold', off);
  }
}
function wireFold(cy, view, id) {
  /* layer folding: type chips hide whole node layers; catalogue chips keep
     their own dim-based semantics wired in initCatalogue */
  var tchips = view.querySelectorAll('.fchip[data-type]');
  var foldOffs = window.__viz.stateArr(id + ':fold');
  restoreChips(tchips, 'data-type', foldOffs);
  for (var i = 0; i < tchips.length; i++) {
    tchips[i].addEventListener('click', function () {
      setPressed(this, !this.classList.contains('on'));
      graphApplyFold(cy, tchips, id, true);
    });
  }
  if (foldOffs.length) {
    graphApplyFold(cy, tchips, id, false);
  }
}
function graphApplyMode(cy, view, ms, id, mode, save) {
  var alt = view.querySelector('.alt-table');
  var cyEl = document.getElementById(id);
  if (!alt) return;
  var table = mode === 'table';
  alt.hidden = !table;
  cyEl.style.display = table ? 'none' : '';
  ms.textContent = table ? '图形视图' : '表格视图';
  if (!table) {
    cy.resize();
  }
  if (save) {
    window.__viz.saveState(id + ':mode', mode);
  }
}
function wireGraphMode(cy, view, id) {
  var ms = view.querySelector('.modeswitch[data-target="' + id + '"]');
  if (!ms) return;
  ms.addEventListener('click', function () {
    graphApplyMode(
      cy,
      view,
      ms,
      id,
      document.getElementById(id).style.display === 'none' ? 'graph' : 'table',
      true,
    );
  });
  if (window.__viz.state[id + ':mode'] === 'table') {
    graphApplyMode(cy, view, ms, id, 'table', false);
  }
}
function wireGraphTip(cy) {
  var tip =
    window.__viz.tip ||
    (window.__viz.tip = (function () {
      var d = document.createElement('div');
      d.className = 'viztip';
      d.style.display = 'none';
      document.body.appendChild(d);
      return d;
    })());
  cy.on('mouseover', 'node', function (ev) {
    var t = ev.target.data('tip');
    if (!t) {
      return;
    }
    tip.innerHTML = t
      .split('\n')
      .map(function (s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
      })
      .join('<br>');
    tip.style.display = 'block';
  });
  cy.on('mousemove', 'node', function (ev) {
    tip.style.left = ev.originalEvent.pageX + 12 + 'px';
    tip.style.top = ev.originalEvent.pageY + 12 + 'px';
  });
  cy.on('mouseout', 'node', function () {
    tip.style.display = 'none';
  });
}
function graphSearch(cy, box, count, id) {
  var setCount = function (t) {
    if (count) {
      count.textContent = t;
    }
  };
  var q = box.value.trim().toLowerCase();
  if (!q) {
    cy.elements().removeClass('dim');
    setCount('');
    return;
  }
  var total = cy.nodes().length,
    hits = 0;
  cy.nodes().forEach(function (n) {
    if ((n.data('label') || '').toLowerCase().indexOf(q) >= 0) {
      hits++;
    }
  });
  if (!hits) {
    /* dimming everything reads as a broken graph — say it instead */
    cy.elements().removeClass('dim');
    setCount('命中 0 / ' + total + ' · 画面未过滤');
    return;
  }
  cy.nodes().forEach(function (n) {
    n.toggleClass('dim', (n.data('label') || '').toLowerCase().indexOf(q) < 0);
  });
  edgesFromNodes(cy, 'dim');
  setCount('命中 ' + hits + ' / ' + total);
}
function wireGraphSearch(cy, id) {
  var box = document.querySelector('.search[data-target="' + id + '"]');
  if (!box) return;
  var count = document.getElementById(id + '_count');
  box.addEventListener('input', function () {
    window.__viz.saveState(id + ':q', box.value);
    graphSearch(cy, box, count, id);
  });
  var savedQ = window.__viz.state[id + ':q'];
  if (savedQ) {
    box.value = savedQ;
    graphSearch(cy, box, count, id);
  }
}
function initGraph(id, elements, opts) {
  opts = opts || {};
  var compound = elements.some(function (e) {
    return e.data && e.data.parent;
  });
  var cy = cytoscape({
    container: document.getElementById(id),
    elements: elements,
    style: graphStyle(),
    layout: graphLayout(compound, opts),
    wheelSensitivity: 0.2,
  });
  if (!compound && (opts.dir === 'LR' || opts.dir === 'RL')) {
    graphTranspose(cy);
  }
  window.__viz.cy[id] = cy;
  wireViewport(cy, id);
  cy.on('dbltap', function (ev) {
    if (ev.target === cy) {
      cy.fit(undefined, 12);
    }
  });
  cy.on('tap', 'node', function (ev) {
    window.__viz.inspect(ev.target.data(), id);
  });
  var view = document.getElementById(id).closest('.view');
  if (view && !view.classList.contains('cat-view')) {
    wireFold(cy, view, id);
    wireGraphMode(cy, view, id);
  }
  wireGraphTip(cy);
  wireGraphSearch(cy, id);
  syncReset(id);
  return cy;
}
function initChart(id, option) {
  var dark =
    window.matchMedia &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  if (
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ) {
    option.animation = false;
  }
  option.backgroundColor =
    'transparent'; /* .chart's var(--canvas) is the surface */
  window.__viz.ecOpt = window.__viz.ecOpt || {};
  window.__viz.ecOpt[id] = option; /* kept for a live theme-change re-init */
  var c = echarts.init(document.getElementById(id), dark ? 'dark' : null);
  c.setOption(option);
  window.__viz.ec[id] = c;
  return c;
}
function initChartMode(id) {
  /* chart views: toggle between the canvas ("_gfx" wrapper) and the
     equivalent data table, persisted like the graph views' mode */
  var gfx = document.getElementById(id + '_gfx');
  if (!gfx) return;
  var view = gfx.closest('.view');
  var ms = view
    ? view.querySelector('.modeswitch[data-target="' + id + '"]')
    : null;
  var alt = view ? view.querySelector('.alt-table') : null;
  if (!ms || !alt) return;
  var applyMode = function (mode, save) {
    var table = mode === 'table';
    alt.hidden = !table;
    gfx.style.display = table ? 'none' : '';
    ms.textContent = table ? '图表视图' : '表格视图';
    if (!table) {
      for (var b in window.__viz.ec) {
        var el = document.getElementById(b);
        if (el && gfx.contains(el)) {
          window.__viz.ec[b].resize();
        }
      }
    }
    if (save) {
      window.__viz.saveState(id + ':mode', mode);
    }
  };
  ms.addEventListener('click', function () {
    applyMode(gfx.style.display === 'none' ? 'graph' : 'table', true);
  });
  if (window.__viz.state[id + ':mode'] === 'table') {
    applyMode('table', false);
  }
}
function catSnapHome(cat) {
  cat.homePos = {};
  cat.cy.nodes().forEach(function (n) {
    var p = n.position();
    cat.homePos[n.id()] = { x: p.x, y: p.y };
  });
}
function catGoHome(cat) {
  if (!cat.homePos) return;
  cat.cy.startBatch();
  cat.cy.nodes().forEach(function (n) {
    var p = cat.homePos[n.id()];
    if (p) {
      n.position({ x: p.x, y: p.y });
    }
  });
  cat.cy.endBatch();
}
function catEgoLayout(cat, keep) {
  /* ego re-layout: global positions scatter a hub's neighbors across the
     whole canvas, so fit alone stays tiny. Concentric reads best for small
     neighborhoods; when its fit still lands unreadably far out, a label-aware
     grid packs hub neighborhoods tighter. Parents are excluded — compound
     layouts derive them from children. */
  var cy = cat.cy;
  var sub = keep.filter(function (el) {
    return el.isEdge() || !el.isParent();
  });
  sub
    .layout({
      name: 'concentric',
      fit: true,
      padding: 40,
      minNodeSpacing: 24,
      animate: false,
      concentric: function (x) {
        return x.id() === cat.fnode ? 2 : 1;
      },
      levelWidth: function () {
        return 1;
      },
    })
    .run();
  if (cy.zoom() < 0.8) {
    sub
      .layout({
        name: 'grid',
        fit: true,
        padding: 40,
        avoidOverlap: true,
        animate: false,
        nodeDimensionsIncludeLabels: true,
      })
      .run();
  }
  /* fitting a tiny neighborhood over-zooms into giant nodes */
  if (cy.zoom() > 2) {
    cy.zoom(2);
    cy.center(keep);
  }
}
function catFocusNbhd(cat, nid, save) {
  /* a dense catalogue is unreadable whole — the graph explores one node's
     direct dependencies; kept nodes' ancestors stay (hiding a compound
     parent would hide its kept children) */
  var cy = cat.cy;
  var n = nid ? cy.getElementById(nid) : cy.collection();
  cat.fnode = n.length && !n.isParent() ? nid : '';
  var keep = cy.collection();
  if (cat.fnode) {
    keep = n.closedNeighborhood();
    keep = keep
      .union(keep.nodes().edgesWith(keep.nodes()))
      .union(keep.nodes().ancestors());
  }
  cy.batch(function () {
    cy.elements().removeClass('offstage');
    if (cat.fnode) {
      cy.elements().not(keep).addClass('offstage');
    }
  });
  if (cat.unf) {
    cat.unf.hidden = !cat.fnode;
  }
  if (cat.gwrap && !cat.gwrap.hidden) {
    catGoHome(cat);
    if (cat.fnode) {
      catEgoLayout(cat, keep);
    } else {
      cy.fit(undefined, 12);
    }
  }
  if (save) {
    window.__viz.saveState(cat.id + ':fnode', cat.fnode);
  }
}
function catRowVisible(row, needle, types, maint) {
  if (row.getAttribute('data-maint') === '1' && (!maint || !maint.checked))
    return false;
  if (types.indexOf(row.getAttribute('data-type')) < 0) return false;
  return !needle || row.textContent.toLowerCase().indexOf(needle) >= 0;
}
function catApplyCount(cat, needle, types, shown) {
  var count = document.getElementById(cat.id + '_count');
  if (!count || !cat.tbl) return;
  var filtered = needle !== '' || types.length < cat.chips.length;
  count.textContent = filtered
    ? '命中 ' + shown + ' / ' + cat.tbl.tBodies[0].rows.length
    : '';
}
function catApply(cat) {
  var needle = cat.q ? cat.q.value.trim().toLowerCase() : '';
  var types = chipVals(cat.chips, 'data-type', true);
  var rows = cat.tbl ? cat.tbl.tBodies[0].rows : [],
    visible = {},
    shown = 0;
  for (var j = 0; j < rows.length; j++) {
    var ok = catRowVisible(rows[j], needle, types, cat.maint);
    rows[j].style.display = ok ? '' : 'none';
    if (ok) {
      shown++;
    }
    visible[rows[j].getAttribute('data-node')] = ok;
  }
  cat.cy.nodes().forEach(function (n) {
    n.toggleClass('dim', visible[n.id()] === false);
  });
  edgesFromNodes(cat.cy, 'dim');
  catApplyCount(cat, needle, types, shown);
}
function catFocusRow(tbl, target) {
  var rows = tbl.tBodies[0].rows;
  for (var i = 0; i < rows.length; i++) {
    rows[i].classList.toggle('focus', rows[i] === target);
  }
}
function catScrollToRow(cat, nid) {
  var rows = cat.tbl.tBodies[0].rows;
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].getAttribute('data-node') === nid) {
      catFocusRow(cat.tbl, rows[i]);
      rows[i].scrollIntoView({ block: 'nearest' });
      break;
    }
  }
}
function catSortTok(tbl, tok, dir) {
  /* dir true = ascending; column = the sorter's own th */
  var th = tok.closest('th'),
    ci = th.cellIndex;
  var body = tbl.tBodies[0],
    rows = Array.prototype.slice.call(body.rows);
  rows.sort(function (a, b) {
    var av = parseInt(a.cells[ci].textContent) || 0,
      bv = parseInt(b.cells[ci].textContent) || 0;
    return dir ? av - bv : bv - av;
  });
  for (var i = 0; i < rows.length; i++) {
    body.appendChild(rows[i]);
  }
  var ths = tbl.tHead.rows[0].cells;
  for (var h = 0; h < ths.length; h++) {
    if (ths[h].hasAttribute('aria-sort')) {
      ths[h].setAttribute(
        'aria-sort',
        ths[h] === th ? (dir ? 'ascending' : 'descending') : 'none',
      );
    }
  }
}
function catTableClick(cat, ev) {
  var tbl = cat.tbl;
  var t = ev.target;
  if (t.className === 'path') {
    copyText(t, t.textContent);
    return;
  }
  while (t && t !== tbl && !t.getAttribute('data-node')) t = t.parentNode;
  if (!t || t === tbl) return;
  catFocusRow(tbl, t);
  var n = cat.cy.getElementById(t.getAttribute('data-node'));
  if (n.length) {
    cat.cy.elements().removeClass('focus');
    n.addClass('focus');
    catFocusNbhd(cat, n.id(), true);
  }
}
function catInitialLayout(cat) {
  var cy = cat.cy;
  var compound = cy.nodes().some(function (n) {
    return n.isChild();
  });
  /* randomize: deferred init leaves every node at the same point, a singular
     start no force layout can separate */
  cy.layout(
    compound
      ? {
          name: 'cose',
          padding: 14,
          fit: false,
          animate: false,
          randomize: true,
          nodeDimensionsIncludeLabels: true,
          idealEdgeLength: 60,
        }
      : {
          name: 'breadthfirst',
          directed: true,
          spacingFactor: 1.1,
          padding: 12,
          fit: false,
        },
  ).run();
  catSnapHome(cat);
}
function catApplyMode(cat, ms, twrap, mode, save) {
  var graph = mode === 'graph';
  cat.gwrap.hidden = !graph;
  twrap.hidden = graph;
  ms.textContent = graph ? '表格视图' : '拓扑视图';
  if (graph) {
    /* positions are deferred at init — the first show lays out at real size,
       then a focus-aware refit (full graph when nothing focused) */
    cat.cy.resize();
    if (!cat.laidOut) {
      cat.laidOut = true;
      catInitialLayout(cat);
    }
    catFocusNbhd(cat, cat.fnode, false);
  }
  if (save) {
    window.__viz.saveState(cat.id + ':mode', mode);
  }
}
function catWireGraph(cat) {
  if (cat.unf) {
    cat.unf.addEventListener('click', function () {
      catFocusNbhd(cat, '', true);
    });
  }
  cat.cy.on('dbltap', function (ev) {
    if (ev.target === cat.cy && cat.fnode) {
      catFocusNbhd(cat, '', true);
    }
  });
  cat.cy.on('tap', 'node', function (ev) {
    cat.cy.elements().removeClass('focus');
    ev.target.addClass('focus');
    catFocusNbhd(cat, ev.target.id(), true);
    if (!cat.tbl) return;
    catScrollToRow(cat, ev.target.id());
  });
}
function catWireFilters(cat) {
  if (cat.q)
    cat.q.addEventListener('input', function () {
      window.__viz.saveState(cat.id + ':q', cat.q.value);
      catApply(cat);
    });
  if (cat.maint)
    cat.maint.addEventListener('change', function () {
      window.__viz.saveState(cat.id + ':maint', cat.maint.checked);
      catApply(cat);
    });
  for (var i = 0; i < cat.chips.length; i++) {
    cat.chips[i].addEventListener('click', function () {
      setPressed(this, !this.classList.contains('on'));
      window.__viz.saveState(
        cat.id + ':off',
        chipVals(cat.chips, 'data-type', false),
      );
      catApply(cat);
    });
  }
}
function catWireSort(cat) {
  var tok = document.getElementById(cat.id + '_tok');
  if (!tok || !cat.tbl) return;
  tok.addEventListener('click', function () {
    var dir = cat.asc;
    catSortTok(cat.tbl, tok, dir);
    cat.asc = !dir;
    window.__viz.saveState(cat.id + ':tok', dir ? 'asc' : 'desc');
  });
  var savedTok = window.__viz.state[cat.id + ':tok'];
  if (savedTok) {
    var sd = savedTok === 'asc';
    catSortTok(cat.tbl, tok, sd);
    cat.asc = !sd;
  }
}
function catWireTable(cat) {
  if (cat.tbl) {
    cat.tbl.addEventListener('click', function (ev) {
      catTableClick(cat, ev);
    });
  }
  catWireSort(cat);
}
function catRestoreFocus(cat) {
  if (!window.__viz.state[cat.id + ':fnode']) return;
  catFocusNbhd(cat, window.__viz.state[cat.id + ':fnode'], false);
  if (!cat.fnode) return;
  cat.cy.getElementById(cat.fnode).addClass('focus');
  if (!cat.tbl) return;
  catScrollHomeRow(cat);
}
function catScrollHomeRow(cat) {
  var frows = cat.tbl.tBodies[0].rows;
  for (var fr = 0; fr < frows.length; fr++) {
    if (frows[fr].getAttribute('data-node') === cat.fnode) {
      catFocusRow(cat.tbl, frows[fr]);
      break;
    }
  }
}
function catWireMode(cat, view) {
  var ms = view
    ? view.querySelector('.modeswitch[data-target="' + cat.id + '"]')
    : null;
  var twrap = cat.tbl ? cat.tbl.parentNode : null;
  if (!ms || !cat.gwrap || !twrap) return;
  ms.addEventListener('click', function () {
    catApplyMode(cat, ms, twrap, cat.gwrap.hidden ? 'graph' : 'table', true);
  });
  if (window.__viz.state[cat.id + ':mode'] === 'graph') {
    catApplyMode(cat, ms, twrap, 'graph', false);
  }
}
function initCatalogue(id, elements) {
  var cy = initGraph(id, elements, { defer: true });
  var tbl = document.getElementById(id + '_tbl');
  var view = tbl ? tbl.parentNode.parentNode : null;
  var st = window.__viz.state;
  var cat = {
    id: id,
    cy: cy,
    q: document.getElementById(id + '_q'),
    tbl: tbl,
    maint: document.getElementById(id + '_maint'),
    chips: view ? view.querySelectorAll('.fchip') : [],
    gwrap: document.getElementById(id + '_gwrap'),
    unf: document.getElementById(id + '_unfocus'),
    fnode: '',
    homePos: null,
    asc: false,
    laidOut: false,
  };
  catWireGraph(cat);
  if (cat.q && st[id + ':q']) {
    cat.q.value = st[id + ':q'];
  }
  if (cat.maint && st[id + ':maint'] != null) {
    cat.maint.checked = st[id + ':maint'];
  }
  restoreChips(cat.chips, 'data-type', window.__viz.stateArr(id + ':off'));
  catWireFilters(cat);
  catWireTable(cat);
  catApply(cat);
  syncReset(id);
  catRestoreFocus(cat);
  catWireMode(cat, view);
  return cy;
}
function ftRowOk(row, needle, on, chips, activeSeg) {
  var s = row.getAttribute('data-status') || '';
  if (activeSeg && s !== activeSeg) return false;
  if (chips.length && on.indexOf(s) < 0) return false;
  return !needle || row.textContent.toLowerCase().indexOf(needle) >= 0;
}
function ftCount(c, needle, on, shown, total) {
  var count = document.getElementById(c.id + '_tcount');
  if (!count) return;
  var filtered =
    needle !== '' ||
    !!c.activeSeg ||
    (c.chips.length && on.length < c.chips.length);
  count.textContent = filtered ? '命中 ' + shown + ' / ' + total : '';
}
function ftApply(c) {
  var needle = c.q ? c.q.value.trim().toLowerCase() : '';
  var on = chipVals(c.chips, 'data-status', true);
  var rows = c.tbl.tBodies[0].rows,
    shown = 0;
  for (var j = 0; j < rows.length; j++) {
    var ok = ftRowOk(rows[j], needle, on, c.chips, c.activeSeg);
    rows[j].style.display = ok ? '' : 'none';
    if (ok) {
      shown++;
    }
  }
  ftCount(c, needle, on, shown, rows.length);
}
function ftWireSegs(c) {
  for (var g = 0; g < c.segs.length; g++) {
    c.segs[g].addEventListener('click', function () {
      var s = this.getAttribute('data-status');
      c.activeSeg = c.activeSeg === s ? null : s;
      for (var i = 0; i < c.segs.length; i++) {
        setPressed(
          c.segs[i],
          c.segs[i].getAttribute('data-status') === c.activeSeg,
        );
      }
      ftApply(c);
    });
  }
}
function ftWire(c) {
  if (c.q)
    c.q.addEventListener('input', function () {
      window.__viz.saveState(c.id + ':q', c.q.value);
      ftApply(c);
    });
  for (var i = 0; i < c.chips.length; i++) {
    c.chips[i].addEventListener('click', function () {
      setPressed(this, !this.classList.contains('on'));
      window.__viz.saveState(
        c.id + ':off',
        chipVals(c.chips, 'data-status', false),
      );
      ftApply(c);
    });
  }
  ftWireSegs(c);
}
function initFilterTable(id) {
  var tbl = document.getElementById(id + '_tbl');
  if (!tbl) return;
  var wrap = tbl.closest('.view');
  var c = {
    id: id,
    tbl: tbl,
    q: document.getElementById(id + '_q'),
    chips: wrap ? wrap.querySelectorAll('.fchip[data-status]') : [],
    segs: wrap ? wrap.querySelectorAll('.seg[data-status]') : [],
    activeSeg: null,
  };
  var st = window.__viz.state;
  if (c.q && st[id + ':q']) {
    c.q.value = st[id + ':q'];
  }
  restoreChips(c.chips, 'data-status', window.__viz.stateArr(id + ':off'));
  ftWire(c);
  ftApply(c);
  syncReset(id);
}
window.__viz.filterAnomalies = function (pid) {
  var panel = document.getElementById(pid);
  if (!panel) return;
  var fine = ['ok', ''];
  for (var a in window.__viz.cy) {
    var g = window.__viz.cy[a];
    if (!panel.contains(g.container())) continue;
    var anom = g.nodes().filter(function (n) {
      return fine.indexOf(n.data('status') || '') < 0;
    });
    if (!anom.length)
      return; /* nothing anomalous — dimming everything helps nobody */
    g.nodes().forEach(function (n) {
      n.toggleClass('dim', fine.indexOf(n.data('status') || '') >= 0);
    });
    g.edges().forEach(function (e) {
      e.toggleClass(
        'dim',
        e.source().hasClass('dim') || e.target().hasClass('dim'),
      );
    });
    return;
  }
  var rows = panel.querySelectorAll('tr[data-status]');
  var hit = false;
  for (var i = 0; i < rows.length; i++) {
    if (fine.indexOf(rows[i].getAttribute('data-status')) < 0) hit = true;
  }
  if (!hit) return;
  for (var j = 0; j < rows.length; j++) {
    rows[j].style.display =
      fine.indexOf(rows[j].getAttribute('data-status')) < 0 ? '' : 'none';
  }
};
window.__viz.focus = function (pid, nid) {
  showPanel(pid);
  var active = document.getElementById(pid);
  if (!active) return;
  for (var a in window.__viz.cy) {
    var g = window.__viz.cy[a];
    if (active.contains(g.container())) {
      g.elements().removeClass('focus');
      var n = g.getElementById(nid);
      if (n.length) {
        n.addClass('focus');
        g.center(n);
      }
      break;
    }
  }
  /* ids are data, not selector syntax — match by attribute value, never by
     interpolating into a selector string */
  var rows = active.querySelectorAll('tr[data-node]');
  var row = null;
  for (var r = 0; r < rows.length; r++) {
    var hit = rows[r].getAttribute('data-node') === nid;
    rows[r].classList.toggle('focus', hit);
    if (hit) {
      row = rows[r];
    }
  }
  if (row) {
    row.setAttribute('tabindex', '-1');
    row.scrollIntoView({ block: 'center' });
    row.focus();
  }
};
function syncTablists() {
  /* roving tabindex: per tablist, the selected tab (else the first) is the
     single tabbable entry point */
  var lists = document.querySelectorAll('[role="tablist"]');
  for (var i = 0; i < lists.length; i++) {
    var tabs = lists[i].querySelectorAll('[role="tab"]');
    var sel = -1;
    for (var j = 0; j < tabs.length; j++) {
      if (tabs[j].classList.contains('sel')) {
        sel = j;
        break;
      }
    }
    for (var k = 0; k < tabs.length; k++) {
      tabs[k].setAttribute(
        'tabindex',
        (sel >= 0 ? k === sel : k === 0) ? '0' : '-1',
      );
    }
  }
}
function initTabKeyboard() {
  var lists = document.querySelectorAll('[role="tablist"]');
  for (var i = 0; i < lists.length; i++) {
    (function (list) {
      list.addEventListener('keydown', function (ev) {
        var delta = { ArrowRight: 1, ArrowLeft: -1 };
        if (!(ev.key in delta) && ev.key !== 'Home' && ev.key !== 'End') return;
        var tabs = Array.prototype.slice.call(
          list.querySelectorAll('[role="tab"]'),
        );
        var idx = tabs.indexOf(document.activeElement);
        if (idx < 0) return;
        ev.preventDefault();
        var next =
          ev.key === 'Home'
            ? 0
            : ev.key === 'End'
              ? tabs.length - 1
              : (idx + delta[ev.key] + tabs.length) % tabs.length;
        for (var t = 0; t < tabs.length; t++) {
          tabs[t].setAttribute('tabindex', t === next ? '0' : '-1');
        }
        tabs[next].focus();
      });
    })(lists[i]);
  }
}
function showPanel(pid) {
  var ps = document.querySelectorAll('.panel');
  for (var i = 0; i < ps.length; i++) {
    ps[i].classList.toggle('active', ps[i].id === pid);
  }
  var ts = document.querySelectorAll('.tab');
  for (var j = 0; j < ts.length; j++) {
    var sel = ts[j].getAttribute('data-panel') === pid;
    ts[j].classList.toggle('sel', sel);
    ts[j].setAttribute('aria-selected', sel ? 'true' : 'false');
  }
  syncTablists();
  var active = document.getElementById(pid);
  if (!active) return;
  var fns = window.__viz.pending[pid];
  if (fns) {
    delete window.__viz.pending[pid];
    for (var f = 0; f < fns.length; f++) {
      try {
        fns[f]();
      } catch (err) {
        /* one broken view must not blank its siblings in the panel */
        if (window.console) {
          console.error('viz init failed for ' + pid, err);
        }
      }
    }
  }
  for (var a in window.__viz.cy) {
    var g = window.__viz.cy[a];
    if (active.contains(g.container())) {
      g.resize();
    }
  }
  for (var b in window.__viz.ec) {
    var el = document.getElementById(b);
    if (el && active.contains(el)) {
      window.__viz.ec[b].resize();
    }
  }
  try {
    history.replaceState(null, '', '#' + pid);
  } catch (e) {}
}
function hashPanel() {
  var h = location.hash.slice(1);
  return h && h.indexOf('panel-') === 0 && document.getElementById(h)
    ? h
    : null;
}
document.addEventListener('DOMContentLoaded', function () {
  var cstat = document.createElement('span');
  cstat.id = 'copy_status';
  cstat.className = 'visually-hidden';
  cstat.setAttribute('aria-live', 'polite');
  document.body.appendChild(cstat);
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    var reset = t.closest ? t.closest('.vreset') : null;
    if (reset) {
      /* clear only this view's persisted keys; reload restores pristine
         defaults (the hash keeps the active tab) */
      clearViewState(reset.getAttribute('data-target'));
      location.reload();
      return;
    }
    var fit = t.closest ? t.closest('.vfit') : null;
    if (fit) {
      var g = window.__viz.cy[fit.getAttribute('data-target')];
      if (g) {
        g.fit(undefined, 12);
      }
      return;
    }
    var hint = t.closest ? t.closest('.rhint') : null;
    if (hint) {
      copyText(hint, hint.textContent);
    }
  });
  var ts = document.querySelectorAll('[data-panel]');
  for (var i = 0; i < ts.length; i++) {
    ts[i].addEventListener('click', function () {
      var pid = this.getAttribute('data-panel');
      showPanel(pid);
      if (this.getAttribute('data-filter') === 'anomaly') {
        window.__viz.filterAnomalies(pid);
      }
    });
  }
  initTabKeyboard();
  var ins = document.getElementById('inspector');
  if (ins) {
    ins.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        closeInspector();
      }
    });
  }
  var omni = document.getElementById('omni');
  var list = document.getElementById('omni_list');
  var omniStatus = document.getElementById('omni_status');
  if (omni && list) {
    var hits = [],
      activeIdx = -1,
      ot;
    var announce = function (msg) {
      if (omniStatus) {
        omniStatus.textContent = msg;
      }
    };
    var setExpanded = function (open) {
      list.hidden = !open;
      omni.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (!open) {
        activeIdx = -1;
        omni.removeAttribute('aria-activedescendant');
      }
    };
    var choose = function (e) {
      setExpanded(false);
      omni.value = '';
      window.__viz.focus(e.p, e.id);
    };
    var setActive = function (n) {
      activeIdx = n;
      var opts = list.querySelectorAll('.omni-hit');
      for (var j = 0; j < opts.length; j++) {
        opts[j].classList.toggle('active', j === n);
        opts[j].setAttribute('aria-selected', j === n ? 'true' : 'false');
      }
      if (n >= 0 && opts[n]) {
        omni.setAttribute('aria-activedescendant', opts[n].id);
        opts[n].scrollIntoView({ block: 'nearest' });
      } else {
        omni.removeAttribute('aria-activedescendant');
      }
    };
    var renderHits = function () {
      list.innerHTML = '';
      for (var j = 0; j < hits.length; j++) {
        (function (e, n) {
          var d = document.createElement('div');
          d.className = 'omni-hit';
          d.id = 'omni_opt_' + n;
          d.setAttribute('role', 'option');
          d.setAttribute('aria-selected', 'false');
          d.textContent = e.l + ' · ' + e.p.slice(6);
          d.addEventListener('click', function () {
            choose(e);
          });
          list.appendChild(d);
        })(hits[j], j);
      }
      if (!hits.length) {
        var empty = document.createElement('div');
        empty.className = 'omni-empty';
        empty.setAttribute('role', 'option');
        empty.setAttribute('aria-disabled', 'true');
        empty.textContent = '无匹配实体';
        list.appendChild(empty);
      }
    };
    omni.addEventListener('input', function () {
      clearTimeout(ot);
      ot = setTimeout(function () {
        var q = omni.value.trim().toLowerCase();
        if (!q) {
          list.innerHTML = '';
          setExpanded(false);
          announce('');
          return;
        }
        var idx = window.__viz.entityIndex || [];
        hits = [];
        for (var i = 0; i < idx.length && hits.length < 20; i++) {
          if ((idx[i].k || '').indexOf(q) >= 0) {
            hits.push(idx[i]);
          }
        }
        renderHits();
        setActive(-1);
        setExpanded(true);
        announce(hits.length ? hits.length + ' 个结果' : '无匹配实体');
      }, 120);
    });
    omni.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
        if (list.hidden || !hits.length) return;
        ev.preventDefault();
        var step = ev.key === 'ArrowDown' ? 1 : -1;
        setActive((activeIdx + step + hits.length) % hits.length);
      } else if (ev.key === 'Enter') {
        if (!list.hidden && hits.length) {
          ev.preventDefault();
          choose(hits[activeIdx >= 0 ? activeIdx : 0]);
        }
      } else if (ev.key === 'Escape') {
        if (!list.hidden) {
          setExpanded(false);
        } else if (omni.value) {
          omni.value = '';
          announce('');
        }
      }
    });
    document.addEventListener('click', function (ev) {
      if (ev.target !== omni && !list.contains(ev.target)) {
        setExpanded(false);
      }
    });
  }
  var target = hashPanel();
  if (!target) {
    var act = document.querySelector('.panel.active');
    target = act ? act.id : null;
  }
  if (target) {
    showPanel(target);
  }
  syncTablists();
});
window.addEventListener('hashchange', function () {
  var h = hashPanel();
  if (h) {
    showPanel(h);
  }
});
(function () {
  if (!window.matchMedia) return;
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  var reskin = function () {
    var gs = graphStyle();
    for (var a in window.__viz.cy) {
      window.__viz.cy[a].style(gs);
    }
    var opts = window.__viz.ecOpt || {};
    for (var b in window.__viz.ec) {
      var el = document.getElementById(b);
      if (!el || !opts[b]) continue;
      window.__viz.ec[b].dispose();
      var c = echarts.init(el, mq.matches ? 'dark' : null);
      c.setOption(opts[b]);
      window.__viz.ec[b] = c;
    }
  };
  if (mq.addEventListener) {
    mq.addEventListener('change', reskin);
  } else if (mq.addListener) {
    mq.addListener(reskin);
  }
})();
(function () {
  var rt;
  window.addEventListener('resize', function () {
    clearTimeout(rt);
    rt = setTimeout(function () {
      var active = document.querySelector('.panel.active');
      for (var a in window.__viz.cy) {
        var g = window.__viz.cy[a];
        if (!active || active.contains(g.container())) {
          g.resize();
        }
      }
      for (var b in window.__viz.ec) {
        var el = document.getElementById(b);
        if (el && (!active || active.contains(el))) {
          window.__viz.ec[b].resize();
        }
      }
    }, 150);
  });
})();
