export function compareModules(a,b){
 if(a[0]==='dashboard')return b[0]==='dashboard'?0:-1;
 if(b[0]==='dashboard')return 1;
 return a[1].localeCompare(b[1],'en',{sensitivity:'base'});
}
// date-display-ddmmyyyy-v1
