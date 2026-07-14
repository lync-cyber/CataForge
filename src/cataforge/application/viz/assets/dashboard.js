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
window.__viz.stateArr=function(k){
  var v=window.__viz.state[k];
  return Array.isArray(v)?v:[]; /* a corrupted persisted value must not crash init */
};
window.__viz.setIndex=function(entries){
  for(var i=0;i<entries.length;i++){
    entries[i].k=((entries[i].id||'')+' '+(entries[i].l||'')).toLowerCase();}
  window.__viz.entityIndex=entries;
};
function escHtml(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function closeInspector(){
  var box=document.getElementById('inspector');
  if(!box||box.hidden)return;
  box.hidden=true;
  var op=window.__viz._insOpener;
  window.__viz._insOpener=null;
  if(op&&op.focus){op.focus();}
}
window.__viz.inspect=function(d,srcDom){
  var box=document.getElementById('inspector');if(!box)return;
  /* remember the opener only on open, not on in-place re-render, so closing
     returns focus to where the user actually came from */
  if(box.hidden){window.__viz._insOpener=document.activeElement;}
  var h='<div class="ins-head"><strong>'+escHtml(d.label||d.id)+'</strong>'
    +'<button class="ins-close" aria-label="关闭">×</button></div>';
  if(d.status){h+='<div class="ins-status">'+escHtml(d.status)+'</div>';}
  var meta=d.meta||{};
  var rows='';
  for(var k in meta){
    rows+='<tr><th>'+escHtml(k)+'</th><td>'+escHtml(meta[k])+'</td></tr>';}
  if(rows){h+='<table class="ins-meta">'+rows+'</table>';}
  var idx=window.__viz.entityIndex||[];
  var cur=srcDom?srcDom.replace(/_v$/,''):null;
  var jumps='';
  for(var i=0;i<idx.length;i++){
    if(idx[i].id===d.id&&idx[i].p!==cur){
      jumps+='<button class="ins-jump" data-p="'+escHtml(idx[i].p)+'" data-n="'
        +escHtml(d.id)+'">'+escHtml(idx[i].p.slice(6))+'</button>';}}
  if(jumps){h+='<div class="ins-xref">在其他视图: '+jumps+'</div>';}
  box.innerHTML=h;box.hidden=false;
  box.focus();
  box.querySelector('.ins-close').addEventListener('click',closeInspector);
  var js=box.querySelectorAll('.ins-jump');
  for(var j=0;j<js.length;j++){js[j].addEventListener('click',function(){
    window.__viz.focus(this.getAttribute('data-p'),this.getAttribute('data-n'));});}
};
function vizTheme(){
  /* the CSS custom properties are the single colour source; the static
     fallbacks only cover environments without getComputedStyle support */
  var cs=getComputedStyle(document.documentElement);
  var v=function(name,fb){var x=cs.getPropertyValue(name).trim();return x||fb;};
  return{
    nodeFill:v('--viz-node-fill','#dfe6ee'),nodeBorder:v('--viz-node-border','#7f8fa6'),
    nodeLabel:v('--viz-node-label','#1f2d3d'),edge:v('--viz-edge','#848e9b'),
    muted:v('--muted','#637288'),canvas:v('--canvas','#fff'),
    accent:v('--accent','#36648b'),chipLine:v('--chip-line','#ccd2da')
  };
}
function graphStyle(){
  var t=vizTheme();
  return[{selector:'node',style:{'background-color':t.nodeFill,'border-color':t.nodeBorder,
    'border-width':1,'label':'data(label)','font-size':10,'text-valign':'center',
    'text-halign':'center','width':'label','height':'label','padding':'6px',
    'shape':'round-rectangle','color':t.nodeLabel}},
    {selector:'node[bg]',style:{'background-color':'data(bg)'}},
    {selector:'node[border]',style:{'border-color':'data(border)','border-width':2}},
    {selector:'edge',style:{'width':1,'line-color':t.edge,'target-arrow-color':t.edge,
    'target-arrow-shape':'triangle','curve-style':'bezier'}},
    {selector:'edge[label]',style:{'label':'data(label)',
    'font-size':8,'color':t.muted,'text-background-color':t.canvas,'text-background-opacity':1}},
    {selector:':parent',style:{'background-opacity':0.06,'background-color':t.accent,
    'border-color':t.chipLine,'border-width':1,'label':'data(label)','font-size':11,
    'color':t.muted,'text-valign':'top','text-halign':'center','padding':'10px',
    'shape':'round-rectangle'}},
    {selector:'.dim',style:{'opacity':0.12}},
    {selector:'.folded',style:{'display':'none'}},
    {selector:'.focus',style:{'border-width':3,'border-color':t.accent}}];
}
function initGraph(id,elements,opts){
  opts=opts||{};
  var compound=elements.some(function(e){return e.data&&e.data.parent;});
  var layout=compound
    ?{name:'cose',padding:14,fit:true,nodeDimensionsIncludeLabels:true,idealEdgeLength:60}
    :{name:'breadthfirst',directed:true,spacingFactor:1.1,padding:12,fit:true};
  var cy=cytoscape({container:document.getElementById(id),elements:elements,
    style:graphStyle(),
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
  cy.on('tap','node',function(ev){window.__viz.inspect(ev.target.data(),id);});
  var view=document.getElementById(id).closest('.view');
  if(view&&!view.classList.contains('cat-view')){
    /* layer folding: type chips hide whole node layers; catalogue chips keep
       their own dim-based semantics wired in initCatalogue */
    var tchips=view.querySelectorAll('.fchip[data-type]');
    var applyFold=function(save){
      var off=[];
      for(var i=0;i<tchips.length;i++){
        if(!tchips[i].classList.contains('on'))off.push(tchips[i].getAttribute('data-type'));}
      cy.batch(function(){
        cy.nodes().forEach(function(n){
          n.toggleClass('folded',off.indexOf(n.data('type')||'')>=0);});
        cy.edges().forEach(function(e){
          e.toggleClass('folded',e.source().hasClass('folded')||e.target().hasClass('folded'));});
      });
      if(save){window.__viz.saveState(id+':fold',off);}
    };
    var foldOffs=window.__viz.stateArr(id+':fold');
    for(var tc=0;tc<tchips.length;tc++){
      if(foldOffs.indexOf(tchips[tc].getAttribute('data-type'))>=0){
        tchips[tc].classList.remove('on');}
      tchips[tc].addEventListener('click',function(){
        this.classList.toggle('on');applyFold(true);});
    }
    if(foldOffs.length){applyFold(false);}
    var ms=view.querySelector('.modeswitch[data-target="'+id+'"]');
    if(ms){
      var applyMode=function(mode,save){
        var alt=view.querySelector('.alt-table');
        var cyEl=document.getElementById(id);
        if(!alt)return;
        var table=mode==='table';
        alt.hidden=!table;
        cyEl.style.display=table?'none':'';
        ms.textContent=table?'图形视图':'表格视图';
        if(!table){cy.resize();}
        if(save){window.__viz.saveState(id+':mode',mode);}
      };
      ms.addEventListener('click',function(){
        applyMode(document.getElementById(id).style.display==='none'?'graph':'table',true);});
      if(window.__viz.state[id+':mode']==='table'){applyMode('table',false);}
    }
  }
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
  if(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches){
    option.animation=false;
  }
  option.backgroundColor='transparent'; /* .chart's var(--canvas) is the surface */
  window.__viz.ecOpt=window.__viz.ecOpt||{};
  window.__viz.ecOpt[id]=option; /* kept for a live theme-change re-init */
  var c=echarts.init(document.getElementById(id),dark?'dark':null);
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
  var offs=window.__viz.stateArr(id+':off');
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
  var offs=window.__viz.stateArr(id+':off');
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
  /* ids are data, not selector syntax — match by attribute value, never by
     interpolating into a selector string */
  var rows=active.querySelectorAll('tr[data-node]');
  var row=null;
  for(var r=0;r<rows.length;r++){
    var hit=rows[r].getAttribute('data-node')===nid;
    rows[r].classList.toggle('focus',hit);
    if(hit){row=rows[r];}
  }
  if(row){
    row.setAttribute('tabindex','-1');
    row.scrollIntoView({block:'center'});
    row.focus();
  }
};
function syncTablists(){
  /* roving tabindex: per tablist, the selected tab (else the first) is the
     single tabbable entry point */
  var lists=document.querySelectorAll('[role="tablist"]');
  for(var i=0;i<lists.length;i++){
    var tabs=lists[i].querySelectorAll('[role="tab"]');
    var sel=-1;
    for(var j=0;j<tabs.length;j++){if(tabs[j].classList.contains('sel')){sel=j;break;}}
    for(var k=0;k<tabs.length;k++){
      tabs[k].setAttribute('tabindex',(sel>=0?k===sel:k===0)?'0':'-1');}
  }
}
function initTabKeyboard(){
  var lists=document.querySelectorAll('[role="tablist"]');
  for(var i=0;i<lists.length;i++){(function(list){
    list.addEventListener('keydown',function(ev){
      var delta={ArrowRight:1,ArrowLeft:-1};
      if(!(ev.key in delta)&&ev.key!=='Home'&&ev.key!=='End')return;
      var tabs=Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
      var idx=tabs.indexOf(document.activeElement);
      if(idx<0)return;
      ev.preventDefault();
      var next=ev.key==='Home'?0
        :ev.key==='End'?tabs.length-1
        :(idx+delta[ev.key]+tabs.length)%tabs.length;
      for(var t=0;t<tabs.length;t++){tabs[t].setAttribute('tabindex',t===next?'0':'-1');}
      tabs[next].focus();
    });
  })(lists[i]);}
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
  syncTablists();
  var active=document.getElementById(pid);if(!active)return;
  var fns=window.__viz.pending[pid];
  if(fns){delete window.__viz.pending[pid];
    for(var f=0;f<fns.length;f++){
      try{fns[f]();}
      catch(err){ /* one broken view must not blank its siblings in the panel */
        if(window.console){console.error('viz init failed for '+pid,err);}
      }
    }}
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
  initTabKeyboard();
  var ins=document.getElementById('inspector');
  if(ins){ins.addEventListener('keydown',function(ev){
    if(ev.key==='Escape'){closeInspector();}});}
  var omni=document.getElementById('omni');
  var list=document.getElementById('omni_list');
  var omniStatus=document.getElementById('omni_status');
  if(omni&&list){
    var hits=[],activeIdx=-1,ot;
    var announce=function(msg){if(omniStatus){omniStatus.textContent=msg;}};
    var setExpanded=function(open){
      list.hidden=!open;
      omni.setAttribute('aria-expanded',open?'true':'false');
      if(!open){activeIdx=-1;omni.removeAttribute('aria-activedescendant');}
    };
    var choose=function(e){
      setExpanded(false);omni.value='';
      window.__viz.focus(e.p,e.id);
    };
    var setActive=function(n){
      activeIdx=n;
      var opts=list.querySelectorAll('.omni-hit');
      for(var j=0;j<opts.length;j++){
        opts[j].classList.toggle('active',j===n);
        opts[j].setAttribute('aria-selected',j===n?'true':'false');
      }
      if(n>=0&&opts[n]){
        omni.setAttribute('aria-activedescendant',opts[n].id);
        opts[n].scrollIntoView({block:'nearest'});
      }else{omni.removeAttribute('aria-activedescendant');}
    };
    var renderHits=function(){
      list.innerHTML='';
      for(var j=0;j<hits.length;j++){(function(e,n){
        var d=document.createElement('div');
        d.className='omni-hit';
        d.id='omni_opt_'+n;
        d.setAttribute('role','option');
        d.setAttribute('aria-selected','false');
        d.textContent=e.l+' · '+e.p.slice(6);
        d.addEventListener('click',function(){choose(e);});
        list.appendChild(d);})(hits[j],j);}
      if(!hits.length){
        var empty=document.createElement('div');
        empty.className='omni-empty';
        empty.setAttribute('role','option');
        empty.setAttribute('aria-disabled','true');
        empty.textContent='无匹配实体';
        list.appendChild(empty);
      }
    };
    omni.addEventListener('input',function(){
      clearTimeout(ot);
      ot=setTimeout(function(){
        var q=omni.value.trim().toLowerCase();
        if(!q){list.innerHTML='';setExpanded(false);announce('');return;}
        var idx=window.__viz.entityIndex||[];
        hits=[];
        for(var i=0;i<idx.length&&hits.length<20;i++){
          if((idx[i].k||'').indexOf(q)>=0){hits.push(idx[i]);}}
        renderHits();
        setActive(-1);
        setExpanded(true);
        announce(hits.length?hits.length+' 个结果':'无匹配实体');
      },120);
    });
    omni.addEventListener('keydown',function(ev){
      if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){
        if(list.hidden||!hits.length)return;
        ev.preventDefault();
        var step=ev.key==='ArrowDown'?1:-1;
        setActive((activeIdx+step+hits.length)%hits.length);
      }else if(ev.key==='Enter'){
        if(!list.hidden&&hits.length){
          ev.preventDefault();
          choose(hits[activeIdx>=0?activeIdx:0]);
        }
      }else if(ev.key==='Escape'){
        if(!list.hidden){setExpanded(false);}
        else if(omni.value){omni.value='';announce('');}
      }
    });
    document.addEventListener('click',function(ev){
      if(ev.target!==omni&&!list.contains(ev.target)){setExpanded(false);}});
  }
  var target=hashPanel();
  if(!target){var act=document.querySelector('.panel.active');target=act?act.id:null;}
  if(target){showPanel(target);}
  syncTablists();
});
window.addEventListener('hashchange',function(){
  var h=hashPanel();
  if(h){showPanel(h);}
});
(function(){
  if(!window.matchMedia)return;
  var mq=window.matchMedia('(prefers-color-scheme: dark)');
  var reskin=function(){
    var gs=graphStyle();
    for(var a in window.__viz.cy){window.__viz.cy[a].style(gs);}
    var opts=window.__viz.ecOpt||{};
    for(var b in window.__viz.ec){
      var el=document.getElementById(b);
      if(!el||!opts[b])continue;
      window.__viz.ec[b].dispose();
      var c=echarts.init(el,mq.matches?'dark':null);
      c.setOption(opts[b]);
      window.__viz.ec[b]=c;
    }
  };
  if(mq.addEventListener){mq.addEventListener('change',reskin);}
  else if(mq.addListener){mq.addListener(reskin);}
})();
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
