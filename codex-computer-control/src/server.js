import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { ListToolsRequestSchema, CallToolRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { zodToJsonSchema } from 'zod-to-json-schema';
import { NativeBridge } from './bridge.js';
import { Controller } from './controller.js';
import { stepSchema,screenshotSchema } from './schema.js';
const controller=new Controller(new NativeBridge());
const server=new Server({name:'codex-computer-control',version:'1.1.0'},{capabilities:{tools:{}}});
const json=s=>zodToJsonSchema(s,{$refStrategy:'none',target:'jsonSchema7'});
server.setRequestHandler(ListToolsRequestSchema,async()=>({tools:[
  {name:'desktop_status',description:'Read OS/backend, primary display and permissions; no input.',inputSchema:{type:'object',properties:{},additionalProperties:false}},
  {name:'desktop_screenshot',description:'Capture primary display in screen coordinates.',inputSchema:json(screenshotSchema)},
  {name:'desktop_step',description:'Run up to 32 guarded native actions. Default image observation attaches AX/UIA controls without OCR. Use advertised element_id for invoke/set_value/focus_element. Observe first. Use view_id for thumbnail coordinates; text/region use screen pixels. Never replay partial input. Verify recipient and draft before send.',inputSchema:json(stepSchema)}
]}));
server.setRequestHandler(CallToolRequestSchema,async request=>{
  try{
    const args=request.params.arguments||{};
    if(request.params.name==='desktop_step')return await controller.step(args);
    if(request.params.name==='desktop_screenshot')return await controller.screenshot(args);
    if(request.params.name==='desktop_status'){
      if(Object.keys(args).length)throw new Error('desktop_status takes no arguments');
      const info=await controller.status();return {content:[{type:'text',text:JSON.stringify(info)}],structuredContent:info};
    }
    throw new Error('Unknown tool');
  }catch(e){return {content:[{type:'text',text:e.message}],isError:true};}
});
server.onclose=()=>controller.close();
for(const name of ['SIGINT','SIGTERM'])process.on(name,()=>{controller.close();process.exit(0);});
await server.connect(new StdioServerTransport());
