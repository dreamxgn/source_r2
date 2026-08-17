const state = { data:null, active:"device" };
const $ = s => document.querySelector(s);

async function request(path, options={}) {
  const response = await fetch(path, {headers:{"Content-Type":"application/json"}, ...options});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Request failed");
  return body;
}

async function load({scrollTop=0}={}) {
  state.data = await request("/api/v1/config");
  $("#vehicle").textContent = state.data.device.car;
  updateHome();
  renderNav(); renderPanel(scrollTop);
}

function renderNav() {
  const entries = [{id:"device",label:"Device"},{id:"network",label:"Network"},...state.data.groups,{id:"software",label:"Software"}];
  $("#nav").innerHTML = entries.map(x => `<button class="nav-button ${x.id===state.active?'active':''}" data-panel="${x.id}">${x.label}</button>`).join("");
  document.querySelectorAll("[data-panel]").forEach(b => b.onclick=()=>{state.active=b.dataset.panel;renderNav();renderPanel();});
}

function renderPanel(scrollTop=0) {
  if (state.active === "device") return renderDevice();
  if (state.active === "network") return renderLabels([["IP Address",location.hostname],["Web UI Port",location.port||"80"]]);
  if (state.active === "software") return renderLabels([["Version",state.data.device.version],["Branch",state.data.device.branch]]);
  const group = state.data.groups.find(g=>g.id===state.active);
  $("#panel").innerHTML = group.controls.filter(visible).map(renderControl).join("");
  bindControls();
  const panel=$("#panel");
  panel.scrollTop=scrollTop;
  requestAnimationFrame(()=>{panel.scrollTop=scrollTop});
}

function visible(c) {
  if (c.key && state.data.states[c.key] && !state.data.states[c.key].visible) return false;
  return !c.visibleWhen || state.data.values[c.visibleWhen[0]] === c.visibleWhen[1];
}

function renderControl(c) {
  if (c.section) return `<div class="section">${c.section}</div>`;
  if (c.action) return `<div class="control"><div class="control-line"><button class="title">${c.title}</button><button class="action" data-action="${c.action}">${c.button}</button></div></div>`;
  const value = state.data.values[c.key] ?? "0", disabled = state.data.states[c.key]?.enabled===false;
  let widget="";
  if(c.type==="toggle") widget=`<button class="toggle ${value==='1'?'on':''}" aria-label="${c.title}" data-key="${c.key}" data-value="${value==='1'?'0':'1'}"></button>`;
  if(c.type==="choice") widget=`<div class="choices">${c.choices.map((x,i)=>`<button class="choice ${String(i)===value?'selected':''}" data-key="${c.key}" data-value="${i}">${x}</button>`).join('')}</div>`;
  if(c.type==="number") { const n=Number(value)||0,label=n===0&&c.zeroText?c.zeroText:`${n}${c.suffix||''}`; widget=`<div class="stepper"><button data-key="${c.key}" data-value="${Math.max(c.min,n-c.step)}">−</button><span>${label}</span><button data-key="${c.key}" data-value="${Math.min(c.max,n+c.step)}">+</button></div>`; }
  return `<div class="control ${disabled?'disabled':''}"><div class="control-line"><button class="title">${c.title}</button>${widget}</div>${c.description?`<div class="description">${c.description}</div>`:''}</div>`;
}

function bindControls() {
  document.querySelectorAll(".control .title").forEach(x=>x.onclick=()=>x.closest(".control").classList.toggle("open"));
  document.querySelectorAll("[data-key]").forEach(x=>x.onclick=async()=>{const scrollTop=$("#panel").scrollTop;try{await request(`/api/v1/params/${encodeURIComponent(x.dataset.key)}`,{method:"PUT",body:JSON.stringify({value:x.dataset.value})});await load({scrollTop});}catch(e){alert(e.message)}});
  document.querySelectorAll("[data-action]").forEach(x=>x.onclick=()=>confirmAction(x.dataset.action,x.closest(".control").querySelector(".title").textContent));
}

function renderDevice() {
  const d=state.data.device;
  $("#panel").innerHTML=`<div class="device-grid"><div class="label-row"><span>Dongle ID</span><span>${d.dongleId}</span></div><div class="label-row"><span>Serial</span><span>${d.serial}</span></div><div class="control"><div class="control-line"><button class="title">Reset Calibration</button><button class="action" data-action="reset-calibration">RESET</button></div><div class="description">Reset calibration only when the device mounting position has changed.</div></div><div class="power"><button data-action="reboot">Reboot</button><button class="danger" data-action="poweroff">Power Off</button></div></div>`;
  bindControls();
}

function renderLabels(rows){$("#panel").innerHTML=rows.map(r=>`<div class="label-row"><span>${r[0]}</span><span>${r[1]}</span></div>`).join('')}

function updateHome(){
  const d=state.data.device;
  $("#home-device-name").textContent=d.name;
  $("#home-version").textContent=`${d.version} / ${d.branch}`;
  $("#home-car").textContent=d.car;
  $("#home-state-text").textContent=d.onroad?"ONROAD":"OFFROAD";
  $("#home-state-dot").classList.toggle("onroad",d.onroad);
  $("#home-status-value").textContent=d.engaged?"openpilot engaged":d.onroad?"Driving":"Ready to drive";
  $("#network-type").textContent=d.networkType;
  document.querySelectorAll("#network-strength i").forEach((bar,index)=>bar.classList.toggle("active",index<d.networkStrength));
  const temperature=value=>value==null?"N/A":`${Math.round(value)}°C`;
  const percent=value=>value==null?"N/A":`${Math.round(value)}%`;
  $("#cpu-temp").textContent=temperature(d.cpuTempC);
  $("#gpu-temp").textContent=temperature(d.gpuTempC);
  $("#memory-use").textContent=percent(d.memoryPercent);
  $("#storage-use").textContent=percent(d.storagePercent);
  $("#vehicle-state").textContent=d.car==="[AUTO SELECT]"?"OFFLINE":"ONLINE";
  document.querySelectorAll(".sidebar-metric").forEach(metric=>metric.classList.remove("warning","danger"));
  [["#cpu-temp",d.cpuTempC],["#gpu-temp",d.gpuTempC]].forEach(([selector,value])=>{if(value>=90)$(selector).closest(".sidebar-metric").classList.add("danger");else if(value>=80)$(selector).closest(".sidebar-metric").classList.add("warning")});
}

function showHome(){ $("#app").hidden=true; $("#home-view").hidden=false; }
function showSettings(panel=state.active){ $("#home-view").hidden=true; $("#app").hidden=false; state.active=panel; renderNav(); renderPanel(); }

async function confirmAction(action,title){if(!confirm(`Are you sure you want to ${title.toLowerCase()}?`))return;try{await request(`/api/v1/actions/${action}`,{method:"POST",body:"{}"});await load()}catch(e){alert(e.message)}}

$("#vehicle").onclick=()=>{
  if(!state.data)return;
  const cars=["[AUTO SELECT]",...state.data.device.cars], dialog=$("#dialog");
  $("#dialog-title").textContent="Select a vehicle";
  $("#dialog-body").innerHTML=`<div class="vehicle-list">${cars.map((car,i)=>`<button type="button" class="vehicle-option ${car===state.data.device.car?'selected':''}" data-car-index="${i}">${car}</button>`).join('')}</div>`;
  document.querySelectorAll("[data-car-index]").forEach(button=>button.onclick=async()=>{const i=Number(button.dataset.carIndex);try{await request("/api/v1/actions/select-car",{method:"POST",body:JSON.stringify({value:i===0?"":cars[i]})});dialog.close();await load()}catch(e){alert(e.message)}});
  dialog.showModal();
};
$("#home-button").onclick=showHome;
$("#settings-button").onclick=()=>showSettings();
$("#home-toggles").onclick=()=>showSettings("toggles");
$("#home-device").onclick=()=>showSettings("device");

function showLoadError(error){
  $("#panel").innerHTML=`<div class="loading">Unable to load settings.<br><small>${error.message}</small><br><button class="retry">Retry</button></div>`;
  $(".retry").onclick=()=>load().catch(showLoadError);
}
load().catch(showLoadError);
