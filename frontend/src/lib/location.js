import {apiRequest} from "./api";

const DEVICE_KEY="sands_web_device_identifier";

function browserDeviceIdentifier(){
  let value=localStorage.getItem(DEVICE_KEY);
  if(!value){
    value=`web-${crypto.randomUUID()}`;
    localStorage.setItem(DEVICE_KEY,value);
  }
  return value;
}

async function employeeDevice(){
  let identifier=browserDeviceIdentifier();
  const devices=await apiRequest("/devices/me");
  const existing=(Array.isArray(devices)?devices:[]).find(device=>device.device_identifier===identifier&&device.is_active);
  if(existing)return existing.id;
  const body=()=>({
    device_identifier:identifier,
    platform:"WEB",
    device_name:`${navigator.platform||"Browser"} attendance browser`,
    manufacturer:null,
    model:navigator.userAgent.slice(0,100),
    os_version:null,
    app_version:"2.2.0",
    fcm_token:null,
  });
  let created;
  try{created=await apiRequest("/devices/register",{method:"POST",body:body()})}
  catch(error){if(error.status!==409)throw error;identifier=`web-${crypto.randomUUID()}`;localStorage.setItem(DEVICE_KEY,identifier);created=await apiRequest("/devices/register",{method:"POST",body:body()})}
  return created.id;
}

function positionRequest(options){
  return new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,options));
}

function positionError(error){
  if(error?.code===1)return new Error("Location permission was denied. Allow location access in browser settings.");
  if(error?.code===2)return new Error("GPS is unavailable. Turn on device location services and try again.");
  return new Error("GPS timed out. Keep location services on, wait for a live reading, and try again.");
}

export async function readBrowserPosition(options={}){
  if(!window.isSecureContext&&!(["localhost","127.0.0.1"].includes(window.location.hostname))){
    throw new Error("GPS requires HTTPS when this page is opened on a phone.");
  }
  if(!navigator.geolocation)throw new Error("This device does not provide browser GPS.");
  try{
    return await positionRequest({enableHighAccuracy:true,timeout:15000,maximumAge:0,...options});
  }catch(error){
    if(error?.code===1)throw positionError(error);
    try{
      // Desktops often cannot produce a second high-accuracy reading on demand.
      // A recent network-assisted reading is still fresh enough for the backend
      // attendance validation and avoids blocking a valid checkout on timeout.
      return await positionRequest({enableHighAccuracy:false,timeout:10000,maximumAge:30000});
    }catch(fallbackError){
      throw positionError(fallbackError);
    }
  }
}

export async function submitEmployeePosition(position){
  const deviceId=await employeeDevice();
  const point={
    client_event_id:crypto.randomUUID(),
    latitude:position.coords.latitude,
    longitude:position.coords.longitude,
    accuracy_meters:position.coords.accuracy??null,
    speed_mps:position.coords.speed??null,
    battery_percentage:null,
    recorded_at:new Date(position.timestamp||Date.now()).toISOString(),
  };
  await apiRequest("/locations/batch",{method:"POST",body:{device_id:deviceId,points:[point]}});
  return point;
}

export async function pushCurrentEmployeeLocation(existingPosition=null){
  const position=existingPosition||await readBrowserPosition();
  return submitEmployeePosition(position);
}
