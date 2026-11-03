#!/usr/bin/env node
'use strict';
const fs=require('fs'),path=require('path');
const SKILL='daily-mindful',DEFAULT_MORNING='07:30',DEFAULT_EVENING='21:30';
const USERS_DIR=path.join(__dirname,'../data/users');
const ALLOWED_CH=new Set(['telegram','feishu','slack','discord']);
function sanitizeId(v){if(typeof v!=='string'||!/^[a-zA-Z0-9_-]{1,128}$/.test(v)){console.error('❌ 无效userId');process.exit(1);}return v;}
function sanitizeTime(v,l){if(!/^\d{1,2}:\d{2}$/.test(v)){console.error('❌ 无效'+l);process.exit(1);}const[h,m]=v.split(':').map(Number);if(h>23||m>59){console.error('❌ 无效'+l);process.exit(1);}return{h,m};}
function safeUserPath(u){const r=path.resolve(USERS_DIR,u+'.json');if(!r.startsWith(path.resolve(USERS_DIR)+path.sep)){console.error('❌ 非法路径');process.exit(1);}return r;}
function loadUser(u){const f=safeUserPath(u);return fs.existsSync(f)?JSON.parse(fs.readFileSync(f,'utf8')):{}}
function saveUser(u,d){fs.mkdirSync(USERS_DIR,{recursive:true});fs.writeFileSync(safeUserPath(u),JSON.stringify(d,null,2),'utf8');}
function enablePush(userId,opts){
  userId=sanitizeId(userId);
  const user=loadUser(userId);
  const mt=opts.morning||user.morningTime||DEFAULT_MORNING;
  const et=opts.evening||user.eveningTime||DEFAULT_EVENING;
  const{h:mh,m:mm}=sanitizeTime(mt,'--morning');
  const{h:eh,m:em}=sanitizeTime(et,'--evening');
  const ch=opts.channel||user.channel||'telegram';
  if(!ALLOWED_CH.has(ch)){console.error('❌ 不支持渠道:'+ch);process.exit(1);}
  const sk=`agent:main:${ch}:direct:${userId}`;
  console.log('__OPENCLAW_CRON_ADD__:'+JSON.stringify({name:`${SKILL}-morning-${userId}`,cronExpr:`${mm} ${mh} * * *`,tz:'Asia/Shanghai',session:'isolated',sessionKey:sk,channel:ch,to:userId,announce:true,timeoutSeconds:180,message:`node ${path.join(__dirname,'morning-push.js')} ${userId}`}));
  console.log('__OPENCLAW_CRON_ADD__:'+JSON.stringify({name:`${SKILL}-evening-${userId}`,cronExpr:`${em} ${eh} * * *`,tz:'Asia/Shanghai',session:'isolated',sessionKey:sk,channel:ch,to:userId,announce:true,timeoutSeconds:180,message:`node ${path.join(__dirname,'evening-push.js')} ${userId}`}));
  saveUser(userId,{...user,morningTime:mt,eveningTime:et,channel:ch,pushEnabled:true,updatedAt:new Date().toISOString()});
  console.log(`\n✅ ${SKILL} 推送已开启\n⏰ 早推: ${mt}  🌙 晚推: ${et}  📡 渠道: ${ch}\n关闭: node push-toggle.js off ${userId}`);
}
function disablePush(userId){
  userId=sanitizeId(userId);
  console.log(`__OPENCLAW_CRON_RM__:${SKILL}-morning-${userId}`);
  console.log(`__OPENCLAW_CRON_RM__:${SKILL}-evening-${userId}`);
  const user=loadUser(userId);
  saveUser(userId,{...user,pushEnabled:false,updatedAt:new Date().toISOString()});
  console.log(`✅ ${SKILL} 推送已关闭`);
}
function showStatus(userId){
  userId=sanitizeId(userId);
  const u=loadUser(userId);
  console.log(`\n📡 ${SKILL} — ${userId}\n状态: ${u.pushEnabled?'✅ 开启':'❌ 关闭'}  早推: ${u.morningTime||DEFAULT_MORNING}  晚推: ${u.eveningTime||DEFAULT_EVENING}  渠道: ${u.channel||'telegram'}\n`);
}
if(require.main!==module)return;
const[cmd,uid,...rest]=process.argv.slice(2);
if(!cmd||!uid){console.log('用法: node push-toggle.js on|off|status <userId>');process.exit(1);}
const opts={};
const mi=rest.indexOf('--morning');if(mi!==-1)opts.morning=rest[mi+1];
const ei=rest.indexOf('--evening');if(ei!==-1)opts.evening=rest[ei+1];
const ci=rest.indexOf('--channel');if(ci!==-1)opts.channel=rest[ci+1];
if(cmd==='on')enablePush(uid,opts);
else if(cmd==='off')disablePush(uid);
else if(cmd==='status')showStatus(uid);
else{console.error('❌ 未知命令:'+cmd);process.exit(1);}
