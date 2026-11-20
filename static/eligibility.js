// Elegibilidad calculada justo antes de cada evento, no al final del partido.
function eventEligibility(players,sport,state,events){
 const active=new Set(Object.values(state.lineups||{}).flat().map(Number)),called=new Set(Object.values(state.squads||{}).flat().map(Number)),removed=new Set(),expelled=new Set(),yellow={},fouls={};
 for(const e of events){const id=Number(e.player);if(!active.has(id))continue;
  if(e.type==='Sustitución'){const incoming=Number(e.incoming),a=players.find(p=>p.id===id),b=players.find(p=>p.id===incoming);if(called.has(incoming)&&!active.has(incoming)&&!expelled.has(incoming)&&String(a?.team_id)===String(b?.team_id)&&(!['Fútbol 11','Fútbol 7'].includes(sport)||!removed.has(incoming))){active.delete(id);removed.add(id);active.add(incoming);}}
  if(e.type==='Amarilla')yellow[id]=(yellow[id]||0)+1;
  if(e.type==='Falta')fouls[id]=(fouls[id]||0)+1;
  if(e.type==='Roja'||yellow[id]>=2||(sport==='Baloncesto'&&fouls[id]>=5)){active.delete(id);expelled.add(id);}
 }
 return {active,called,removed,expelled};
}
const appendUnfilteredEvent=appendEvent;
appendEvent=function(container,players,sport,event={}){
 const row=appendUnfilteredEvent(container,players,sport,event),grid=row.querySelector('.event-grid');
 const label=document.createElement('label');label.textContent='Equipo';const team=document.createElement('select');team.className='event-team';label.append(team);
 const teams=[...new Set(players.map(p=>String(p.team_id)))];team.innerHTML=teams.map(id=>`<option value="${esc(id)}">${esc(players.find(p=>String(p.team_id)===id)?.team_name|| (typeof liveData!=='undefined'&&liveData?.teams?.[id]) || teamName(Number(id)))}</option>`).join('');
 const author=players.find(p=>p.id===event.player);if(author)team.value=String(author.team_id);grid.insertBefore(label,row.querySelector('.player').parentElement);
 const note=document.createElement('p');note.className='hint event-eligibility-hint';grid.after(note);
 function refresh(){
  const rows=[...container.querySelectorAll('.event-editor')];
  rows.forEach((r,index)=>{
   const stamp=x=>Number(x.querySelector('.minute').value)*60+Number(x.querySelector('.second').value);
   let state,previous;
   if(container.id==='single-event'){const leg=liveData.legs[liveLeg];state=leg;previous=leg.events.filter(e=>e.minute*60+(e.second||0)<=stamp(r));}
   else {state=readLineup();previous=rows.map((x,i)=>({x,i})).filter(({x,i})=>stamp(x)<stamp(r)||(stamp(x)===stamp(r)&&i<index)).sort((a,b)=>stamp(a.x)-stamp(b.x)||a.i-b.i).map(({x})=>({player:Number(x.querySelector('.player').value),incoming:Number(x.querySelector('.incoming').value),type:x.querySelector('.type').value}));}
   const eligible=eventEligibility(players,sport,state,previous),tid=r.querySelector('.event-team').value;
   function fill(select,list){const old=select.value;select.innerHTML='<option value="">Selecciona jugador</option>'+list.map(p=>`<option value="${p.id}">#${p.number} ${esc(p.name)}</option>`).join('');select.value=list.some(p=>String(p.id)===old)?old:'';select.required=true;}
   const own=players.filter(p=>String(p.team_id)===tid);
   fill(r.querySelector('.player'),own.filter(p=>eligible.active.has(p.id)));
   const sub=r.querySelector('.type').value==='Sustitución';
   fill(r.querySelector('.incoming'),own.filter(p=>eligible.called.has(p.id)&&!eligible.active.has(p.id)&&!eligible.expelled.has(p.id)&&(!['Fútbol 11','Fútbol 7'].includes(sport)||!eligible.removed.has(p.id))));
   r.querySelector('.incoming').required=sub;r.querySelector('.incoming').disabled=!sub;
   r.querySelector('.event-eligibility-hint').textContent=sub?'Sale: jugador en cancha. Entra: suplente de este equipo. Si falta un suplente, márcalo como Convocado arriba, sin marcarlo Titular.':'Solo aparecen jugadores de este equipo que están en cancha en este minuto.';
  });
 }
 // Conservar la selección original solo si sigue siendo válida.
 if(!event.player)row.querySelector('.player').value='';
 row.querySelector('.remove-event').addEventListener('click',refresh);
 if(!container._eligibilityBound){container.addEventListener('input',()=>container._refreshEligibility());container.addEventListener('change',()=>container._refreshEligibility());container._eligibilityBound=true;const form=container.closest('form');form?.addEventListener('change',e=>{if(e.target.matches('[data-called],[data-starter]'))container._refreshEligibility();});}
 container._refreshEligibility=refresh;refresh();return row;
};
const readUnsortedEvents=readEvents;
readEvents=function(){return readUnsortedEvents().sort((a,b)=>(a.minute*60+a.second)-(b.minute*60+b.second));};
