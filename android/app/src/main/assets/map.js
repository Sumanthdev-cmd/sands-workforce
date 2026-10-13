const map=L.map('map').setView([20.59,78.96],4);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
let markers=L.layerGroup().addTo(map),fitted=false;
window.showPeople=function(rows){
  markers.clearLayers();const list=document.getElementById('people');list.replaceChildren();const bounds=[];let freshCount=0;
  rows.forEach(p=>{
    const button=document.createElement('button');button.className='person';button.textContent=`${p.name} · ${p.code}`;
    const time=p.recorded_at?new Date(p.recorded_at):null, fresh=!!(p.active&&time&&Date.now()-time.getTime()<120000);
    if(fresh)freshCount++;
    const detail=document.createElement('small');detail.textContent=`${p.kind} · ${p.active?'Checked in':'Checked out / no active session'}\n${time?`Last seen ${time.toLocaleString()}`:'No location received yet'}`;button.appendChild(detail);
    if(Number.isFinite(p.latitude)&&Number.isFinite(p.longitude)){
      const coords=[p.latitude,p.longitude];bounds.push(coords);const label=document.createElement('div');label.textContent=`${p.name} (${p.kind}) — ${fresh?'Recent work location':'Last known location'}`;
      const marker=L.circleMarker(coords,{radius:8,color:p.active?(fresh?'#0b996f':'#cb861a'):'#77849c',fillOpacity:.85}).addTo(markers).bindPopup(label);
      button.onclick=()=>{map.setView(coords,16);marker.openPopup();};
    }else button.disabled=true;
    list.appendChild(button);
  });
  document.getElementById('summary').textContent=`${rows.length} people · ${freshCount} recent active locations · updated ${new Date().toLocaleTimeString()}`;
  if(bounds.length&&!fitted){map.fitBounds(bounds,{padding:[25,25],maxZoom:15});fitted=true;}
};
