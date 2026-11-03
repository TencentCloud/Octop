#!/usr/bin/env node
'use strict';
const fs=require('fs'),path=require('path');
const USERS_DIR=path.join(__dirname,'../data/users');
function sanitizeId(v){if(typeof v!=='string'||!/^[a-zA-Z0-9_-]{1,128}$/.test(v)){console.error('invalid userId');process.exit(1);}return v;}
function safeUserPath(u){const r=path.resolve(USERS_DIR,u+'.json');if(!r.startsWith(path.resolve(USERS_DIR)+path.sep)){console.error('illegal path');process.exit(1);}return r;}
function loadUser(u){const f=safeUserPath(u);return fs.existsSync(f)?JSON.parse(fs.readFileSync(f,'utf8')):{};}
const userId=sanitizeId(process.argv[2]||'default');
loadUser(userId);
const now=new Date();
const WEEKDAYS=['星期日','星期一','星期二','星期三','星期四','星期五','星期六'];
const wd=now.getDay();
const date=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
const weekday=WEEKDAYS[wd];
const month=now.getMonth()+1;
const day=now.getDate();
const tomorrow_weekday=WEEKDAYS[(wd+1)%7];
console.log(`睡前放松时间🌙（${date}）。请生成今晚睡眠引导程序：①睡前90分钟清单（该做/不该做各3条）②今晚放松程序（4-7-8呼吸引导+渐进式肌肉放松，3步）③睡眠环境检查（温度/光线/噪音/手机各1条建议）④今晚助眠冥想引导（2分钟正念入睡引导语）⑤明日唤醒预告（提醒明天最重要的1件事，放下，安心入睡）。语气极度舒缓，帮助用户自然入睡。`);
