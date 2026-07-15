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
