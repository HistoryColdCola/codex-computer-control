import { z } from 'zod';
export const region = z.object({ x: z.number().int().nonnegative(), y: z.number().int().nonnegative(),
  width: z.number().int().positive(), height: z.number().int().positive() }).strict();
const xy = { x: z.number().int().nonnegative(), y: z.number().int().nonnegative() };
const button = z.enum(['left', 'right', 'middle']);
const keys = ['command','cmd','meta','win','windows','shift','alt','option','ctrl','control','enter','return','esc','escape','tab','space','backspace','delete','up','down','left','right','home','end','pageup','pagedown','insert'];
export function validKey(k) { return keys.includes(k.toLowerCase()) || /^[a-z0-9]$/i.test(k) || /^f([1-9]|1[0-2])$/i.test(k); }
export const key = z.string().min(1).max(20).refine(validKey, 'Unsupported key name');
const exactText = z.string().min(1).max(500).refine(v => v.trim().length > 0, 'Text must contain a non-whitespace character');
export const action = z.discriminatedUnion('action', [
  z.object({ action:z.literal('click'), ...xy, button:button.default('left'), clicks:z.number().int().min(1).max(3).default(1) }).strict(),
  z.object({ action:z.literal('move'), ...xy, duration:z.number().finite().min(0).max(1).default(0.1) }).strict(),
  z.object({ action:z.literal('drag'), start_x:xy.x,start_y:xy.y,end_x:xy.x,end_y:xy.y,duration:z.number().finite().min(.1).max(2).default(.3),button:z.enum(['left','right']).default('left') }).strict(),
  z.object({ action:z.literal('scroll'), clicks:z.number().int().min(-100).max(100),horizontal:z.boolean().default(false) }).strict(),
  z.object({ action:z.literal('type'), text:z.string().max(10000) }).strict(),
  z.object({ action:z.literal('press'), key, presses:z.number().int().min(1).max(50).default(1) }).strict(),
  z.object({ action:z.literal('hotkey'), keys:z.array(key).min(1).max(6) }).strict(),
  z.object({ action:z.literal('invoke'),element_id:z.string().min(1).max(128) }).strict(),
  z.object({ action:z.literal('focus_element'),element_id:z.string().min(1).max(128) }).strict(),
  z.object({ action:z.literal('set_value'),element_id:z.string().min(1).max(128),value:z.string().max(10000) }).strict(),
  z.object({ action:z.literal('wait'), seconds:z.number().finite().min(0).max(1) }).strict(),
  ...['click_text','assert_text'].map(a=>z.object({action:z.literal(a),text:exactText,region:region.optional(),timeout_ms:z.number().int().min(0).max(3000).default(0)}).strict())
]);
export const stepSchema = z.object({
  actions:z.array(action).max(32),app:z.string().trim().min(1).max(200).refine(s=>!s.includes('\0')).optional(),
  settle_ms:z.number().int().min(0).max(500).default(0),profile:z.enum(['ultra','fast','detail']).default('ultra'),
  output:z.enum(['image','text','none']).default('image'),view_id:z.string().min(1).max(64).optional(),crop:region.optional(),
  budget_ms:z.number().int().min(100).max(20000).default(8000),include_text:z.union([z.boolean(),z.literal('auto')]).default('auto')
}).strict().superRefine((v,c)=>{
  if(v.actions.reduce((n,a)=>n+(a.action==='wait'?a.seconds:0),0)>2)c.addIssue({code:'custom',message:'Total explicit waits exceed 2 seconds'});
});
export const screenshotSchema = z.object({format:z.enum(['jpeg','png']).default('jpeg')}).strict();
export function validateGeometry(actions, crop, width, height) {
  const point=(x,y)=>{if(x<0||y<0||x>=width||y>=height||(x===0&&y===0))throw new Error('Point outside primary display or reserved stop corner');};
  const box=r=>{if(r&&(r.x+r.width>width||r.y+r.height>height))throw new Error('Region outside primary display');};
  box(crop);
  for(const a of actions){
    if(['click','move'].includes(a.action))point(a.x,a.y);
    if(a.action==='drag'){point(a.start_x,a.start_y);point(a.end_x,a.end_y);}
    box(a.region);
  }
}
