// Tablas compactas: una vista y una familia de métricas a la vez.
function compactClassification(matches,teamList,sport,scope='all'){
 const rs=new Map(teamList.map(t=>[String(t.id),{...t,pj:0,pg:0,pe:0,pp:0,gf:0,gc:0,dg:0,pts:0,form:[]}])) ;
 const completed=matches.filter(m=>m.hs!==null&&m.aws!==null).sort((a,b)=>(a.date||'').localeCompare(b.date||'')||(a.round||0)-(b.round||0)||a.id-b.id);
 for(const m of completed){for(const [id,side,scored,conceded] of [[m.home,'home',m.hs,m.aws],[m.away,'away',m.aws,m.hs]]){
  if(scope!=='all'&&scope!==side)continue;
  const r=rs.get(String(id));if(!r)continue;
  r.pj++;r.gf+=scored;r.gc+=conceded;r.dg=r.gf-r.gc;
  const result=scored>conceded?'G':scored<conceded?'P':'E';r.form.push(result);
  if(result==='G'){r.pg++;r.pts+=sport==='Baloncesto'?2:3;}else if(result==='E'){r.pe++;r.pts++;}else{r.pp++;if(sport==='Baloncesto')r.pts++;}
 }}
 return [...rs.values()].sort((a,b)=>(a.group_no||0)-(b.group_no||0)||b.pts-a.pts||b.dg-a.dg||b.gf-a.gf||a.name.localeCompare(b.name));
}
function formBadges(results){return results.length?`<div class="recent-form">${results.slice(-5).map(x=>`<span class="form-${x}" title="${{G:'Ganado',E:'Empatado',P:'Perdido'}[x]}">${x}</span>`).join('')}</div>`:'<span class="muted">—</span>';}
function compactClassificationHTML(rs,offset=0){return table(['#','Equipo','PJ','G','E','P','GF:GC','DG','PTS','Forma'],rs.map((r,i)=>`<tr><td><span class="rank-number">${offset+i+1}</span></td><td>${badgeTeam(r.name)}${r.group_no?` <small class="group-chip">G${r.group_no}</small>`:''}</td><td>${r.pj}</td><td>${r.pg}</td><td>${r.pe}</td><td>${r.pp}</td><td>${r.gf}:${r.gc}</td><td>${r.dg>0?'+':''}${r.dg}</td><td class="points-cell">${r.pts}</td><td>${formBadges(r.form)}</td></tr>`));}
standings=function(){return `<div class="compact-stats">${compactClassificationHTML(compactClassification(data.matches.filter(m=>m.phase!=='Llave'),data.teams,data.tournament.sport))}</div>`;};
function statsViews(sport){const basket=sport==='Baloncesto';return {
 general:{label:'General',keys:[]},
 scoring:{label:basket?'Anotadores':'Goleadores',keys:[basket?'points':'goals']},
 assists:{label:'Asistencias',keys:['assists']},
 shots:{label:'Remates',keys:['shots','on_target']},
 discipline:{label:basket?'Faltas':'Tarjetas',keys:basket?['fouls']:['yellows','reds','cards']},
 penalties:{label:'Penales',keys:['penalties','penalties_scored','penalty_misses']},
 shootout:{label:'Tandas',keys:['shootout_taken','shootout_scored']},
 ...Object.fromEntries((basket?['rebounds','steals','turnovers','substitutions']:['fouls','tackles','big_misses','corners','offsides','saves','own_goals','substitutions']).map(k=>[k,{label:METRICS[k],keys:[k]}]))
 };}
function compactMetricLabel(k){return {cards:'Total tarjetas',penalty_misses:'Fallados'}[k]||METRICS[k]||k;}
function compactMetric(r,k){return k==='cards'?(r.yellows||0)+(r.reds||0):k==='penalty_misses'?(r.penalties||0)-(r.penalties_scored||0):r[k]||0;}
statisticsHTML=function(analyses,players,teams,sport){const choices=statsViews(sport);const keys=Object.keys(choices).filter(k=>sport!=='Baloncesto'||!['penalties','shootout'].includes(k));return `<section class="compact-stats"><div class="title-row"><div><p class="eyebrow">ESTADÍSTICAS</p><h2 id="stats-heading">Clasificación general</h2></div><button class="small" id="stats-reset">Restablecer filtros</button></div><nav class="stats-view-tabs" aria-label="Tipo de estadística">${['general','scoring','assists','shots','discipline'].map(k=>`<button data-stats-view="${k}" class="${k==='general'?'selected':''}">${choices[k].label}</button>`).join('')}</nav><div class="stats-filters"><label>Estadística<select id="stats-view">${keys.map(k=>`<option value="${k}">${choices[k].label}</option>`).join('')}</select></label><label id="stats-entity-label" hidden>Mostrar<select id="stats-entity"><option value="players">Jugadores</option><option value="teams">Equipos</option></select></label><label id="stats-scope-label">Condición<select id="stats-scope"><option value="all">General</option><option value="home">Local</option><option value="away">Visitante</option></select></label><label>Equipo<select id="stats-team"><option value="">Todos los equipos</option>${Object.entries(teams).map(([id,name])=>`<option value="${esc(id)}">${esc(name)}</option>`).join('')}</select></label><label class="stats-search-label">Buscar<input id="stat-search" placeholder="Nombre del equipo" aria-label="Buscar en la tabla"></label></div><div class="panel" id="statistics-players"></div><div class="stats-pagination"><span id="stats-count" class="muted"></span><div><button class="small" id="stats-prev">← Anterior</button><span id="stats-page"></span><button class="small" id="stats-next">Siguiente →</button></div></div><p class="hint" id="stats-note"></p></section>`;};
function scopedAnalyses(matches,scope){return matches.map(m=>{if(!m.analysis)return null;const a=m.analysis;if(scope==='all')return a;const tid=String(scope==='home'?m.home:m.away);return {...a,players:a.players.filter(p=>String(p.team_id)===tid),teams:Object.fromEntries(Object.entries(a.teams).filter(([id])=>id===tid))};}).filter(Boolean);}
bindStatistics=function(analyses,players,teams,sport,context=null){
 const views=statsViews(sport);let page=0;const pageSize=15;
 const isTournament=Boolean(context);const contextMatches=context?.matches||[];
 $('#stats-scope-label').hidden=!isTournament;
 const draw=()=>{
  const kind=$('#stats-view').value,view=views[kind],entity=$('#stats-entity').value;
  const scope=isTournament?$('#stats-scope').value:'all',team=$('#stats-team').value,q=$('#stat-search').value.trim().toLocaleLowerCase();
  const general=kind==='general';$('#stats-entity-label').hidden=general;
  $('#stat-search').placeholder=general||entity==='teams'?'Nombre del equipo':'Jugador o equipo';
  document.querySelectorAll('[data-stats-view]').forEach(b=>b.classList.toggle('selected',b.dataset.statsView===kind));
  let entries,headers,renderRows,note='';
  if(general&&isTournament){
   const elimination=context.format==='Eliminación directa';
   const games=contextMatches.filter(m=>elimination||m.phase!=='Llave');
   entries=compactClassification(games,context.teams,sport,scope).filter(r=>(!team||String(r.id)===team)&&r.name.toLocaleLowerCase().includes(q));
   $('#stats-heading').textContent=elimination?'Balance de partidos':'Clasificación';
   renderRows=(slice,offset)=>compactClassificationHTML(slice,offset);
   note=(elimination?'El avance en las llaves se decide por los cruces; esta tabla resume el rendimiento. ':'La clasificación incluye la liga o fase de grupos; excluye las llaves. ')+'Forma: últimos cinco resultados, de izquierda a derecha. G: ganado · E: empatado · P: perdido.';
  }else{
   const filtered=isTournament?scopedAnalyses(contextMatches,scope):analyses;
   const totals=statRows(filtered,players,teams);
   let keys=general?[sport==='Baloncesto'?'points':'goals','shots','cards']:view.keys;
   const teamMode=general||entity==='teams';
   entries=(teamMode?Object.entries(totals.teams).map(([id,r])=>({...r,id,name:teams[id]})):totals.players)
    .filter(r=>(!team||String(teamMode?r.id:r.team_id)===team)&&((r.name||'')+' '+(teamMode?'':teams[r.team_id])).toLocaleLowerCase().includes(q))
    .sort((a,b)=>compactMetric(b,kind==='discipline'&&sport!=='Baloncesto'?'cards':keys[0])-compactMetric(a,kind==='discipline'&&sport!=='Baloncesto'?'cards':keys[0])||a.name.localeCompare(b.name));
   headers=teamMode?['#','Equipo',...keys.map(compactMetricLabel)]:['#','Jugador','Equipo',...keys.map(compactMetricLabel)];
   renderRows=(slice,offset)=>table(headers,slice.map((r,i)=>`<tr><td><span class="rank-number">${offset+i+1}</span></td>${teamMode?`<td>${badgeTeam(r.name)}</td>`:`<td><span class="dorsal-chip">${r.number}</span><strong>${esc(r.name)}</strong></td><td>${esc(teams[r.team_id])}</td>`}${keys.map(k=>`<td class="metric-cell">${compactMetric(r,k)}</td>`).join('')}</tr>`));
   $('#stats-heading').textContent=general?'Resumen del partido':view.label+' · '+(teamMode?'Equipos':'Jugadores');
   note='Solo se muestran las columnas de la estadística seleccionada. Los valores corresponden a eventos registrados.';
   if(kind==='discipline')note+=' Una segunda amarilla también suma una expulsión.';
  }
  const pages=Math.max(1,Math.ceil(entries.length/pageSize));page=Math.min(page,pages-1);
  const offset=page*pageSize,slice=entries.slice(offset,offset+pageSize);
  $('#statistics-players').innerHTML=entries.length?renderRows(slice,offset):'<p class="empty">No hay resultados para estos filtros.</p>';
  $('#stats-count').textContent=entries.length?`${offset+1}–${Math.min(offset+pageSize,entries.length)} de ${entries.length}`:'0 resultados';
  $('#stats-page').textContent=`${page+1} / ${pages}`;$('#stats-prev').disabled=page===0;$('#stats-next').disabled=page>=pages-1;$('#stats-note').textContent=note;
 };
 const resetPage=()=>{page=0;draw();};
 for(const id of ['stats-view','stats-entity','stats-scope','stats-team'])$('#'+id).onchange=resetPage;
 $('#stat-search').oninput=resetPage;
 document.querySelectorAll('[data-stats-view]').forEach(b=>b.onclick=()=>{$('#stats-view').value=b.dataset.statsView;resetPage();});
 $('#stats-prev').onclick=()=>{page--;draw();};$('#stats-next').onclick=()=>{page++;draw();};
 $('#stats-reset').onclick=()=>{$('#stats-view').value='general';$('#stats-entity').value='players';$('#stats-scope').value='all';$('#stats-team').value='';$('#stat-search').value='';resetPage();};
 draw();
};
stats=function(){const teams=Object.fromEntries(data.teams.map(t=>[t.id,t.name])),analyses=data.matches.map(m=>m.analysis);$('#section').innerHTML=statisticsHTML(analyses,data.players,teams,data.tournament.sport);bindStatistics(analyses,data.players,teams,data.tournament.sport,{matches:data.matches,teams:data.teams,format:data.tournament.format});};

const readonlyRoster=roster;
roster=function(id){
 if(!editor()){readonlyRoster(id);return;}
 const ps=data.players.filter(p=>p.team_id===id).sort((a,b)=>a.number-b.number),locked=data.matches.length>0;
 if(!ps.length){addPlayersModal(id);return;}
 const positions=data.tournament.sport==='Baloncesto'?['Base','Escolta','Alero','Ala-pívot','Pívot']:['Portero','Defensa','Mediocampista','Delantero'];
 modal('Plantilla · '+teamName(id),`<p class="hint">Edita nombre, dorsal y posición. Los goles, tarjetas y partidos seguirán vinculados al mismo jugador.</p><div class="table-wrap roster-edit">${table(['Dorsal','Nombre del jugador','Posición'],ps.map((p,i)=>`<tr data-edit-player="${p.id}"><td><input aria-label="Dorsal del jugador ${i+1}" data-player-number type="number" min="0" max="99" value="${p.number}" required></td><td><input aria-label="Nombre del jugador ${i+1}" data-player-name value="${esc(p.name)}" minlength="2" maxlength="100" required></td><td><select aria-label="Posición del jugador ${i+1}" data-player-position>${positions.map(pos=>`<option ${pos===p.position?'selected':''}>${pos}</option>`).join('')}</select></td></tr>`))}</div>${true?'<button type="button" class="small" id="open-add-players">Agregar jugadores en bloque</button><p class="hint">Guarda las ediciones antes de abrir el registro de jugadores nuevos.</p>':''}`,async()=>{
  const players=[...document.querySelectorAll('[data-edit-player]')].map(row=>{const original=ps.find(p=>p.id===+row.dataset.editPlayer);return {id:original.id,name:row.querySelector('[data-player-name]').value.trim(),number:Number(row.querySelector('[data-player-number]').value),position:row.querySelector('[data-player-position]').value,original:{name:original.name,number:original.number,position:original.position}};});
  const used=new Map();for(const p of players){if(used.has(p.number))throw Error(`Dorsal ${p.number} repetido: ${used.get(p.number)} y ${p.name}.`);used.set(p.number,p.name);}
  await api(`/teams/${id}/players/edit`,{players});
 },'Guardar cambios');
 if($('#open-add-players'))$('#open-add-players').onclick=()=>{const changed=[...document.querySelectorAll('[data-edit-player]')].some(row=>{const p=ps.find(p=>p.id===+row.dataset.editPlayer);return row.querySelector('[data-player-name]').value!==p.name||+row.querySelector('[data-player-number]').value!==p.number||row.querySelector('[data-player-position]').value!==p.position;});if(changed){$('#form-error').textContent='Guarda tus cambios antes de agregar jugadores.';return;}$('#modal').close();addPlayersModal(id);};
};
