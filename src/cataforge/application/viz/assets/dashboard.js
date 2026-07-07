window.__viz=window.__viz||{cy:{},ec:{},pending:{}};
window.__viz.register=function(pid,fn){
  (window.__viz.pending[pid]=window.__viz.pending[pid]||[]).push(fn);
};
window.__viz.stateKey='cataforge-viz:'+location.pathname;
window.__viz.state=(function(){
  try{return JSON.parse(localStorage.getItem(window.__viz.stateKey)||'{}')||{};}
  catch(e){return{};}
})();
window.__viz.saveState=function(k,v){
  window.__viz.state[k]=v;
  try{localStorage.setItem(window.__viz.stateKey,JSON.stringify(window.__viz.state));}
  catch(e){}
};
function initGraph(id,elements,opts){
  opts=opts||{};
  var compound=elements.some(function(e){return e.data&&e.data.parent;});
  var layout=compound
    ?{name:'cose',padding:14,fit:true,nodeDimensionsIncludeLabels:true,idealEdgeLength:60}
    :{name:'breadthfirst',directed:true,spacingFactor:1.1,padding:12,fit:true};
  var cy=cytoscape({container:document.getElementById(id),elements:elements,
    style:[{selector:'node',style:{'background-color':'#dfe6ee','border-color':'#7f8fa6',
      'border-width':1,'label':'data(label)','font-size':10,'text-valign':'center',
      'text-halign':'center','width':'label','height':'label','padding':'6px',
      'shape':'round-rectangle','color':'#1f2d3d'}},
      {selector:'node[bg]',style:{'background-color':'data(bg)'}},
      {selector:'node[border]',style:{'border-color':'data(border)','border-width':2}},
      {selector:'edge',style:{'width':1,'line-color':'#aab2bd','target-arrow-color':'#aab2bd',
      'target-arrow-shape':'triangle','curve-style':'bezier'}},
      {selector:'edge[label]',style:{'label':'data(label)',
      'font-size':8,'color':'#66758c','text-background-color':'#fff','text-background-opacity':1}},
      {selector:':parent',style:{'background-opacity':0.06,'background-color':'#36648b',
      'border-color':'#c3ccd6','border-width':1,'label':'data(label)','font-size':11,
      'color':'#66758c','text-valign':'top','text-halign':'center','padding':'10px',
      'shape':'round-rectangle'}},
      {selector:'.dim',style:{'opacity':0.12}},
      {selector:'.focus',style:{'border-width':3,'border-color':'#36648b'}}],
    layout:layout,
    wheelSensitivity:0.2});
  if(!compound&&(opts.dir==='LR'||opts.dir==='RL')){
    /* breadthfirst lays top-down; a horizontal graph transposes its ranks */
    cy.startBatch();
    cy.nodes().forEach(function(n){var p=n.position();n.position({x:p.y,y:p.x});});
    cy.endBatch();
    cy.fit(undefined,12);
  }
  window.__viz.cy[id]=cy;
  var vp=window.__viz.state[id+':vp'];
  if(vp&&vp.zoom){cy.viewport({zoom:vp.zoom,pan:vp.pan});}
  var vt;
  cy.on('viewport',function(){
    clearTimeout(vt);
    vt=setTimeout(function(){
      window.__viz.saveState(id+':vp',{zoom:cy.zoom(),pan:cy.pan()});},200);
  });
  cy.on('dbltap',function(ev){if(ev.target===cy){cy.fit(undefined,12);}});
  var tip=window.__viz.tip||(window.__viz.tip=(function(){
    var d=document.createElement('div');d.className='viztip';d.style.display='none';
    document.body.appendChild(d);return d;})());
  cy.on('mouseover','node',function(ev){
    var t=ev.target.data('tip');if(!t){return;}
    tip.innerHTML=t.split('\n').map(function(s){
      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;');}).join('<br>');
    tip.style.display='block';
  });
  cy.on('mousemove','node',function(ev){
    tip.style.left=(ev.originalEvent.pageX+12)+'px';
    tip.style.top=(ev.originalEvent.pageY+12)+'px';
  });
  cy.on('mouseout','node',function(){tip.style.display='none';});
  var box=document.querySelector('.search[data-target="'+id+'"]');
  if(box){
    var applySearch=function(){
      var q=box.value.trim().toLowerCase();
      if(!q){cy.elements().removeClass('dim');return;}
      cy.nodes().forEach(function(n){
        var hit=(n.data('label')||'').toLowerCase().indexOf(q)>=0;
        n.toggleClass('dim',!hit);});
      cy.edges().forEach(function(e){
        var keep=!e.source().hasClass('dim')&&!e.target().hasClass('dim');
        e.toggleClass('dim',!keep);});
    };
    box.addEventListener('input',function(){
      window.__viz.saveState(id+':q',box.value);applySearch();});
    var savedQ=window.__viz.state[id+':q'];
    if(savedQ){box.value=savedQ;applySearch();}
  }
  return cy;
}
function initChart(id,option){
  var dark=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;
  var c=echarts.init(document.getElementById(id),dark?'dark':null);
  if(dark){option.backgroundColor='transparent';}
  c.setOption(option);window.__viz.ec[id]=c;return c;
}
function initCatalogue(id,elements){
  var cy=initGraph(id,elements);
  var q=document.getElementById(id+'_q');
  var tbl=document.getElementById(id+'_tbl');
  var maint=document.getElementById(id+'_maint');
  var view=tbl?tbl.parentNode.parentNode:null;
  var chips=view?view.querySelectorAll('.fchip'):[];
  var st=window.__viz.state;
  if(q&&st[id+':q']){q.value=st[id+':q'];}
  if(maint&&st[id+':maint']!=null){maint.checked=st[id+':maint'];}
  var offs=st[id+':off']||[];
  for(var r=0;r<chips.length;r++){
    if(offs.indexOf(chips[r].getAttribute('data-type'))>=0){chips[r].classList.remove('on');}
  }
  function rowVisible(row,needle,types){
    if(row.getAttribute('data-maint')==='1'&&(!maint||!maint.checked))return false;
    if(types.indexOf(row.getAttribute('data-type'))<0)return false;
    return !needle||row.textContent.toLowerCase().indexOf(needle)>=0;
  }
  function apply(){
    var needle=q?q.value.trim().toLowerCase():'';
    var types=[];
    for(var i=0;i<chips.length;i++){if(chips[i].classList.contains('on'))types.push(chips[i].getAttribute('data-type'));}
    var rows=tbl?tbl.tBodies[0].rows:[],visible={};
    for(var j=0;j<rows.length;j++){
      var ok=rowVisible(rows[j],needle,types);
      rows[j].style.display=ok?'':'none';
      visible[rows[j].getAttribute('data-node')]=ok;
    }
    cy.nodes().forEach(function(n){n.toggleClass('dim',visible[n.id()]===false);});
    cy.edges().forEach(function(e){
      var keep=!e.source().hasClass('dim')&&!e.target().hasClass('dim');
      e.toggleClass('dim',!keep);});
  }
  if(q)q.addEventListener('input',function(){
    window.__viz.saveState(id+':q',q.value);apply();});
  if(maint)maint.addEventListener('change',function(){
    window.__viz.saveState(id+':maint',maint.checked);apply();});
  for(var c=0;c<chips.length;c++){chips[c].addEventListener('click',function(){
    this.classList.toggle('on');
    var off=[];
    for(var k=0;k<chips.length;k++){
      if(!chips[k].classList.contains('on'))off.push(chips[k].getAttribute('data-type'));}
    window.__viz.saveState(id+':off',off);
    apply();});}
  function focusRow(target){
    var rows=tbl.tBodies[0].rows;
    for(var i=0;i<rows.length;i++){rows[i].classList.toggle('focus',rows[i]===target);}
  }
  if(tbl){tbl.addEventListener('click',function(ev){
    var t=ev.target;
    if(t.className==='path'){
      if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(t.textContent);
      t.setAttribute('title','已复制');
      return;
    }
    while(t&&t!==tbl&&!t.getAttribute('data-node'))t=t.parentNode;
    if(!t||t===tbl)return;
    focusRow(t);
    var n=cy.getElementById(t.getAttribute('data-node'));
    if(n.length){cy.elements().removeClass('focus');n.addClass('focus');cy.center(n);}
  });}
  cy.on('tap','node',function(ev){
    cy.elements().removeClass('focus');ev.target.addClass('focus');
    if(!tbl)return;
    var rows=tbl.tBodies[0].rows;
    for(var i=0;i<rows.length;i++){
      if(rows[i].getAttribute('data-node')===ev.target.id()){
        focusRow(rows[i]);rows[i].scrollIntoView({block:'nearest'});break;}}
  });
  var tok=document.getElementById(id+'_tok'),asc=false;
  function sortTok(dir){/* cell 7 = est_tokens; dir true = ascending */
    var body=tbl.tBodies[0],rows=Array.prototype.slice.call(body.rows);
    rows.sort(function(a,b){
      var av=parseInt(a.cells[7].textContent)||0,bv=parseInt(b.cells[7].textContent)||0;
      return dir?av-bv:bv-av;});
    for(var i=0;i<rows.length;i++){body.appendChild(rows[i]);}
  }
  if(tok&&tbl){
    tok.addEventListener('click',function(){
      var dir=asc;sortTok(dir);asc=!dir;
      window.__viz.saveState(id+':tok',dir?'asc':'desc');});
    var savedTok=window.__viz.state[id+':tok'];
    if(savedTok){var sd=savedTok==='asc';sortTok(sd);asc=!sd;}
  }
  apply();
  return cy;
}
function initFilterTable(id){
  var tbl=document.getElementById(id+'_tbl');if(!tbl)return;
  var q=document.getElementById(id+'_q');
  var wrap=tbl.closest('.view');
  var chips=wrap?wrap.querySelectorAll('.fchip[data-status]'):[];
  var segs=wrap?wrap.querySelectorAll('.seg[data-status]'):[];
  var activeSeg=null;
  var st=window.__viz.state;
  if(q&&st[id+':q']){q.value=st[id+':q'];}
  var offs=st[id+':off']||[];
  for(var r=0;r<chips.length;r++){
    if(offs.indexOf(chips[r].getAttribute('data-status'))>=0){chips[r].classList.remove('on');}
  }
  function apply(){
    var needle=q?q.value.trim().toLowerCase():'';
    var on=[];
    for(var i=0;i<chips.length;i++){if(chips[i].classList.contains('on'))on.push(chips[i].getAttribute('data-status'));}
    var rows=tbl.tBodies[0].rows;
    for(var j=0;j<rows.length;j++){
      var s=rows[j].getAttribute('data-status')||'';
      var ok=(!activeSeg||s===activeSeg)&&(!chips.length||on.indexOf(s)>=0)
        &&(!needle||rows[j].textContent.toLowerCase().indexOf(needle)>=0);
      rows[j].style.display=ok?'':'none';
    }
  }
  if(q)q.addEventListener('input',function(){
    window.__viz.saveState(id+':q',q.value);apply();});
  for(var c=0;c<chips.length;c++){chips[c].addEventListener('click',function(){
    this.classList.toggle('on');
    var off=[];
    for(var k=0;k<chips.length;k++){
      if(!chips[k].classList.contains('on'))off.push(chips[k].getAttribute('data-status'));}
    window.__viz.saveState(id+':off',off);
    apply();});}
  for(var g=0;g<segs.length;g++){segs[g].addEventListener('click',function(){
    var s=this.getAttribute('data-status');
    activeSeg=activeSeg===s?null:s;
    for(var i=0;i<segs.length;i++){
      segs[i].classList.toggle('on',segs[i].getAttribute('data-status')===activeSeg);}
    apply();});}
  apply();
}
window.__viz.filterAnomalies=function(pid){
  var panel=document.getElementById(pid);if(!panel)return;
  var fine=['ok',''];
  for(var a in window.__viz.cy){var g=window.__viz.cy[a];
    if(!panel.contains(g.container()))continue;
    var anom=g.nodes().filter(function(n){return fine.indexOf(n.data('status')||'')<0;});
    if(!anom.length)return; /* nothing anomalous — dimming everything helps nobody */
    g.nodes().forEach(function(n){n.toggleClass('dim',fine.indexOf(n.data('status')||'')>=0);});
    g.edges().forEach(function(e){
      e.toggleClass('dim',e.source().hasClass('dim')||e.target().hasClass('dim'));});
    return;}
  var rows=panel.querySelectorAll('tr[data-status]');
  var hit=false;
  for(var i=0;i<rows.length;i++){
    if(fine.indexOf(rows[i].getAttribute('data-status'))<0)hit=true;}
  if(!hit)return;
  for(var j=0;j<rows.length;j++){
    rows[j].style.display=fine.indexOf(rows[j].getAttribute('data-status'))<0?'':'none';}
};
window.__viz.focus=function(pid,nid){
  showPanel(pid);
  var active=document.getElementById(pid);if(!active)return;
  for(var a in window.__viz.cy){var g=window.__viz.cy[a];
    if(active.contains(g.container())){
      g.elements().removeClass('focus');
      var n=g.getElementById(nid);
      if(n.length){n.addClass('focus');g.center(n);}
      break;}}
};
function linkGraph(id,targetPid){
  var cy=window.__viz.cy[id];if(!cy)return;
  cy.on('tap','node',function(ev){window.__viz.focus(targetPid,ev.target.id());});
}
function linkTable(id,targetPid){
  var tbl=document.getElementById(id+'_tbl');if(!tbl)return;
  tbl.addEventListener('click',function(ev){
    var t=ev.target;
    while(t&&t!==tbl&&!t.getAttribute('data-node'))t=t.parentNode;
    if(!t||t===tbl)return;
    var rows=tbl.tBodies[0].rows;
    for(var i=0;i<rows.length;i++){rows[i].classList.toggle('focus',rows[i]===t);}
    window.__viz.focus(targetPid,t.getAttribute('data-node'));
  });
}
function showPanel(pid){
  var ps=document.querySelectorAll('.panel');
  for(var i=0;i<ps.length;i++){ps[i].classList.toggle('active',ps[i].id===pid);}
  var ts=document.querySelectorAll('.tab');
  for(var j=0;j<ts.length;j++){
    var sel=ts[j].getAttribute('data-panel')===pid;
    ts[j].classList.toggle('sel',sel);
    ts[j].setAttribute('aria-selected',sel?'true':'false');
  }
  var active=document.getElementById(pid);if(!active)return;
  var fns=window.__viz.pending[pid];
  if(fns){delete window.__viz.pending[pid];
    for(var f=0;f<fns.length;f++){fns[f]();}}
  for(var a in window.__viz.cy){var g=window.__viz.cy[a];
    if(active.contains(g.container())){g.resize();}}
  for(var b in window.__viz.ec){var el=document.getElementById(b);
    if(el&&active.contains(el)){window.__viz.ec[b].resize();}}
  try{history.replaceState(null,'','#'+pid);}catch(e){}
}
function hashPanel(){
  var h=location.hash.slice(1);
  return h&&h.indexOf('panel-')===0&&document.getElementById(h)?h:null;
}
document.addEventListener('DOMContentLoaded',function(){
  var ts=document.querySelectorAll('[data-panel]');
  for(var i=0;i<ts.length;i++){ts[i].addEventListener('click',function(){
    var pid=this.getAttribute('data-panel');
    showPanel(pid);
    if(this.getAttribute('data-filter')==='anomaly'){window.__viz.filterAnomalies(pid);}
  });}
  var target=hashPanel();
  if(!target){var act=document.querySelector('.panel.active');target=act?act.id:null;}
  if(target){showPanel(target);}
});
window.addEventListener('hashchange',function(){
  var h=hashPanel();
  if(h){showPanel(h);}
});
(function(){
  var rt;
  window.addEventListener('resize',function(){
    clearTimeout(rt);
    rt=setTimeout(function(){
      var active=document.querySelector('.panel.active');
      for(var a in window.__viz.cy){var g=window.__viz.cy[a];
        if(!active||active.contains(g.container())){g.resize();}}
      for(var b in window.__viz.ec){var el=document.getElementById(b);
        if(el&&(!active||active.contains(el))){window.__viz.ec[b].resize();}}
    },150);
  });
})();
