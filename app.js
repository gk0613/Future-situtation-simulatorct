let zones = [
  {name:"Entrance", capacity:120, people:35},
  {name:"Central Hall", capacity:160, people:55},
  {name:"Exit Area", capacity:100, people:25}
];
let lastPayload = null, lastResult = null, lastSimulationId = null, animationId = null;

const $ = id => document.getElementById(id);

function escapeHtml(s){return String(s).replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));}
function renderZones(){
  $("zones").innerHTML = zones.map((z,i)=>`
    <div class="zone-card">
      <div class="zhead"><strong>Zone ${i+1}</strong>${zones.length>1?`<button type="button" class="remove" onclick="removeZone(${i})">Remove</button>`:""}</div>
      <input data-i="${i}" data-k="name" value="${escapeHtml(z.name)}" placeholder="Zone name">
      <input data-i="${i}" data-k="capacity" type="number" min="1" value="${z.capacity}" placeholder="Capacity">
      <input data-i="${i}" data-k="people" type="number" min="0" value="${z.people}" placeholder="Initial people">
    </div>`).join("");
  document.querySelectorAll("#zones input").forEach(el=>{
    el.addEventListener("input", e=>{
      const i=+e.target.dataset.i, k=e.target.dataset.k;
      zones[i][k] = k==="name" ? e.target.value : Math.max(0, +e.target.value || 0);
      if(k === "capacity") zones[i].people = Math.min(zones[i].people, Math.max(1, zones[i].capacity));
    });
  });
}
function removeZone(i){zones.splice(i,1);renderZones();}
function getPayload(){
  return {
    space_name:$('spaceName').value.trim(),
    simulation_time:+$('simTime').value,
    arrival_rate:+$('arrivalRate').value,
    exit_rate:+$('exitRate').value,
    emergency:$('emergency').checked,
    zones:zones.map(z=>({name:z.name,capacity:+z.capacity,people:+z.people}))
  };
}
async function api(url, options={}){
  const res=await fetch(url, options);
  if(res.status===401){window.location.href='/login';return null;}
  const data=await res.json();
  if(!data.ok) throw new Error(data.error||'Request failed');
  return data;
}
async function runSimulation(payload=getPayload()){
  const data=await api('/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!data)return;
  lastPayload=payload; lastResult=data.result; lastSimulationId=data.simulation_id;
  renderResult(data.result);
  $('savedMessage').textContent=`Saved to Simulation History • Record #${data.simulation_id}`;
  animate(data.result);
  refreshHistory();
}
function riskClass(r){return 'risk-'+r.toLowerCase()}
function pill(r){return `<span class="pill ${r.toLowerCase()}">${r}</span>`}
function renderResult(r){
  $('results').classList.remove('hidden');
  $('resultTitle').textContent=`${r.space_name} — Simulation Results`;
  $('stats').innerHTML=[
    ['Final Crowd',r.timeline.at(-1).total_people],['Peak Crowd',r.peak_total_people],['Final Density',r.final_density+'%'],['Peak Density',r.peak_density+'%'],['Overall Risk',`<span class="${riskClass(r.overall_risk)}">${r.overall_risk}</span>`]
  ].map(x=>`<div class="stat ${x[0]==='Overall Risk'?'risk':''}"><small>${x[0]}</small><strong>${x[1]}</strong></div>`).join('');
  $('riskTable').innerHTML=`<table><thead><tr><th>Zone</th><th>People</th><th>Capacity</th><th>Density</th><th>Risk</th><th>Peak</th></tr></thead><tbody>${r.final_zones.map((z,i)=>`<tr><td><b>${escapeHtml(z.name)}</b></td><td>${z.people}</td><td>${z.capacity}</td><td>${z.density}%</td><td>${pill(z.risk)}</td><td>${r.peak_by_zone[i].peak_density}%</td></tr>`).join('')}</tbody></table>`;
  $('bottlenecks').innerHTML=r.bottlenecks.length?r.bottlenecks.map((b,i)=>`<div class="b-item"><div><strong>#${i+1} ${escapeHtml(b.name)}</strong><small>Peak density ${b.peak_density}%</small></div>${pill(b.severity)}</div>`).join(''):`<p class="muted">No zone crossed the 80% bottleneck threshold.</p>`;
  $('emergencyPanel').innerHTML=r.emergency?`<div class="panel-head"><h3>Emergency Analysis</h3><span>Activated</span></div><p>Emergency conditions begin around <b>minute ${r.emergency_step}</b>. The model increases incoming pressure, reduces exit flow and lowers inter-zone movement efficiency.</p><p class="muted">This is a simulation assumption for demonstration, not a real-world emergency prediction.</p>`:'';
  drawTimeline(r);
}
function drawTimeline(r){
  const c=$('timelineCanvas'),ctx=c.getContext('2d'),w=c.width,h=c.height; ctx.clearRect(0,0,w,h); ctx.strokeStyle='#dce2ec';ctx.fillStyle='#667085';ctx.font='12px Segoe UI';
  for(let i=0;i<5;i++){let y=35+i*(h-70)/4;ctx.beginPath();ctx.moveTo(45,y);ctx.lineTo(w-20,y);ctx.stroke();ctx.fillText(Math.round(120-i*30)+'%',5,y+4)}
  const max=120,pts=r.timeline;ctx.beginPath();pts.forEach((p,i)=>{let x=45+i*(w-65)/(pts.length-1),y=h-35-(Math.min(max,p.overall_density)/max)*(h-70);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.strokeStyle='#2457d6';ctx.lineWidth=3;ctx.stroke();ctx.fillStyle='#14213d';ctx.font='bold 13px Segoe UI';ctx.fillText('Overall density over time',55,22);
}
function animate(r){
  cancelAnimationFrame(animationId);
  const c=$('crowdCanvas'),ctx=c.getContext('2d'),w=c.width,h=c.height;
  let start=performance.now(),duration=9000;

  function riskColor(risk){
    if(risk==='LOW') return '#49a447';
    if(risk==='MEDIUM') return '#e4b63c';
    if(risk==='HIGH') return '#ef8d2f';
    return '#d83d4d';
  }

  function frame(now){
    const progress=Math.min(1,(now-start)/duration);
    const idx=Math.min(r.timeline.length-1,Math.floor(progress*(r.timeline.length-1)));
    const snap=r.zone_history[idx], t=r.timeline[idx];
    $('clock').textContent=`t = ${t.time} min`;
    ctx.clearRect(0,0,w,h);

    const gap=16, margin=22, top=55, bottom=55;
    const zw=(w-margin*2-gap*(snap.length-1))/snap.length;
    const zh=250;

    snap.forEach((z,i)=>{
      const x=margin+i*(zw+gap), y=top;
      const density=Math.max(0,Math.min(100,Number(z.density)||0));
      const fillH=(density/100)*(zh-18);
      const color=riskColor(z.risk);

      // Neutral zone background — risk color is used only for the occupied crowd level.
      ctx.fillStyle='#edf1f7';
      ctx.beginPath();
      ctx.roundRect(x,y,zw,zh,16);
      ctx.fill();

      // Crowd level: height directly follows the zone density.
      if(fillH>0){
        ctx.fillStyle=color;
        ctx.beginPath();
        ctx.roundRect(x+8,y+zh-8-fillH,zw-16,fillH,12);
        ctx.fill();
      }

      // Zone name
      ctx.textAlign='center';
      ctx.fillStyle='#14213d';
      ctx.font='bold 14px Segoe UI';
      ctx.fillText(z.name,x+zw/2,30);

      // People count — use dark text when the filled area is too small.
      ctx.fillStyle=density>=55?'#fff':'#14213d';
      ctx.font='bold 15px Segoe UI';
      ctx.fillText(z.people,x+zw/2,y+zh/2);

      // Density + risk label
      ctx.fillStyle=color;
      ctx.font='bold 11px Segoe UI';
      ctx.fillText(`${z.density}% • ${z.risk}`,x+zw/2,y+zh+22);
    });

    ctx.textAlign='left';
    ctx.fillStyle='#667085';
    ctx.font='12px Segoe UI';
    ctx.fillText(`Total crowd: ${t.total_people}   |   Overall: ${t.overall_density}%`,22,h-15);

    if(progress<1) animationId=requestAnimationFrame(frame);
  }

  animationId=requestAnimationFrame(frame);
}
async function compare(){
  if(!lastPayload) await runSimulation();
  const base=lastPayload,b={...base,arrival_rate:+$('testArrival').value,exit_rate:+$('testExit').value,simulation_time:+$('testTime').value,emergency:$('testEmergency').checked};
  const data=await api('/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario_a:base,scenario_b:b})});if(!data)return;const c=data.comparison;$('comparison').classList.remove('hidden');
  $('comparison').innerHTML=`<strong>${c.message}</strong><div class="compare-grid"><div class="compare-card"><b>Scenario A — Baseline</b><p>Final density: <strong>${data.scenario_a.final_density}%</strong></p><p>Peak density: <strong>${data.scenario_a.peak_density}%</strong></p><p>Risk: ${pill(data.scenario_a.overall_risk)}</p></div><div class="compare-card"><b>Scenario B — Intervention</b><p>Final density: <strong>${data.scenario_b.final_density}%</strong></p><p>Peak density: <strong>${data.scenario_b.peak_density}%</strong></p><p>Risk: ${pill(data.scenario_b.overall_risk)}</p></div></div><p class="muted">Final-density difference (A − B): <b>${c.density_change} percentage points</b> • Peak-density difference (A − B): <b>${c.peak_density_change} percentage points</b></p>`;
}
async function refreshHistory(){
  const data=await api('/api/history');if(!data)return;const rows=data.history;$('historyTable').innerHTML=rows.length?`<div class="history-scroll"><table><thead><tr><th>Date</th><th>Space</th><th>Risk</th><th>Final Density</th><th>Peak Density</th><th>Peak Crowd</th><th>Bottlenecks</th><th>Action</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${escapeHtml(row.created_at)}</td><td><b>${escapeHtml(row.space_name)}</b></td><td>${pill(row.overall_risk)}</td><td>${row.final_density}%</td><td>${row.peak_density}%</td><td>${row.peak_total_people}</td><td>${row.bottleneck_count}</td><td><button type="button" class="small-btn" onclick="viewHistory(${row.id})">View</button> <button type="button" class="small-btn danger" onclick="deleteHistory(${row.id})">Delete</button></td></tr>`).join('')}</tbody></table></div>`:`<div class="empty-history"><strong>No simulations yet.</strong><p>Run your first simulation and it will appear here automatically.</p></div>`;
}
async function viewHistory(id){
  const data=await api(`/api/history/${id}`);if(!data)return;lastPayload=data.simulation.payload;lastResult=data.simulation.result;lastSimulationId=id;renderResult(lastResult);$('savedMessage').textContent=`Loaded from Simulation History • Record #${id} • ${data.simulation.created_at}`;animate(lastResult);$('results').scrollIntoView({behavior:'smooth',block:'start'});
}
async function deleteHistory(id){
  if(!confirm('Delete this simulation history record?'))return;await api(`/api/history/${id}`,{method:'DELETE'});refreshHistory();
}
$('addZone').onclick=()=>{if(zones.length<12){zones.push({name:`Zone ${zones.length+1}`,capacity:100,people:20});renderZones();}};
$('runBtn').onclick=()=>runSimulation().catch(e=>alert(e.message));
$('compareBtn').onclick=()=>compare().catch(e=>alert(e.message));
$('historyBtn').onclick=()=>{$('historyPanel').classList.toggle('hidden');refreshHistory().catch(e=>alert(e.message));};
$('refreshHistoryBtn').onclick=()=>refreshHistory().catch(e=>alert(e.message));
$('downloadBtn').onclick=async()=>{if(!lastPayload)return;const res=await fetch('/report.csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(lastPayload)});if(res.status===401){location.href='/login';return;}const blob=await res.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='future_situation_simulator_report.csv';a.click();URL.revokeObjectURL(a.href);};
$('demoBtn').onclick=()=>{zones=[{name:'Entrance',capacity:120,people:35},{name:'Main Hall',capacity:140,people:65},{name:'Exit Zone',capacity:90,people:25},{name:'Food Court',capacity:110,people:45}];$('spaceName').value='College Tech Fest';$('simTime').value=40;$('arrivalRate').value=16;$('exitRate').value=8;$('emergency').checked=false;renderZones();runSimulation().catch(e=>alert(e.message));};
renderZones();
