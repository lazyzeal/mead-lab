#!/usr/bin/env python3
import json
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = "0.0.0.0"
PORT = 8098
DB_PATH = Path(__file__).with_name("temperature.db")
STATIC_DIR = Path(__file__).with_name("static")
STATIC_TYPES = {".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
ESP32_URL = "http://192.168.31.123"
DB_LOCK = threading.Lock()
LATEST = {}
SYNC_LOCK = threading.Lock()
SYNC_STATUS = {}

PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>蜜酒工坊</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#172033;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.app{display:flex;min-height:100vh}main{flex:1;min-width:0;max-width:1220px;padding:28px 32px}
.side{width:248px;flex:none;background:#fff;border-right:1px solid #e3e9f2;padding:22px 14px;display:flex;flex-direction:column;position:sticky;top:0;height:100vh;overflow:auto}
.brand{font-size:20px;font-weight:700;padding:0 12px 18px;display:flex;flex-direction:column}.brand small{font-size:11px;letter-spacing:.14em;color:#4674c8}
nav{display:flex;flex-direction:column;gap:2px;flex:1}.nav{display:flex;flex-direction:column;padding:9px 12px;border-radius:8px;color:#33415c;cursor:pointer;user-select:none}
.nav:hover{background:#f1f5fb}.nav.on{background:#e8f0fd;color:#2d63c4;font-weight:600}.nav span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nav small{color:#8a97ab;font-weight:400;font-size:12px}.group{font-size:12px;color:#8a97ab;padding:14px 12px 4px;font-weight:600}button.new{margin:16px 4px 4px}
.side-status{font-size:12px;color:#718096;padding:12px 12px 0;border-top:1px solid #edf1f6;margin-top:12px}
.top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:4px}.badge{display:inline-block;font-size:12px;padding:1px 8px;border-radius:10px;background:#edf1f6;color:#526174;margin-right:6px}
.badge.active{background:#e3f4ea;color:#218653}.badge.draft{background:#fdf3dc;color:#9a6b00}
h1{margin:0 0 2px;font-size:26px}.muted{color:#718096}.card{padding:22px;margin:16px 0;border:1px solid #e3e9f2;border-radius:14px;background:#fff;box-shadow:0 4px 16px #233b6610}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.stat{position:relative;overflow:hidden}.stat:after{content:"";position:absolute;right:-20px;top:-30px;width:90px;height:90px;border-radius:50%;background:#edf3ff}
.label{color:#718096;font-size:14px}.value{font-size:32px;font-weight:700;margin-top:8px;position:relative;z-index:1}.status{display:inline-flex;align-items:center;gap:7px;margin-top:14px}.status:before{content:"";width:8px;height:8px;border-radius:50%;background:#21a366}
label{display:block;color:#526174;margin:8px 0 4px}input,select,button{font:inherit;border-radius:8px;border:1px solid #d3dce9;padding:10px;background:#fff;color:#172033}
button{background:#3978df;color:#fff;border:0;cursor:pointer;font-weight:600}.settings{display:flex;gap:18px;flex-wrap:wrap;align-items:end}.settings label{min-width:140px}
.chart-head{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.chart-wrap{height:480px;margin-top:12px}.ok{color:#218653}.error{color:#d14343}
h3{font-size:15px;margin:22px 0 4px;color:#33415c}textarea{width:100%;font:inherit;border-radius:8px;border:1px solid #d3dce9;padding:10px;resize:vertical}
label.inline{display:flex;align-items:center;gap:8px;margin:0}input:disabled,select:disabled,textarea:disabled{background:#f4f7fb;color:#526174}
table.ferm{width:100%;border-collapse:collapse;margin:6px 0 10px}table.ferm th{text-align:left;font-weight:500;color:#718096;padding:4px 6px}table.ferm td{padding:4px 6px}table.ferm input,table.ferm select{width:100%}
button.secondary{background:#e8f0fd;color:#2d63c4}button.success{background:#218653}button.danger{background:#d14343}button.ghost{background:transparent;color:#d14343;border:1px solid #f0caca}
button:disabled{opacity:.45;cursor:default}.actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:20px 0 8px}.abv{margin-top:10px;font-weight:600}
@media(max-width:860px){.app{flex-direction:column}.side{width:auto;height:auto;position:static;border-right:0;border-bottom:1px solid #e3e9f2}main{padding:20px 16px}}
@media(max-width:760px){.grid{grid-template-columns:repeat(2,1fr)}.chart-wrap{height:390px}}
</style></head><body><div class="app">
<aside class="side"><div class="brand">蜜酒工坊<small>MEAD LAB</small></div>
<nav><div class="nav" data-view="overview">温度监控</div><div class="nav" data-view="settings">温控设置</div>
<button id="newBrew" class="new">＋ 新建酿造</button><div id="brewNav"></div></nav>
<div id="status" class="side-status">正在连接电脑服务…</div></aside>
<main><header class="top"><div><h1 id="viewTitle">温度监控</h1><div id="viewSub" class="muted"></div></div>
<label class="inline" id="rangeWrap">时间范围<select id="range"><option value="3">最近 3 小时</option><option value="6">最近 6 小时</option>
<option value="12">最近 12 小时</option><option value="24" selected>最近 24 小时</option>
<option value="72">最近 3 天</option><option value="168">最近 7 天</option><option value="504">最近 21 天</option></select></label></header>
<section id="stats" class="grid"><div class="card stat"><div class="label">当前温度</div><div id="temp" class="value">--.--℃</div></div>
<div class="card stat"><div class="label">制冷状态</div><div id="control" class="value">--</div></div>
<div class="card stat"><div class="label">启动温度</div><div id="start" class="value">--℃</div></div>
<div class="card stat"><div class="label">停止温度</div><div id="stop" class="value">--℃</div></div></section>
<section id="chartCard" class="card"><div id="chart" class="chart-wrap"></div><div class="muted">将鼠标移动到曲线上，可查看准确时间、温度和制冷状态。</div></section>
<section id="brewCard" class="card"><form id="brewForm" novalidate>
<h3 style="margin-top:0">基本信息</h3><div class="settings">
<label>标题<input id="fTitle" placeholder="传统蜂蜜酒"></label>
<label>类型<select id="fStyle"><option value="">未选择</option><option value="traditional">传统</option><option value="melomel">果酒</option><option value="metheglin">香料</option><option value="other">其他</option></select></label>
<label>开始日期<input id="fDate" type="date"></label>
<label>批次体积（L）<input id="fVolume" type="number" step="0.1" min="0"></label></div>
<h3>可发酵糖</h3>
<table class="ferm"><thead><tr><th>名称</th><th>类别</th><th>用量</th><th>单位</th><th>含糖率 %</th><th title="反算时调整这一项的用量">补足</th><th></th></tr></thead><tbody id="fermRows"></tbody></table>
<button type="button" id="addFerm" class="secondary">添加原料</button>
<h3>酵母</h3><div class="settings">
<label>名称 / 型号<input id="fYeast" placeholder="M05"></label>
<label>耐酒度 %<input id="fTolerance" type="number" step="0.5" min="0"></label>
<label>用量（g）<input id="fYeastAmount" type="number" step="0.1" min="0"></label></div>
<h3>温度设置</h3><div class="settings">
<label>目标温度（℃）<input id="fTempTarget" type="number" step="1" min="0" max="40"></label>
<label>启动温度（℃）<input id="fTempStart" type="number" step="1" min="0" max="40"></label>
<label>停止温度（℃）<input id="fTempStop" type="number" step="1" min="0" max="40"></label></div>
<div class="muted">开始酿造时作为初始温控设定下发到 ESP32，之后可以在"温控设置"中调整。</div>
<h3>比重</h3><div class="settings">
<label>实测 OG<input id="fOg" type="number" step="0.001" placeholder="1.100"></label>
<label>预期 FG<input id="fFgExp" type="number" step="0.001"></label>
<label>实测 FG<input id="fFgMeas" type="number" step="0.001" placeholder="发酵结束后填写"></label>
<button type="button" id="estimate" class="secondary">估算</button></div>
<div id="estimateResult" class="muted"></div>
<div class="settings"><label>目标 OG（仅用于反算）<input id="fTargetOg" type="number" step="0.001"></label>
<button type="button" id="reverse" class="secondary">反算补足原料用量</button></div>
<div id="abv" class="abv"></div>
<h3>配方 / 工艺</h3><textarea id="fRecipe" rows="6" placeholder="原料细节、营养盐、添加物、步骤……"></textarea>
<h3>备注</h3><textarea id="fNotes" rows="4"></textarea>
<div class="actions"><button type="button" id="saveDraft">保存草稿</button>
<button type="button" id="startBrew" class="success">开始酿造</button>
<button type="button" id="saveFg">保存实测 FG</button>
<button type="button" id="endBrew" class="danger">结束酿造</button>
<button type="button" id="deleteDraft" class="ghost">删除草稿</button><span id="brewMessage"></span></div>
</form>
<div class="muted">含糖率和估算 OG 仅供参考，OG 以比重计实测为准。开始酿造后只能补填实测 FG。</div></section>
<section id="settingsCard" class="card"><form id="settings" class="settings" novalidate>
<label>目标温度（℃）<input id="target" type="number" step="1" min="0" max="40"></label>
<label>启动温度（℃）<input id="startInput" type="number" step="1" min="0" max="40"></label>
<label>停止温度（℃）<input id="stopInput" type="number" step="1" min="0" max="40"></label>
<button>保存并下发到 ESP32</button><span id="message"></span></form>
<div class="muted" style="margin-top:10px">温度高于启动温度时开始制冷，低于停止温度时停止，中间保持当前状态。</div></section>
<script src="/static/echarts.min.js"></script>
<script>
const $=s=>document.querySelector(s),chart=echarts.init($("#chart"));let points=[],editing=false;
["#target","#startInput","#stopInput"].forEach(selector=>$(selector).addEventListener("input",()=>editing=true));
const GAP_MS=35000;
function draw(raw){let d=[];raw.forEach((p,i)=>{if(i&&new Date(p.time)-new Date(raw[i-1].time)>GAP_MS)d.push({time:p.time,gap:true});d.push(p)});
points=d;let values=raw.flatMap(p=>[p.temperature,p.target,p.start,p.stop]).filter(Number.isFinite);
if(!values.length){chart.setOption({graphic:{type:"text",left:"center",top:"middle",style:{text:"暂无温度记录",fill:"#8a97ab",fontSize:16}}},{notMerge:true});return}
let lo=Math.floor(Math.min(...values)-1),hi=Math.ceil(Math.max(...values)+1);
if(hi-lo<4){let center=(lo+hi)/2;lo=Math.floor(center-2);hi=Math.ceil(center+2)}
let line=(name,key,color)=>({name,type:"line",data:d.map(p=>[p.time,p.gap?null:p[key]]),step:"end",symbol:"none",lineStyle:{color,type:"dashed",width:2},tooltip:{show:false}});
chart.setOption({animation:false,color:["#3978df","#e6a817","#df6b5d","#36a269"],grid:{left:58,right:24,top:25,bottom:58},legend:{top:0,right:0},
tooltip:{trigger:"axis",axisPointer:{type:"cross"},backgroundColor:"#172033",borderWidth:0,textStyle:{color:"#fff"},formatter:function(items){let p=d[items[0].dataIndex];if(!p||p.gap)return"";let date=new Date(p.time);return date.toLocaleString()+"<br><b>实际温度："+p.temperature.toFixed(2)+"℃</b><br>目标："+p.target.toFixed(2)+"℃ · 启动："+p.start.toFixed(2)+"℃ · 停止："+p.stop.toFixed(2)+"℃<br>"+(p.cooler_on?"制冷中":"制冷停止")}},
xAxis:{type:"time",name:"时间",nameLocation:"middle",nameGap:36,axisLabel:{color:"#718096"},axisLine:{lineStyle:{color:"#cbd5e1"}},splitLine:{show:false}},
yAxis:{type:"value",name:"温度（℃）",min:lo,max:hi,interval:1,axisLabel:{color:"#718096",formatter:"{value}℃"},splitLine:{lineStyle:{color:"#edf1f6"}}},
series:[{name:"实际温度",type:"line",data:d.map(p=>[p.time,p.gap?null:p.temperature]),smooth:true,symbol:"none",lineStyle:{width:3},areaStyle:{color:"#3978df12"}},line("目标温度","target","#e6a817"),line("启动温度","start","#df6b5d"),line("停止温度","stop","#36a269")]},{notMerge:true});}
const STATUS={draft:"草稿",active:"进行中",ended:"已结束"},SUGAR_DEFAULT={honey:80,sugar:100,juice:12,fruit:10,other:50},
CATEGORY={honey:"蜂蜜",sugar:"糖",juice:"果汁",fruit:"水果",other:"其他"},SUCROSE_POINTS=384;let brews=[];
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const num=v=>v===""?null:Number(v);let view="overview",currentId=null;const selectedBrew=()=>brews.find(b=>b.id===currentId)||null;
function msg(text,ok){$("#brewMessage").textContent=text;$("#brewMessage").className=ok?"ok":"error"}
async function refreshBrews(selectId){brews=await(await fetch("/api/brews")).json();
if(selectId===undefined)renderNav();else if(selectId)go("brew",selectId);else go("overview")}
function renderNav(){let html=[["active","进行中"],["draft","草稿"],["ended","已结束"]].map(([k,label])=>{let items=brews.filter(b=>b.status===k);
return items.length?`<div class="group">${label}</div>`+items.map(b=>`<div class="nav${view==="brew"&&b.id===currentId?" on":""}" data-id="${b.id}"><span>${esc(b.title)}</span><small>#${b.id}${b.brew_date?" · "+b.brew_date:""}</small></div>`).join(""):""}).join("");
$("#brewNav").innerHTML=html||'<div class="group">暂无酿造记录</div>';$("#brewNav").querySelectorAll("[data-id]").forEach(a=>a.onclick=()=>go("brew",+a.dataset.id));
document.querySelectorAll(".nav[data-view]").forEach(a=>a.classList.toggle("on",a.dataset.view===view))}
function go(v,id){view=v;currentId=v==="brew"?id:null;let b=selectedBrew(),show=(sel,on)=>$(sel).style.display=on?"":"none",recorded=b&&b.status!=="draft";
show("#stats",v==="overview");show("#chartCard",v==="overview"||(v==="brew"&&recorded));show("#brewCard",v==="brew"||v==="new");show("#settingsCard",v==="settings");
show("#rangeWrap",v==="overview"||(v==="brew"&&b&&b.status==="active"));
$("#viewTitle").textContent={overview:"温度监控",settings:"温控设置",new:"新建酿造"}[v]||(b?b.title:"");
$("#viewSub").innerHTML=v==="brew"&&b?`<span class="badge ${b.status}">${STATUS[b.status]}</span>#${b.id}${b.brew_date?" · 开始日期 "+b.brew_date:""}${b.status==="ended"?" · 温度曲线为开始到结束":""}`:v==="new"?"填写配方并保存为草稿，开始酿造前不会启动制冷":"";
if(v==="brew"||v==="new")fillForm(b);renderNav();chart.resize();update()}
function fermRow(f={}){let tr=document.createElement("tr"),cat=f.category||"honey";
tr.innerHTML=`<td><input class="fn" value="${esc(f.name)}" placeholder="椴树蜜"></td><td><select class="fc">${Object.entries(CATEGORY).map(([k,v])=>`<option value="${k}"${k===cat?" selected":""}>${v}</option>`).join("")}</select></td>
<td><input class="fa" type="number" step="0.01" min="0" value="${f.amount??""}"></td><td><select class="fu"><option value="kg">kg</option><option value="L">L</option></select></td>
<td><input class="fp" type="number" step="1" min="0" max="100" value="${f.sugar_pct??SUGAR_DEFAULT[cat]}"></td><td><input class="fb" type="radio" name="balance"${f.is_balance?" checked":""}></td>
<td><button type="button" class="ghost fd">删除</button></td>`;tr.querySelector(".fu").value=f.unit||(cat==="juice"?"L":"kg");
tr.querySelector(".fc").onchange=e=>{tr.querySelector(".fp").value=SUGAR_DEFAULT[e.target.value];tr.querySelector(".fu").value=e.target.value==="juice"?"L":"kg"};
tr.querySelector(".fd").onclick=()=>tr.remove();$("#fermRows").append(tr);return tr}
function readFerms(){return [...$("#fermRows").children].map(tr=>({name:tr.querySelector(".fn").value.trim(),category:tr.querySelector(".fc").value,
amount:num(tr.querySelector(".fa").value),unit:tr.querySelector(".fu").value,sugar_pct:num(tr.querySelector(".fp").value),is_balance:tr.querySelector(".fb").checked}))}
function readForm(){return {title:$("#fTitle").value.trim(),style:$("#fStyle").value,brew_date:$("#fDate").value,volume_l:num($("#fVolume").value),
yeast_name:$("#fYeast").value.trim(),yeast_tolerance:num($("#fTolerance").value),yeast_amount_g:num($("#fYeastAmount").value),og:num($("#fOg").value),
fg_expected:num($("#fFgExp").value),fg_measured:num($("#fFgMeas").value),recipe:$("#fRecipe").value,notes:$("#fNotes").value,
temp_target:num($("#fTempTarget").value),temp_start:num($("#fTempStart").value),temp_stop:num($("#fTempStop").value),fermentables:readFerms()}}
function fillForm(b){let v=b||{},status=v.status||"new",editable=status==="new"||status==="draft",set=(id,x)=>$(id).value=x??"";
set("#fTitle",v.title);set("#fStyle",v.style);set("#fDate",v.brew_date);set("#fVolume",v.volume_l);set("#fYeast",v.yeast_name);set("#fTolerance",v.yeast_tolerance);
set("#fYeastAmount",v.yeast_amount_g);set("#fOg",v.og);set("#fFgExp",v.fg_expected);set("#fFgMeas",v.fg_measured);set("#fRecipe",v.recipe);set("#fNotes",v.notes);set("#fTargetOg","");
let fresh=status==="new";set("#fTempTarget",fresh?18:v.temp_target);set("#fTempStart",fresh?19:v.temp_start);set("#fTempStop",fresh?17:v.temp_stop);
$("#fermRows").innerHTML="";(v.fermentables&&v.fermentables.length?v.fermentables:[{}]).forEach(fermRow);
document.querySelectorAll("#brewForm input,#brewForm select,#brewForm textarea,#addFerm,#estimate,#reverse,.fd").forEach(el=>el.disabled=!editable);
$("#fFgMeas").disabled=editable;let show=(id,on)=>$(id).style.display=on?"":"none";
show("#saveDraft",editable);show("#startBrew",editable);show("#deleteDraft",status==="draft");show("#saveFg",!editable);show("#endBrew",status==="active");
$("#estimateResult").textContent="";msg("",true);showAbv()}
function estimatedOg(d){let fs=d.fermentables.filter(f=>f.amount>0&&f.sugar_pct>0);if(!(d.volume_l>0)||!fs.length)return null;
return 1+fs.reduce((s,f)=>s+f.amount*f.sugar_pct/100*SUCROSE_POINTS/d.volume_l,0)/1000}
function showAbv(estOg){let d=readForm(),og=d.og||estOg,parts=[];if(og&&d.fg_expected)parts.push("预期酒精度 "+Math.max(0,(og-d.fg_expected)*131.25).toFixed(1)+"%"+(d.og?"":"（基于估算 OG）"));
if(d.og&&d.fg_measured)parts.push("实际酒精度 "+Math.max(0,(d.og-d.fg_measured)*131.25).toFixed(1)+"%");$("#abv").textContent=parts.join(" · ")}
async function update(){try{let s=await(await fetch("/api/status")).json();if(s.temperature!==null){$("#temp").textContent=s.temperature.toFixed(2)+"℃";$("#control").textContent=s.cooler_on?"制冷中":"已停止";$("#control").className="value "+(s.cooler_on?"error":"ok");$("#start").textContent=s.start.toFixed(2)+"℃";$("#stop").textContent=s.stop.toFixed(2)+"℃";if(!editing){$("#target").value=s.target;$("#startInput").value=s.start;$("#stopInput").value=s.stop}$("#status").textContent="电脑服务在线 · ESP32 "+(s.online?"在线":"暂时离线");}
let brew=s.active_brew;if(view==="overview")$("#viewSub").textContent=brew?`进行中：#${brew.id} ${brew.title}${brew.volume_l?"（"+brew.volume_l+" L）":""}`:"没有进行中的酿造，开始酿造后才会记录温度";
let sel=selectedBrew(),id=view==="overview"?(brew&&brew.id):view==="brew"&&sel&&sel.status!=="draft"?sel.id:null;
if(view!=="overview"&&!id)return;if(!id){draw([]);return}let q="&brew_id="+id;
let h=await(await fetch("/api/history?hours="+$("#range").value+q)).json();draw(h)}catch(e){$("#status").textContent="服务连接失败："+e.message}}
async function post(url,body){let r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})});return r.json()}
async function saveDraft(){let d=readForm();if(!d.title){msg("请填写标题",false);return null}let b=selectedBrew(),r=await post(b?"/api/brews/"+b.id:"/api/brews",d);
if(!r.ok){msg("保存失败："+r.error,false);return null}await refreshBrews(r.id);msg("草稿已保存",true);return r.id}
$("#saveDraft").onclick=saveDraft;
$("#startBrew").onclick=async()=>{if(!confirm("开始酿造后 ESP32 将启用自动制冷并开始记录温度，配方和 OG 将不能再修改。确认开始？"))return;
let id=await saveDraft();if(!id)return;let r=await post("/api/brews/"+id+"/start");if(!r.ok){msg("开始失败："+r.error,false);return}await refreshBrews(id);msg("已开始酿造",true);update()};
$("#saveFg").onclick=async()=>{let b=selectedBrew();if(!b)return;let r=await post("/api/brews/"+b.id,{fg_measured:num($("#fFgMeas").value)});
if(!r.ok){msg("保存失败："+r.error,false);return}await refreshBrews(b.id);msg("实测 FG 已保存",true)};
$("#endBrew").onclick=async()=>{let b=selectedBrew();if(!b||!confirm("确认结束酿造？将关闭制冷并停止记录温度。"))return;let r=await post("/api/brews/"+b.id+"/end");
if(!r.ok){msg("结束失败："+r.error,false);return}await refreshBrews(b.id);msg("酿造已结束",true);update()};
$("#deleteDraft").onclick=async()=>{let b=selectedBrew();if(!b||!confirm("确认删除草稿「"+b.title+"」？"))return;let r=await post("/api/brews/"+b.id+"/delete");
if(!r.ok){msg("删除失败："+r.error,false);return}await refreshBrews("");msg("草稿已删除",true)};
$("#addFerm").onclick=()=>fermRow({});
$("#estimate").onclick=()=>{let d=readForm(),og=estimatedOg(d);if(!og){msg("请先填写批次体积和可发酵糖用量",false);return}
let base=d.og||og,parts=["估算 OG "+og.toFixed(3)];if(d.yeast_tolerance>0){let fg=Math.max(0.996,base-d.yeast_tolerance/131.25);$("#fFgExp").value=fg.toFixed(3);
parts.push("预期 FG 已填入 "+fg.toFixed(3)+(d.og?"（基于实测 OG）":"（基于估算 OG）"))}else parts.push("填写酵母耐酒度后可估算预期 FG");
$("#estimateResult").textContent=parts.join(" · ");msg("",true);showAbv(og)};
$("#reverse").onclick=()=>{let d=readForm(),target=num($("#fTargetOg").value),idx=d.fermentables.findIndex(f=>f.is_balance);
if(!(d.volume_l>0&&target>1)){msg("请填写批次体积和目标 OG",false);return}if(idx<0){msg("请在可发酵糖中勾选一个补足原料",false);return}
let b=d.fermentables[idx];if(!(b.sugar_pct>0)){msg("补足原料的含糖率需大于 0",false);return}
let other=d.fermentables.reduce((s,f,i)=>i===idx||!(f.amount>0)?s:s+f.amount*f.sugar_pct/100*SUCROSE_POINTS/d.volume_l,0),need=(target-1)*1000-other;
if(need<=0){msg("其他原料已达到目标 OG，无需补足",false);return}let amount=need*d.volume_l/(b.sugar_pct/100*SUCROSE_POINTS);
$("#fermRows").children[idx].querySelector(".fa").value=amount.toFixed(2);msg((b.name||CATEGORY[b.category])+" 需要约 "+amount.toFixed(2)+" "+b.unit,true)};
["#fOg","#fFgExp","#fFgMeas"].forEach(id=>$(id).addEventListener("input",()=>showAbv()));
document.querySelectorAll(".nav[data-view]").forEach(a=>a.onclick=()=>go(a.dataset.view));$("#newBrew").onclick=()=>go("new");
window.addEventListener("resize",()=>chart.resize());$("#range").onchange=update;
refreshBrews().then(()=>go("overview"));setInterval(update,10000);
$("#settings").onsubmit=async e=>{e.preventDefault();let target=+$("#target").value,start=+$("#startInput").value,stop=+$("#stopInput").value;if(![target,start,stop].every(Number.isFinite)){$("#message").textContent="请输入三个温度值";$("#message").className="error";return}if(!(stop<target&&target<start)){$("#message").textContent="必须满足 停止 < 目标 < 启动";$("#message").className="error";return}let r=await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({target,start,stop})});let d=await r.json();$("#message").textContent=d.ok?"已保存并下发":"下发失败："+d.error;$("#message").className=d.ok?"ok":"error";if(d.ok){editing=false;update()}};
</script></main></div></body></html>"""


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.execute("""CREATE TABLE IF NOT EXISTS temperature (
        id INTEGER PRIMARY KEY, received_at TEXT NOT NULL, device_at_ms INTEGER,
        temperature REAL NOT NULL, cooler_on INTEGER NOT NULL, sensor_ok INTEGER NOT NULL,
        brew_id INTEGER
    )""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(temperature)")}
    if "brew_id" not in columns:
        connection.execute("ALTER TABLE temperature ADD COLUMN brew_id INTEGER")
    for column in ("device_boot", "device_seq"):
        if column not in columns:
            connection.execute(f"ALTER TABLE temperature ADD COLUMN {column} INTEGER")
    # Each ESP32 reading is identified by (boot, seq), so synced readings are never duplicated.
    connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS temperature_device_sample
        ON temperature(device_boot, device_seq)""")
    connection.execute("CREATE TABLE IF NOT EXISTS device_state (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
    brew_columns = {row[1] for row in connection.execute("PRAGMA table_info(brews)")}
    legacy = "batch" in brew_columns
    if legacy:
        # Keep the first-generation table instead of dropping it.
        connection.execute("ALTER TABLE brews RENAME TO brews_legacy")
    connection.execute("""CREATE TABLE IF NOT EXISTS brews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, style TEXT, brew_date TEXT, volume_l REAL,
        yeast_name TEXT, yeast_tolerance REAL, yeast_amount_g REAL,
        og REAL, fg_expected REAL, fg_measured REAL, recipe TEXT, notes TEXT,
        status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL,
        started_at TEXT, ended_at TEXT
    )""")
    brew_columns = {row[1] for row in connection.execute("PRAGMA table_info(brews)")}
    for column in ("temp_target", "temp_start", "temp_stop"):
        if column not in brew_columns:
            connection.execute(f"ALTER TABLE brews ADD COLUMN {column} REAL")
    connection.execute("""CREATE TABLE IF NOT EXISTS brew_fermentables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brew_id INTEGER NOT NULL REFERENCES brews(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,
        amount REAL NOT NULL, unit TEXT NOT NULL, sugar_pct REAL NOT NULL,
        is_balance INTEGER NOT NULL DEFAULT 0
    )""")
    if legacy:
        rows = connection.execute("""SELECT id,title,batch,yeast,initial_gravity,target_gravity,
            recipe,notes,started_at,ended_at,status FROM brews_legacy""").fetchall()
        for row in rows:
            connection.execute("""INSERT INTO brews(id,title,brew_date,volume_l,yeast_name,og,fg_expected,
                recipe,notes,status,created_at,started_at,ended_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row[0], row[1], (row[8] or "")[:10] or None, loose_float(row[2]), row[3],
                 loose_float(row[4]), loose_float(row[5]), row[6], row[7], row[10], row[8], row[8], row[9]))
    connection.execute("""CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY, value REAL NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS config_history (
        id INTEGER PRIMARY KEY, changed_at TEXT NOT NULL,
        target REAL NOT NULL, start REAL NOT NULL, stop REAL NOT NULL
    )""")
    for key, value in (("target", 18.0), ("start", 19.0), ("stop", 17.0)):
        connection.execute("INSERT OR IGNORE INTO config(key,value) VALUES (?,?)", (key, value))
    values = config_values(connection)
    first_temperature = connection.execute("SELECT MIN(received_at) FROM temperature").fetchone()[0]
    first_config = connection.execute("SELECT MIN(changed_at) FROM config_history").fetchone()[0]
    if first_config is None:
        first_config = first_temperature or datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO config_history(changed_at,target,start,stop) VALUES(?,?,?,?)",
            (first_config, values["target"], values["start"], values["stop"]),
        )
    elif first_temperature and first_temperature < first_config:
        connection.execute(
            "INSERT INTO config_history(changed_at,target,start,stop) VALUES(?,?,?,?)",
            (first_temperature, values["target"], values["start"], values["stop"]),
        )
    connection.commit()
    return connection


def config_values(connection):
    return {key: value for key, value in connection.execute("SELECT key,value FROM config")}


BREW_TEXT_FIELDS = ("title", "style", "brew_date", "yeast_name", "recipe", "notes")
BREW_NUMBER_FIELDS = ("volume_l", "yeast_tolerance", "yeast_amount_g", "og", "fg_expected",
                      "temp_target", "temp_start", "temp_stop")
BREW_COLUMNS = ("id", "title", "style", "brew_date", "volume_l", "yeast_name", "yeast_tolerance",
                "yeast_amount_g", "og", "fg_expected", "fg_measured", "recipe", "notes",
                "status", "created_at", "started_at", "ended_at", "temp_target", "temp_start", "temp_stop")
FERMENTABLE_CATEGORIES = {"honey", "sugar", "juice", "fruit", "other"}
STYLES = {"", "traditional", "melomel", "metheglin", "other"}


def loose_float(value):
    try:
        return float(str(value).strip().rstrip("Ll")) if value not in (None, "") else None
    except ValueError:
        return None


def optional_number(value, name):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(value)


def clean_brew(body):
    brew = {key: str(body.get(key) or "").strip() for key in BREW_TEXT_FIELDS}
    if not brew["title"]:
        raise ValueError("请填写标题")
    if brew["style"] not in STYLES:
        raise ValueError("invalid style")
    if brew["brew_date"]:
        try:
            datetime.strptime(brew["brew_date"], "%Y-%m-%d")
        except ValueError:
            raise ValueError("开始日期格式应为 YYYY-MM-DD") from None
    for key in BREW_NUMBER_FIELDS:
        brew[key] = optional_number(body.get(key), key)
    fermentables = []
    for item in body.get("fermentables") or []:
        amount = optional_number(item.get("amount"), "amount")
        if amount is None:
            continue
        category = item.get("category")
        unit = item.get("unit")
        sugar_pct = optional_number(item.get("sugar_pct"), "sugar_pct")
        if category not in FERMENTABLE_CATEGORIES or unit not in ("kg", "L"):
            raise ValueError("invalid fermentable")
        if sugar_pct is None or not 0 <= sugar_pct <= 100 or amount < 0:
            raise ValueError("含糖率需在 0～100 之间，用量不能为负")
        fermentables.append((str(item.get("name") or "").strip(), category, amount, unit,
                             sugar_pct, int(bool(item.get("is_balance")))))
    if sum(item[5] for item in fermentables) > 1:
        raise ValueError("只能选择一个补足原料")
    temps = (brew["temp_target"], brew["temp_start"], brew["temp_stop"])
    if any(t is not None for t in temps):
        if None in temps:
            raise ValueError("请完整填写目标、启动、停止三个温度")
        check_temperatures(*temps)
    return brew, fermentables


def check_temperatures(target, start, stop):
    if not 0 <= stop < target < start <= 40:
        raise ValueError("温度需满足 停止 < 目标 < 启动，且在 0～40℃ 之间")


def apply_config(target, start, stop):
    """Push thresholds to the ESP32, then persist them and their history."""
    check_temperatures(target, start, stop)
    request = urllib.request.Request(
        ESP32_URL + "/api/config",
        data=json.dumps({"target": target, "start": start, "stop": stop}, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("ESP32 rejected configuration")
    with DB_LOCK, db() as connection:
        connection.executemany("INSERT OR REPLACE INTO config(key,value) VALUES(?,?)",
                               (("target", target), ("start", start), ("stop", stop)))
        connection.execute("INSERT INTO config_history(changed_at,target,start,stop) VALUES(?,?,?,?)",
                           (datetime.now(timezone.utc).isoformat(), target, start, stop))
        connection.commit()


def save_fermentables(connection, brew_id, fermentables):
    connection.execute("DELETE FROM brew_fermentables WHERE brew_id=?", (brew_id,))
    connection.executemany("""INSERT INTO brew_fermentables(brew_id,position,name,category,amount,unit,
        sugar_pct,is_balance) VALUES(?,?,?,?,?,?,?,?)""",
        [(brew_id, position, *item) for position, item in enumerate(fermentables)])


def load_brews(connection, brew_id=None):
    sql = f"SELECT {','.join(BREW_COLUMNS)} FROM brews"
    rows = connection.execute(sql + (" WHERE id=?" if brew_id else " ORDER BY id DESC"),
                              (brew_id,) if brew_id else ()).fetchall()
    brews = [dict(zip(BREW_COLUMNS, row)) for row in rows]
    for brew in brews:
        brew["fermentables"] = [dict(zip(("name", "category", "amount", "unit", "sugar_pct", "is_balance"),
                                         (*row[:5], bool(row[5])))) for row in connection.execute(
            """SELECT name,category,amount,unit,sugar_pct,is_balance FROM brew_fermentables
            WHERE brew_id=? ORDER BY position""", (brew["id"],))]
    return brews


def iso_from_ms(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="microseconds")


def brew_for_time(connection, at):
    row = connection.execute("""SELECT id FROM brews WHERE status IN ('active','ended') AND started_at<=?
        AND (ended_at IS NULL OR ended_at>=?) ORDER BY id DESC LIMIT 1""", (at, at)).fetchone()
    return row[0] if row else None


def store_sample(connection, boot, sample):
    """Insert a reading if it falls inside a brew; returns True when a new row was written."""
    at = iso_from_ms(sample["ts_ms"])
    brew_id = brew_for_time(connection, at)
    if brew_id is None:
        return False
    cursor = connection.execute("""INSERT OR IGNORE INTO temperature(received_at,temperature,cooler_on,
        sensor_ok,brew_id,device_boot,device_seq) VALUES(?,?,?,1,?,?,?)""",
        (at, float(sample["t"]), int(bool(sample["on"])), brew_id, boot, sample.get("seq")))
    return cursor.rowcount == 1


def sync_cursor(connection):
    state = dict(connection.execute("SELECT key,value FROM device_state"))
    return state.get("boot", 0), state.get("seq", 0)


def set_sync_cursor(connection, boot, seq):
    connection.executemany("INSERT OR REPLACE INTO device_state(key,value) VALUES(?,?)",
                           (("boot", boot), ("seq", seq)))


def sync_from_esp32():
    """Request readings newer than the stored cursor from the ESP32 and backfill them."""
    if not SYNC_LOCK.acquire(blocking=False):
        return None
    inserted = 0
    try:
        while True:
            with DB_LOCK, db() as connection:
                boot, after = sync_cursor(connection)
            with urllib.request.urlopen(f"{ESP32_URL}/api/samples?boot={boot}&after={after}&limit=300",
                                        timeout=5) as response:
                data = json.loads(response.read())
            if not data.get("time_known"):
                SYNC_STATUS.update(error="ESP32 尚未获得时间，稍后再同步")
                return None
            samples = data.get("samples") or []
            with DB_LOCK, db() as connection:
                inserted += sum(store_sample(connection, data["boot"], s) for s in samples if s.get("ts_ms"))
                last = samples[-1]["seq"] if samples else (after if data["boot"] == boot else 0)
                set_sync_cursor(connection, data["boot"], last)
                connection.commit()
            if not data.get("more"):
                break
        SYNC_STATUS.update(at=datetime.now(timezone.utc).isoformat(), inserted=inserted, error=None)
        return inserted
    except Exception as error:
        SYNC_STATUS.update(error=str(error))
        return None
    finally:
        SYNC_LOCK.release()


def set_esp32_cooling(enabled):
    request = urllib.request.Request(
        ESP32_URL + "/api/control",
        data=json.dumps({"enabled": enabled}, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("ESP32 rejected cooling state")


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        payload = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            payload = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path.startswith("/static/"):
            file_path = (STATIC_DIR / path[len("/static/"):]).resolve()
            if STATIC_DIR.resolve() not in file_path.parents or not file_path.is_file():
                self.send_error(404)
                return
            payload = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", STATIC_TYPES.get(file_path.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(payload)
            return
        if path == "/api/status":
            with DB_LOCK, db() as connection:
                row = connection.execute("SELECT received_at,temperature,cooler_on FROM temperature ORDER BY id DESC LIMIT 1").fetchone()
                config = config_values(connection)
                brew = connection.execute("SELECT id,title,volume_l,started_at FROM brews WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
            if LATEST:
                row = (LATEST["received_at"], LATEST["temperature"], LATEST["cooler_on"])
            online = bool(row and datetime.fromisoformat(row[0]) > datetime.now(timezone.utc) - timedelta(seconds=35))
            self.send_json({"temperature": row[1] if row else None, "cooler_on": bool(row[2]) if row else False,
                            "received_at": row[0] if row else None, "online": online, "sync": SYNC_STATUS,
                            "active_brew": {"id": brew[0], "title": brew[1], "volume_l": brew[2], "started_at": brew[3]} if brew else None,
                            **config})
            return
        if path == "/api/brews":
            with DB_LOCK, db() as connection:
                brews = load_brews(connection)
            self.send_json(brews)
            return
        if path == "/api/history":
            hours = 24
            query = parse_qs(parsed.query)
            if query.get("hours"):
                hours = min(24 * 21, max(1, int(query["hours"][0])))
            brew_id = int(query["brew_id"][0]) if query.get("brew_id") else None
            if brew_id is None:
                # Temperature history only exists per brew.
                self.send_json([])
                return
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            until = datetime.now(timezone.utc).isoformat()
            with DB_LOCK, db() as connection:
                if brew_id is not None:
                    brew = connection.execute("SELECT started_at,ended_at,status FROM brews WHERE id=?", (brew_id,)).fetchone()
                    if not brew or not brew[0]:
                        self.send_json([])
                        return
                    # Active brews follow the selected range; finished brews show start to end.
                    since = max(brew[0], since) if brew[2] == "active" else brew[0]
                    until = brew[1] or until
                rows = connection.execute(
                    """SELECT t.received_at,t.temperature,t.cooler_on,
                    (SELECT h.target FROM config_history h WHERE h.changed_at<=t.received_at ORDER BY h.id DESC LIMIT 1),
                    (SELECT h.start FROM config_history h WHERE h.changed_at<=t.received_at ORDER BY h.id DESC LIMIT 1),
                    (SELECT h.stop FROM config_history h WHERE h.changed_at<=t.received_at ORDER BY h.id DESC LIMIT 1)
                    FROM temperature t WHERE t.received_at>=? AND t.received_at<=? AND (? IS NULL OR t.brew_id=?)
                    ORDER BY t.id""",
                    (since, until, brew_id, brew_id),
                ).fetchall()
            self.send_json([{"time": row[0], "temperature": row[1], "cooler_on": bool(row[2]),
                            "target": row[3], "start": row[4], "stop": row[5]} for row in rows])
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw) if raw else {}
        except (ValueError, json.JSONDecodeError):
            self.send_json({"error": "invalid JSON"}, 400)
            return
        if path == "/api/telemetry":
            now_ms = int(time.time() * 1000)
            received_at = iso_from_ms(now_ms)
            # Live status is kept even when no brew is recording.
            LATEST.update(received_at=received_at, temperature=float(body["temperature"]),
                          cooler_on=bool(body.get("cooler_on")))
            sample = dict(body.get("sample") or {"t": body["temperature"], "on": body.get("cooler_on")})
            sample["ts_ms"] = sample.get("ts_ms") or now_ms  # device clock not known yet
            boot, seq = body.get("boot"), sample.get("seq")
            gap = False
            with DB_LOCK, db() as connection:
                recorded = store_sample(connection, boot, sample)
                if boot is not None and seq is not None:
                    cursor_boot, cursor_seq = sync_cursor(connection)
                    gap = not (boot == cursor_boot and seq == cursor_seq + 1)
                    if not gap:
                        set_sync_cursor(connection, boot, seq)
                connection.commit()
            if gap:
                # Missed readings (or the ESP32 rebooted): ask it for its buffer.
                threading.Thread(target=sync_from_esp32, daemon=True).start()
            self.send_json({"ok": True, "recorded": recorded, "server_time_ms": now_ms})
            return
        if path == "/api/sync":
            inserted = sync_from_esp32()
            if inserted is None:
                self.send_json({"ok": False, "error": SYNC_STATUS.get("error") or "同步进行中"}, 409)
            else:
                self.send_json({"ok": True, "inserted": inserted})
            return
        if path == "/api/brews":
            try:
                brew, fermentables = clean_brew(body)
            except ValueError as error:
                self.send_json({"error": str(error)}, 400)
                return
            with DB_LOCK, db() as connection:
                cursor = connection.execute(
                    f"""INSERT INTO brews({','.join(brew)},status,created_at)
                    VALUES({','.join('?' * len(brew))},'draft',?)""",
                    (*brew.values(), datetime.now(timezone.utc).isoformat()))
                save_fermentables(connection, cursor.lastrowid, fermentables)
                connection.commit()
            self.send_json({"ok": True, "id": cursor.lastrowid})
            return
        parts = path.strip("/").split("/")
        if len(parts) in (3, 4) and parts[:2] == ["api", "brews"]:
            try:
                brew_id = int(parts[2])
            except ValueError:
                self.send_json({"error": "invalid brew id"}, 400)
                return
            self.handle_brew_action(brew_id, parts[3] if len(parts) == 4 else "update", body)
            return
        if path == "/api/config":
            try:
                target, start, stop = float(body["target"]), float(body["start"]), float(body["stop"])
                check_temperatures(target, start, stop)
            except (KeyError, TypeError, ValueError) as error:
                self.send_json({"error": str(error)}, 400)
                return
            try:
                apply_config(target, start, stop)
            except Exception as error:
                self.send_json({"error": str(error)}, 502)
                return
            self.send_json({"ok": True})
            return
        self.send_error(404)

    def handle_brew_action(self, brew_id, action, body):
        with DB_LOCK, db() as connection:
            row = connection.execute("SELECT status,title FROM brews WHERE id=?", (brew_id,)).fetchone()
            active = connection.execute("SELECT id FROM brews WHERE status='active' LIMIT 1").fetchone()
        if row is None:
            self.send_json({"error": "brew not found"}, 404)
            return
        status = row[0]
        now = datetime.now(timezone.utc).isoformat()
        if action == "update":
            if status == "draft":
                try:
                    brew, fermentables = clean_brew(body)
                except ValueError as error:
                    self.send_json({"error": str(error)}, 400)
                    return
                with DB_LOCK, db() as connection:
                    connection.execute(f"UPDATE brews SET {','.join(k + '=?' for k in brew)} WHERE id=?",
                                       (*brew.values(), brew_id))
                    save_fermentables(connection, brew_id, fermentables)
                    connection.commit()
            else:
                # After the brew starts only the measured FG remains editable.
                try:
                    fg_measured = optional_number(body.get("fg_measured"), "fg_measured")
                except ValueError as error:
                    self.send_json({"error": str(error)}, 400)
                    return
                with DB_LOCK, db() as connection:
                    connection.execute("UPDATE brews SET fg_measured=? WHERE id=?", (fg_measured, brew_id))
                    connection.commit()
            self.send_json({"ok": True, "id": brew_id})
        elif action == "start":
            if status != "draft":
                self.send_json({"error": "只有草稿可以开始酿造"}, 409)
                return
            if active:
                self.send_json({"error": f"已有进行中的酿造 #{active[0]}，请先结束"}, 409)
                return
            with DB_LOCK, db() as connection:
                temps = connection.execute("SELECT temp_target,temp_start,temp_stop FROM brews WHERE id=?",
                                           (brew_id,)).fetchone()
            try:
                # The brew's own settings become the initial thresholds.
                if None not in temps:
                    apply_config(*temps)
                set_esp32_cooling(True)
            except Exception as error:
                self.send_json({"error": "无法下发温控设置到 ESP32：" + str(error)}, 502)
                return
            with DB_LOCK, db() as connection:
                connection.execute("""UPDATE brews SET status='active',started_at=?,
                    brew_date=COALESCE(NULLIF(brew_date,''),?) WHERE id=?""",
                                   (now, datetime.now().strftime("%Y-%m-%d"), brew_id))
                connection.commit()
            self.send_json({"ok": True, "started_at": now})
        elif action == "end":
            if status != "active":
                self.send_json({"error": "只有进行中的酿造可以结束"}, 409)
                return
            try:
                set_esp32_cooling(False)
            except Exception as error:
                self.send_json({"error": "无法关闭 ESP32 制冷：" + str(error)}, 502)
                return
            with DB_LOCK, db() as connection:
                connection.execute("UPDATE brews SET ended_at=?,status='ended' WHERE id=?", (now, brew_id))
                connection.commit()
            self.send_json({"ok": True, "ended_at": now})
        elif action == "delete":
            if status != "draft":
                self.send_json({"error": "只能删除草稿"}, 409)
                return
            with DB_LOCK, db() as connection:
                connection.execute("DELETE FROM brew_fermentables WHERE brew_id=?", (brew_id,))
                connection.execute("DELETE FROM brews WHERE id=?", (brew_id,))
                connection.commit()
            self.send_json({"ok": True})
        else:
            self.send_error(404)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    with db():
        pass
    # Backfill anything the ESP32 buffered while this service was down.
    threading.Thread(target=sync_from_esp32, daemon=True).start()
    print(f"Temperature server: http://0.0.0.0:{PORT}/")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
