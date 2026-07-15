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
function tablistFocusKey(ev) {
  var delta = { ArrowRight: 1, ArrowLeft: -1 };
  if (!(ev.key in delta) && ev.key !== 'Home' && ev.key !== 'End') return;
  var tabs = Array.prototype.slice.call(
    ev.currentTarget.querySelectorAll('[role="tab"]'),
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
}
function initTabKeyboard() {
  var lists = document.querySelectorAll('[role="tablist"]');
  for (var i = 0; i < lists.length; i++) {
    lists[i].addEventListener('keydown', tablistFocusKey);
  }
}
function flushPending(pid) {
  /* run each view's deferred init once, on first show; one broken view must
     not blank its siblings in the panel */
  var fns = window.__viz.pending[pid];
  if (!fns) return;
  delete window.__viz.pending[pid];
  for (var f = 0; f < fns.length; f++) {
    try {
      fns[f]();
    } catch (err) {
      if (window.console) {
        console.error('viz init failed for ' + pid, err);
      }
    }
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
  flushPending(pid);
  resizeGraphsIn(active);
  resizeChartsIn(active);
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
      resizeGraphsIn(active);
      resizeChartsIn(active);
    }, 150);
  });
})();
