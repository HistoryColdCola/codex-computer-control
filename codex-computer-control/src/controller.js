import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { stepSchema, screenshotSchema, validateGeometry } from './schema.js';
import { detectPlatform } from './platform.js';
const normalize=s=>s.replace(/\s/gu,'');
export class Controller {
  constructor(bridge,{clock=()=>performance.now()}={}){this.bridge=bridge;this.clock=clock;this.views=new Map();this.busy=false;this.stopFile=path.join(bridge.dataDir,'STOP');}
  checkStop(){if(existsSync(this.stopFile))throw new Error('Emergency stop active. The user must run the resume command.');}
  stop(){mkdirSync(this.bridge.dataDir,{recursive:true});writeFileSync(this.stopFile,'');}
  async exclusive(fn){if(this.busy)throw new Error('Desktop busy. Wait for the current call; do not replay input.');this.busy=true;try{return await fn();}finally{this.busy=false;}}
  async status(){return this.exclusive(async()=>({...await this.bridge.call('status'),...detectPlatform(this.bridge.platform),stopped:existsSync(this.stopFile),stop_file:this.stopFile}));}
  async screenshot(args={}){
    const {format}=screenshotSchema.parse(args);
    return this.exclusive(async()=>{this.checkStop();const result=await this.bridge.call('observe',{profile:'detail',format});
      return {content:[{type:'image',data:result.image,mimeType:result.mimeType}]};});
  }
  viewPoint(view,x,y){
    const [w,h]=view.image_size;
    if(x<0||y<0||x>=w||y>=h)throw new Error('Coordinates outside supplied view');
    return [Math.min(view.origin[0]+view.logical_size[0]-1,Math.round(view.origin[0]+x*view.logical_size[0]/w)),
      Math.min(view.origin[1]+view.logical_size[1]-1,Math.round(view.origin[1]+y*view.logical_size[1]/h))];
  }
  async step(input){
    // Validate all shapes/key names before starting a native process or activating apps.
    const args=stepSchema.parse(input);
    return this.exclusive(async()=>{
      const start=this.clock(),hardEnd=start+Math.min(20000,Math.max(3000,args.budget_ms+2000));
      const deadline=start+args.budget_ms;
      const call=async(op,params={})=>{
        const started=this.clock();
        try{return await this.bridge.call(op,params,Math.max(0,hardEnd-this.clock()));}
        finally{const stat=nativeStats[op]??={calls:0,ms:0};stat.calls++;stat.ms+=Math.round(this.clock()-started);}
      };
      let completed=0,current=null,expected=null,error=null,uncertain=false,inFlightInput=false,status={},observation={};const results=[],content=[],nativeStats={};
      let actions=args.actions.map(a=>({...a}));
      try{
        this.checkStop();
        const view=args.view_id?this.views.get(args.view_id):null;
        if(args.view_id&&(!view||this.clock()-view.created>120000))throw new Error('Unknown/expired view_id; observe again.');
        status=await call('status');
        if(!status.desktop_available)throw new Error('Desktop locked, asleep or unavailable. Wake/unlock manually.');
        if(actions.some(a=>a.action!=='wait')&&!status.accessibility)throw new Error('Accessibility/input access unavailable.');
        if(!status.screen_recording)throw new Error('Screen recording access unavailable.');
        if(view){
          if(view.generation!==this.bridge.generation)throw new Error('Native backend restarted; observe again.');
          if(view.screen_size[0]!==status.width||view.screen_size[1]!==status.height)throw new Error('Display geometry changed; observe again.');
          if(status.app_id!==view.app_id)throw new Error('Foreground app changed since the view; observe intended app again.');
          actions=actions.map(a=>{if(['click','move'].includes(a.action))[a.x,a.y]=this.viewPoint(view,a.x,a.y);
            if(a.action==='drag'){[a.start_x,a.start_y]=this.viewPoint(view,a.start_x,a.start_y);[a.end_x,a.end_y]=this.viewPoint(view,a.end_x,a.end_y);}return a;});
        }
        validateGeometry(actions,args.crop,status.width,status.height);
        if(this.bridge.platform==='darwin'&&actions.some(a=>(a.keys||[a.key]).filter(Boolean).some(k=>['win','windows','insert'].includes(k.toLowerCase()))))throw new Error('win/windows/insert keys are Windows-only');
        expected=status.app_id;
        if(args.app){const focused=await call('focus',{app:args.app});expected=focused.app_id;if(view&&view.app_id!==expected)throw new Error('View belongs to another application.');}
        if(actions.length&&!expected)throw new Error('No foreground app; observe/activate first.');
        for(const a of actions){
          this.checkStop();if(this.clock()>=deadline)throw new Error('Action budget exceeded; remaining actions were not run.');
          current=a;
          if(a.action==='wait')await this.wait(a.seconds*1000,expected,call);
          else if(['click_text','assert_text'].includes(a.action)){
            const target=await this.findText(a,expected,call,Math.min(deadline,this.clock()+a.timeout_ms));
            if(a.action==='click_text'){inFlightInput=true;await call('action',{expected,action:target.element_id&&target.actions?.includes('invoke')?{action:'invoke',element_id:target.element_id}:{action:'click',x:target.x,y:target.y,button:'left',clicks:1}});inFlightInput=false;}
            results.push({verified:a.text,x:target.x,y:target.y,source:target.source,text_timing:target.text_timing,method:a.action==='click_text'?(target.element_id&&target.actions?.includes('invoke')?'invoke':'pointer'):'assertion'});
          }else {inFlightInput=true;results.push(await call('action',{expected,action:a}));inFlightInput=false;}
          completed++;current=null;
        }
        if(args.settle_ms)await this.wait(args.settle_ms,expected,call);
      }catch(e){error=e.message;uncertain=inFlightInput;if(uncertain)this.stop();}
      const actionsMs=this.clock()-start;
      try{
        if(!uncertain){
          this.checkStop();
          if(args.output==='image'||error){
            const frame=await call('observe',{expected:error?null:expected,profile:args.profile,crop:args.crop,format:'jpeg'});
            const token=randomUUID();
            const {image,mimeType,...meta}=frame;
            if(this.views.size>=16)this.views.delete(this.views.keys().next().value);
            this.views.set(token,{...meta,created:this.clock(),generation:this.bridge.generation});
            observation={...meta,view_id:token,profile:args.profile};content.push({type:'image',data:image,mimeType});
          }
          if(!error&&(args.output==='text'||args.include_text===true||(args.output==='image'&&args.include_text==='auto'))){
            const text=await call('text',{expected,region:args.crop,accessibility_only:args.output!=='text'&&args.include_text==='auto'});observation={...observation,text:text.rows,text_source:text.source,text_coordinates:'screen'};
          }
        }
      }catch(e){error||=e.message;}
      const info={completed,requested:actions.length,error,results,uncertain_action:uncertain?current.action:null,
        stopped:existsSync(this.stopFile),observe_again_required:Boolean(error),platform:this.bridge.platform,
        actions_ms:Math.round(actionsMs),capture_ms:Math.round(this.clock()-start-actionsMs),total_ms:Math.round(this.clock()-start),native_calls:nativeStats,...observation};
      content.unshift({type:'text',text:JSON.stringify(info)});return {content,structuredContent:info,isError:Boolean(error)};
    });
  }
  async wait(ms,expected,call){const end=this.clock()+ms;do{this.checkStop();await call('guard',{expected});const left=end-this.clock();if(left>0)await new Promise(r=>setTimeout(r,Math.min(30,left)));}while(this.clock()<end);}
  async findText(a,expected,call,end){
    do{
      this.checkStop();const text=await call('text',{expected,region:a.region,target:a.text});
      const matches=[...new Map(text.rows.filter(r=>normalize(r.text)===normalize(a.text)).map(r=>[`${r.x},${r.y}`,r])).values()];
      if(matches.length===1)return {...matches[0],source:text.source,text_timing:text.timing};
      if(matches.length>1)throw new Error('Text target ambiguous; tighten region.');
      if(this.clock()>=end)throw new Error(`Expected exact text not found: ${a.text}`);
      await new Promise(r=>setTimeout(r,30));
    }while(true);
  }
  close(){this.bridge.close();}
}
