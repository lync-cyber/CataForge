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
