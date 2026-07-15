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
