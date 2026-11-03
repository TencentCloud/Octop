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
console.log(`今天是${weekday}（${date}），请为12个西方星座生成今日运势推送。每个星座包含：①今日综合运势简评（2句）②爱情💕/事业💼/财运💰各项指数（1-5颗星）③今日幸运颜色、数字、方位④一句今日箴言。输出格式清晰，中英双语，适合每日推送。星座顺序：白羊/金牛/双子/巨蟹/狮子/处女/天秤/天蝎/射手/摩羯/水瓶/双鱼。`);
