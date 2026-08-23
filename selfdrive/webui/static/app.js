const state = { data:null, active:"device", videoEnabled:localStorage.getItem("roadVideoEnabled")==="1", videoStreaming:false };
const $ = s => document.querySelector(s);
const EMPTY_IMAGE = "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";

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
  if (state.active === "software") return renderSoftware();
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

function renderSoftware(){
  const d=state.data.device;
  $("#panel").innerHTML=`<div class="device-grid"><div class="label-row"><span>Version</span><span>${d.version}</span></div><div class="label-row"><span>Branch</span><span>${d.branch}</span></div><div class="control"><div class="control-line"><button class="title">Pull Latest Update</button><button class="action danger" data-action="pull-update">PULL</button></div><div class="description">Force tracked files to match the current branch upstream. Local tracked changes will be lost. Git LFS content will not be downloaded.</div></div></div>`;
  bindControls();
}

function updateHome(){
  const d=state.data.device;
  $("#home-device-name").textContent=d.name;
  $("#home-version").textContent=`${d.version} / ${d.branch}`;
  $("#home-car").textContent=d.car;
  $("#home-state-text").textContent=d.onroad?"ONROAD":"OFFROAD";
  $("#home-state-dot").classList.toggle("onroad",d.onroad);
  const driving=state.data.driving,isMetric=state.data.values.IsMetric==="1",speedFactor=isMetric?1:0.621371,unit=isMetric?"km/h":"mph";
  const speed=value=>value==null?"--":String(Math.round(value*speedFactor));
  $("#current-speed").textContent=speed(driving.speedKph);
  $("#set-speed").textContent=speed(driving.setSpeedKph);
  document.querySelectorAll(".speed-unit").forEach(x=>x.textContent=unit);
  $("#drive-state").textContent=driving.status;
  $("#drive-state").className=`drive-state ${driving.status.toLowerCase()}`;
  const eventTitle=$("#event-title"),eventDetail=$("#event-detail"),eventBox=$("#event-overview");
  const humanize=value=>value.replace(/([a-z])([A-Z])/g,"$1 $2").replace(/^./,x=>x.toUpperCase());
  eventTitle.textContent=driving.alertText1||driving.events.map(humanize).join(" · ")||"No active alerts";
  eventDetail.textContent=driving.alertText2||(driving.available?"System operating normally":"Waiting for vehicle data");
  eventBox.classList.toggle("active",Boolean(driving.alertText1||driving.alertText2||driving.events.length));
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
  const calibration=state.data.calibration;
  $("#calibration-status").textContent=calibration.status;
  $(".calibration-track span").style.width=`${calibration.progress}%`;
  const angle=(value,positive,negative)=>value==null?"N/A":`${Math.abs(value).toFixed(2)}° ${value>0?positive:negative}`;
  $("#calibration-pitch").textContent=`Pitch: ${angle(calibration.pitchDeg,"down","up")}`;
  $("#calibration-yaw").textContent=`Yaw: ${angle(calibration.yawDeg,"left","right")}`;
  const adjustment=$("#calibration-adjustment"),directions={left:"← left",right:"right →",up:"↑ up",down:"↓ down"};
  adjustment.hidden=calibration.adjustment.length===0;
  adjustment.textContent=calibration.adjustment.length?`Adjust device ${calibration.adjustment.map(x=>directions[x]).join(" and ")}`:"";
  updateRoadVideo();
  updateHomeModes();
}

function updateRoadVideo(){
  const video=$("#road-video"),placeholder=$("#road-video-placeholder"),status=$("#road-video-status"),toggle=$("#road-video-toggle");
  const homeVisible=!$("#home-view").hidden,shouldStream=state.videoEnabled&&state.data?.device.onroad&&!document.hidden&&homeVisible;
  toggle.checked=state.videoEnabled;
  if(shouldStream&&!state.videoStreaming){
    state.videoStreaming=true;
    video.hidden=false;placeholder.hidden=true;status.textContent="Connecting…";
    video.src=`/api/v1/road-camera.mjpeg?t=${Date.now()}`;
  }else if(!shouldStream&&state.videoStreaming){
    state.videoStreaming=false;
    video.src=EMPTY_IMAGE;video.hidden=true;placeholder.hidden=false;
  }
  if(!state.videoEnabled){status.textContent="Video off";placeholder.textContent="Turn on video to view the road camera"}
  else if(!state.data?.device.onroad){status.textContent="Waiting for onroad";placeholder.textContent="Road video is available while driving"}
  else if(!shouldStream){status.textContent="Paused";placeholder.textContent="Video paused while this page is hidden"}
}

function updateHomeModes(){
  $(".home-mode-controls").hidden=!state.data.homeModeControlsVisible;
  if(!state.data.homeModeControlsVisible)return;
  const modes=[
    {key:"LongitudinalPersonality",labels:["Aggressive","Standard","Relaxed"],value:"#driving-mode-value",options:"#driving-mode-options"},
    {key:"dp_long_accel_profile",labels:["OP","ECO","NOR","SPT"],value:"#accel-mode-value",options:"#accel-mode-options"},
  ];
  modes.forEach(mode=>{
    const value=state.data.values[mode.key]??"0",index=Number(value),enabled=state.data.states[mode.key]?.enabled!==false;
    $(mode.value).textContent=mode.labels[index]??mode.labels[0];
    document.querySelectorAll(`${mode.options} [data-home-value]`).forEach(button=>{
      button.classList.toggle("selected",button.dataset.homeValue===value);
      button.disabled=!enabled;
    });
  });
}

document.querySelectorAll("[data-home-key]").forEach(button=>button.onclick=async()=>{
  const key=button.dataset.homeKey,value=button.dataset.homeValue,previous=state.data.values[key];
  state.data.values[key]=value;updateHomeModes();
  try{await request(`/api/v1/params/${encodeURIComponent(key)}`,{method:"PUT",body:JSON.stringify({value})});await refreshHome()}
  catch(e){state.data.values[key]=previous;updateHomeModes();alert(e.message)}
});

async function refreshHome(){
  if(document.hidden||$("#home-view").hidden)return;
  try{state.data=await request("/api/v1/config");updateHome()}catch(_){/* keep the last known status */}
}

function showHome(){ $("#app").hidden=true; $("#home-view").hidden=false; updateRoadVideo(); }
function showSettings(panel=state.active){ $("#home-view").hidden=true; $("#app").hidden=false; updateRoadVideo(); state.active=panel; renderNav(); renderPanel(); }

async function confirmAction(action,title){const message=action==="pull-update"?"Pull the latest remote update and permanently discard all tracked local changes? Git LFS content will not be downloaded.":`Are you sure you want to ${title.toLowerCase()}?`;if(!confirm(message))return;try{const result=await request(`/api/v1/actions/${action}`,{method:"POST",body:"{}"});if(action==="pull-update")alert(`Update complete: ${result.revision}`);await load()}catch(e){alert(e.message)}}

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
$("#road-video-toggle").onchange=event=>{state.videoEnabled=event.target.checked;localStorage.setItem("roadVideoEnabled",state.videoEnabled?"1":"0");updateRoadVideo()};
$("#road-video").onload=()=>{if(state.videoStreaming)$("#road-video-status").textContent="LIVE"};
$("#road-video").onerror=()=>{if(state.videoStreaming){state.videoStreaming=false;$("#road-video-status").textContent="Video unavailable";$("#road-video").hidden=true;$("#road-video-placeholder").hidden=false;$("#road-video-placeholder").textContent="Unable to receive road camera video"}};
document.addEventListener("visibilitychange",updateRoadVideo);

function showLoadError(error){
  $("#panel").innerHTML=`<div class="loading">Unable to load settings.<br><small>${error.message}</small><br><button class="retry">Retry</button></div>`;
  $(".retry").onclick=()=>load().catch(showLoadError);
}
load().catch(showLoadError);
setInterval(refreshHome,1000);
