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
