#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "secrets.h"  // WIFI_SSID / WIFI_PASSWORD, kept out of git; see secrets.example.h

constexpr uint8_t SENSOR_PIN = 4;   // Board label D4
constexpr uint8_t MOSFET_PIN = 13;  // Board label D13
constexpr unsigned long READ_INTERVAL_MS = 10000;
constexpr char AP_PASSWORD[] = "esp32temp";
constexpr char COMPUTER_SERVER_URL[] = "http://192.168.31.113:8098/api/telemetry";
constexpr size_t HISTORY_SIZE = 3600;  // About 10 hours at one sample per 10 seconds.
constexpr float DEFAULT_START_TEMPERATURE_C = 19.0f;
constexpr float DEFAULT_STOP_TEMPERATURE_C = 17.0f;
constexpr float DEFAULT_TARGET_TEMPERATURE_C = 18.0f;

OneWire oneWire(SENSOR_PIN);
DallasTemperature sensors(&oneWire);
WebServer server(80);
Preferences preferences;
unsigned long lastReadAt = 0;
unsigned long lastWiFiStatusAt = 0;
float currentTemperatureC = NAN;
bool coolerOn = false;
bool coolingEnabled = true;
float startTemperatureC = DEFAULT_START_TEMPERATURE_C;
float stopTemperatureC = DEFAULT_STOP_TEMPERATURE_C;
float targetTemperatureC = DEFAULT_TARGET_TEMPERATURE_C;
struct Sample {
  unsigned long atMs;
  uint32_t seq;
  float temperatureC;
  bool coolerOn;
};
Sample history[HISTORY_SIZE] = {};
size_t historyCount = 0;
size_t historyNext = 0;
uint32_t bootId = 0;           // Random per boot so the computer can tell sequences apart.
uint32_t nextSeq = 1;
bool serverClockKnown = false;
int64_t serverClockOffsetMs = 0;  // Unix ms minus millis(), learned from the computer.

const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>发酵箱温控</title>
<style>
body{margin:0;background:#101827;color:#e8eef8;font:15px system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:24px 16px}.card{padding:18px;margin:14px 0;
border:1px solid #2d3c55;border-radius:16px;background:#162238}
h1{margin:0 0 6px}.muted{color:#9eacc2}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.value{font-size:32px;font-weight:700;margin-top:7px}.status{color:#70d394}
label{display:block;color:#9eacc2;margin:8px 0 4px}input,select,button{font:inherit;border-radius:8px;
border:1px solid #415571;padding:9px;background:#0f192b;color:#fff}button{background:#2878e8;border:0;
cursor:pointer;margin-top:10px}.settings{display:flex;gap:16px;flex-wrap:wrap;align-items:end}
.settings label{min-width:125px}.settings button{height:39px}.ok{color:#70d394}.error{color:#ff8d8d}
canvas{width:100%;height:430px;display:block}.legend{display:flex;gap:16px;flex-wrap:wrap;color:#b8c5d8}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
@media(max-width:720px){.grid{grid-template-columns:repeat(2,1fr)}canvas{height:320px}}
</style></head><body><main>
<h1>发酵箱温控</h1><div id="status" class="muted">正在连接 ESP32…</div>
<section class="grid">
<div class="card"><div class="muted">当前温度</div><div id="temp" class="value">--.--℃</div></div>
<div class="card"><div class="muted">制冷状态</div><div id="control" class="value">--</div></div>
<div class="card"><div class="muted">启动温度</div><div id="start" class="value">--℃</div></div>
<div class="card"><div class="muted">停止温度</div><div id="stop" class="value">--℃</div></div>
</section>
<section class="card"><strong>温控设置</strong><form id="settings" class="settings">
<label>目标温度（℃）<input id="targetInput" type="number" step=".1" min="0" max="40"></label>
<label>启动温度（℃）<input id="startInput" type="number" step=".1" min="0" max="40"></label>
<label>停止温度（℃）<input id="stopInput" type="number" step=".1" min="0" max="40"></label>
<button>保存并立即应用</button><span id="message"></span></form>
<div class="muted">逻辑：温度高于启动温度制冷，低于停止温度停止；中间区间保持当前状态。</div></section>
<section class="card"><div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">
<strong>温度曲线</strong><select id="range"><option value="3">最近 3 小时</option>
<option value="6">最近 6 小时</option><option value="12">最近 12 小时</option>
<option value="24" selected>最近 24 小时</option></select></div>
<canvas id="chart" width="1060" height="430"></canvas>
<div class="legend"><span><i class="dot" style="background:#45a3ff"></i>实际温度</span>
<span><i class="dot" style="background:#f5c542"></i>目标温度</span>
<span><i class="dot" style="background:#ff8b7d"></i>启动温度</span>
<span><i class="dot" style="background:#70d394"></i>停止温度</span></div></section>
<script>
const $=s=>document.querySelector(s), c=$("#chart"),x=c.getContext("2d");let data=[];
function fmt(v){return Number(v).toFixed(2)}
function draw(d){data=d.values||[];x.clearRect(0,0,c.width,c.height);if(!data.length)return;
let W=c.width,H=c.height,L=58,R=20,T=20,B=42,vals=data.map(p=>p.t),
lo=Math.min(...vals,$("#stopInput").value)-.5,hi=Math.max(...vals,$("#startInput").value)+.5;
if(hi-lo<1)hi=lo+1;let y=v=>H-B-(v-lo)*(H-T-B)/(hi-lo), px=i=>L+i*(W-L-R)/Math.max(1,data.length-1);
x.font="12px system-ui";x.strokeStyle="#30425f";x.fillStyle="#9eacc2";x.lineWidth=1;
for(let i=0;i<6;i++){let yy=T+i*(H-T-B)/5,v=hi-i*(hi-lo)/5;x.beginPath();x.moveTo(L,yy);x.lineTo(W-R,yy);x.stroke();x.fillText(fmt(v),5,yy+4)}
let start=Number($("#startInput").value),stop=Number($("#stopInput").value),target=Number($("#targetInput").value);
x.fillStyle="#ff8b7d20";x.fillRect(L,y(hi),W-L-R,y(start)-y(hi));
x.fillStyle="#70d39418";x.fillRect(L,y(stop),W-L-R,y(start)-y(stop));
x.fillStyle="#5d9dff12";x.fillRect(L,y(stop),W-L-R,y(lo)-y(stop));
[[target,"#f5c542"],[start,"#ff8b7d"],[stop,"#70d394"]].forEach(([v,col])=>{x.strokeStyle=col;x.setLineDash([7,5]);
x.beginPath();x.moveTo(L,y(v));x.lineTo(W-R,y(v));x.stroke();x.setLineDash([])});
x.strokeStyle="#45a3ff";x.lineWidth=3;x.beginPath();data.forEach((p,i)=>i?x.lineTo(px(i),y(p.t)):x.moveTo(px(i),y(p.t)));x.stroke();
data.forEach((p,i)=>{if(p.on){x.fillStyle="#ff8b7d44";x.fillRect(px(i),T,Math.max(2,(W-L-R)/data.length),H-T-B)}});
x.strokeStyle="#45a3ff";x.lineWidth=3;x.beginPath();data.forEach((p,i)=>i?x.lineTo(px(i),y(p.t)):x.moveTo(px(i),y(p.t)));x.stroke()}
async function update(){try{let d=await(await fetch("/api/temperature")).json();
if(d.connected){$("#temp").textContent=fmt(d.temperature)+"℃";$("#control").textContent=d.coolerOn?"制冷中":"已停止";
$("#control").className="value "+(d.coolerOn?"error":"ok");$("#start").textContent=fmt(d.startTemperature)+"℃";
$("#stop").textContent=fmt(d.stopTemperature)+"℃";$("#targetInput").value=d.targetTemperature;
$("#startInput").value=d.startTemperature;$("#stopInput").value=d.stopTemperature;
$("#status").textContent="ESP32 在线 · D4 传感器正常 · D13 自动控制";$("#status").className="status"}}
let h=await(await fetch("/api/history?hours="+$("#range").value)).json();draw(h)}catch(e){$("#status").textContent="连接失败："+e.message}}
$("#settings").onsubmit=async e=>{e.preventDefault();let target=+$("#targetInput").value,start=+$("#startInput").value,stop=+$("#stopInput").value;
if(!(stop<target&&target<start)){$("#message").textContent="必须满足：停止温度 < 目标温度 < 启动温度";$("#message").className="error";return}
let r=await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({target,start,stop})});
let d=await r.json();$("#message").textContent=d.ok?"已保存并立即应用":d.error;$("#message").className=d.ok?"ok":"error";update()};
$("#range").onchange=update;update();setInterval(update,10000);
</script></main></body></html>)HTML";

const Sample& addTemperature(float temperatureC) {
  Sample& sample = history[historyNext];
  sample = {millis(), nextSeq++, temperatureC, coolerOn};
  historyNext = (historyNext + 1) % HISTORY_SIZE;
  if (historyCount < HISTORY_SIZE) ++historyCount;
  return sample;
}

// Current Unix time in ms: NTP first, then the computer's clock; 0 if unknown.
uint64_t nowEpochMs() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  if (tv.tv_sec > 1700000000) return (uint64_t)tv.tv_sec * 1000ULL + tv.tv_usec / 1000;
  if (serverClockKnown) return (uint64_t)(serverClockOffsetMs + (int64_t)millis());
  return 0;
}

// A sample's timestamp is derived from its millis() age, so it stays valid
// even if the clock was only learned after the reading was taken.
uint64_t sampleEpochMs(const Sample& sample) {
  uint64_t now = nowEpochMs();
  return now ? now - (uint64_t)(millis() - sample.atMs) : 0;
}

void appendSample(String& out, const Sample& sample) {
  char buffer[96];
  snprintf(buffer, sizeof(buffer), "{\"seq\":%lu,\"ts_ms\":%llu,\"t\":%.2f,\"on\":%s}",
           (unsigned long)sample.seq, (unsigned long long)sampleEpochMs(sample),
           sample.temperatureC, sample.coolerOn ? "true" : "false");
  out += buffer;
}

// GET /api/samples?boot=B&after=S&limit=N returns buffered samples newer than S.
void handleSamples() {
  uint32_t boot = server.hasArg("boot") ? strtoul(server.arg("boot").c_str(), nullptr, 10) : 0;
  uint32_t after = server.hasArg("after") ? strtoul(server.arg("after").c_str(), nullptr, 10) : 0;
  if (boot != bootId) after = 0;  // Rebooted since the last sync: everything buffered is new.
  long limit = server.hasArg("limit") ? constrain(server.arg("limit").toInt(), 1L, 500L) : 300L;
  String out;
  out.reserve(limit * 64 + 96);
  out = "{\"boot\":" + String(bootId) + ",\"latest\":" + String(nextSeq - 1) +
        ",\"time_known\":" + (nowEpochMs() ? "true" : "false") + ",\"samples\":[";
  size_t first = historyCount == HISTORY_SIZE ? historyNext : 0;
  long written = 0;
  bool more = false;
  for (size_t i = 0; i < historyCount; ++i) {
    const Sample& sample = history[(first + i) % HISTORY_SIZE];
    if (sample.seq <= after) continue;
    if (written == limit) {
      more = true;
      break;
    }
    if (written++) out += ",";
    appendSample(out, sample);
  }
  out += String("],\"more\":") + (more ? "true" : "false") + "}";
  server.send(200, "application/json", out);
}

void handleRoot() {
  server.send_P(200, "text/html; charset=utf-8", INDEX_HTML);
}

void handleTemperature() {
  String response = "{\"connected\":";
  response += isnan(currentTemperatureC) ? "false" : "true";
  if (!isnan(currentTemperatureC)) {
    response += ",\"temperature\":";
    response += String(currentTemperatureC, 2);
  }
  response += ",\"coolerOn\":";
  response += coolerOn ? "true" : "false";
  response += ",\"startTemperature\":";
  response += String(startTemperatureC, 2);
  response += ",\"stopTemperature\":";
  response += String(stopTemperatureC, 2);
  response += ",\"targetTemperature\":";
  response += String(targetTemperatureC, 2);
  response += "}";
  server.send(200, "application/json", response);
}

void handleHistory() {
  unsigned long hours = server.hasArg("hours") ? server.arg("hours").toInt() : 24;
  hours = constrain(hours, 1UL, 10UL);
  unsigned long windowMs = hours * 3600000UL;
  unsigned long now = millis();
  String response = "{\"values\":[";
  size_t first = historyCount == HISTORY_SIZE ? historyNext : 0;
  bool wrote = false;
  for (size_t i = 0; i < historyCount; ++i) {
    const Sample& sample = history[(first + i) % HISTORY_SIZE];
    if (now - sample.atMs > windowMs) continue;
    if (wrote) response += ",";
    response += "{\"t\":" + String(sample.temperatureC, 2);
    response += ",\"on\":" + String(sample.coolerOn ? "true" : "false") + "}";
    wrote = true;
  }
  response += "]}";
  server.send(200, "application/json", response);
}

void handleConfig() {
  if (server.method() != HTTP_POST) {
    server.send(405, "application/json", "{\"error\":\"POST required\"}");
    return;
  }
  String body = server.arg("plain");
  int targetIndex = body.indexOf("\"target\":");
  int startIndex = body.indexOf("\"start\":");
  int stopIndex = body.indexOf("\"stop\":");
  if (targetIndex < 0 || startIndex < 0 || stopIndex < 0) {
    server.send(400, "application/json", "{\"error\":\"invalid config\"}");
    return;
  }
  float newTarget = body.substring(targetIndex + 9).toFloat();
  float newStart = body.substring(startIndex + 8).toFloat();
  float newStop = body.substring(stopIndex + 7).toFloat();
  if (!(newStop < newTarget && newTarget < newStart) ||
      newStop < 0 || newStart > 40) {
    server.send(400, "application/json", "{\"error\":\"stop < target < start and 0-40 C required\"}");
    return;
  }
  targetTemperatureC = newTarget;
  startTemperatureC = newStart;
  stopTemperatureC = newStop;
  preferences.putFloat("target", targetTemperatureC);
  preferences.putFloat("start", startTemperatureC);
  preferences.putFloat("stop", stopTemperatureC);
  server.send(200, "application/json", "{\"ok\":true}");
}

void setCooler(bool enabled, const char* reason);

void handleControl() {
  String body = server.arg("plain");
  // Accept both {"enabled":true} and {"enabled": true}.
  int key = body.indexOf("\"enabled\"");
  int value = key < 0 ? -1 : body.indexOf("true", key);
  int comma = key < 0 ? -1 : body.indexOf(",", key);
  coolingEnabled = value >= 0 && (comma < 0 || value < comma);
  preferences.putBool("cooling", coolingEnabled);
  if (!coolingEnabled) setCooler(false, "cooling disabled by brew state");
  server.send(200, "application/json", String("{\"ok\":true,\"enabled\":") + (coolingEnabled ? "true}" : "false}"));
}

void connectWiFi() {
  if (WIFI_SSID[0] == '\0') {
    WiFi.mode(WIFI_AP);
    WiFi.softAP("ESP32-Temperature", AP_PASSWORD);
    Serial.print("Wi-Fi credentials are empty; started setup AP at ");
    Serial.println(WiFi.softAPIP());
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  unsigned long startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 20000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected; open http://");
    Serial.println(WiFi.localIP());
  } else {
    WiFi.mode(WIFI_AP);
    WiFi.softAP("ESP32-Temperature", AP_PASSWORD);
    Serial.print("Wi-Fi failed; started fallback AP at ");
    Serial.println(WiFi.softAPIP());
  }
}

void setCooler(bool enabled, const char* reason) {
  if (coolerOn == enabled) return;
  coolerOn = enabled;
  digitalWrite(MOSFET_PIN, coolerOn ? HIGH : LOW);
  Serial.print("Cooler ");
  Serial.print(coolerOn ? "ON" : "OFF");
  Serial.print(" (");
  Serial.print(reason);
  Serial.println(")");
}

void updateTemperatureControl(float temperatureC) {
  if (!coolingEnabled) {
    setCooler(false, "cooling disabled");
    return;
  }
  if (temperatureC > startTemperatureC) {
    setCooler(true, "above start temperature");
  } else if (temperatureC < stopTemperatureC) {
    setCooler(false, "below stop temperature");
  }
}

void uploadTelemetry(const Sample& sample) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient client;
  client.begin(COMPUTER_SERVER_URL);
  client.setTimeout(1500);
  client.addHeader("Content-Type", "application/json");
  String payload = "{\"device_at_ms\":" + String(sample.atMs);
  payload += ",\"boot\":" + String(bootId);
  payload += ",\"temperature\":" + String(sample.temperatureC, 2);
  payload += ",\"cooler_on\":" + String(sample.coolerOn ? "true" : "false");
  payload += ",\"sensor_ok\":true,\"sample\":";
  appendSample(payload, sample);
  payload += "}";
  int status = client.POST(payload);
  if (status == 200) {
    // Learn the computer's clock as a fallback when NTP is unavailable.
    String body = client.getString();
    int key = body.indexOf("\"server_time_ms\":");
    if (key >= 0) {
      uint64_t serverMs = strtoull(body.c_str() + key + 17, nullptr, 10);
      if (serverMs > 1700000000000ULL) {
        serverClockOffsetMs = (int64_t)serverMs - (int64_t)millis();
        serverClockKnown = true;
      }
    }
  }
  Serial.print("Computer upload HTTP status: ");
  Serial.println(status);
  client.end();
}

void setup() {
  pinMode(MOSFET_PIN, OUTPUT);
  digitalWrite(MOSFET_PIN, LOW);

  Serial.begin(115200);
  delay(1000);

  sensors.begin();
  sensors.setResolution(12);
  preferences.begin("temp-control", false);
  startTemperatureC = preferences.getFloat("start", DEFAULT_START_TEMPERATURE_C);
  stopTemperatureC = preferences.getFloat("stop", DEFAULT_STOP_TEMPERATURE_C);
  targetTemperatureC = preferences.getFloat("target", DEFAULT_TARGET_TEMPERATURE_C);
  coolingEnabled = preferences.getBool("cooling", true);

  Serial.println();
  Serial.println("ESP32 single DS18B20 test");
  Serial.print("Sensors found: ");
  Serial.println(sensors.getDeviceCount());
  Serial.println("D4=data, D13=MOSFET control");
  Serial.print("Auto control: ON above ");
  Serial.print(startTemperatureC, 1);
  Serial.print(" C, OFF below ");
  Serial.print(stopTemperatureC, 1);
  Serial.println(" C");

  connectWiFi();
  bootId = esp_random();
  configTime(0, 0, "ntp.aliyun.com", "cn.pool.ntp.org", "pool.ntp.org");  // UTC
  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/temperature", HTTP_GET, handleTemperature);
  server.on("/api/history", HTTP_GET, handleHistory);
  server.on("/api/samples", HTTP_GET, handleSamples);
  server.on("/api/config", HTTP_POST, handleConfig);
  server.on("/api/control", HTTP_POST, handleControl);
  server.begin();
  Serial.println("HTTP server started on port 80");
}

void loop() {
  server.handleClient();
  if (millis() - lastWiFiStatusAt >= 10000) {
    lastWiFiStatusAt = millis();
    Serial.print("Wi-Fi status: ");
    Serial.print(WiFi.status() == WL_CONNECTED ? "connected, http://" : "AP mode, http://");
    Serial.println(WiFi.status() == WL_CONNECTED ? WiFi.localIP() : WiFi.softAPIP());
  }
  if (millis() - lastReadAt < READ_INTERVAL_MS) {
    delay(10);
    return;
  }
  lastReadAt = millis();

  sensors.requestTemperatures();
  const float temperatureC = sensors.getTempCByIndex(0);

  if (temperatureC == DEVICE_DISCONNECTED_C) {
    setCooler(false, "sensor disconnected");
    Serial.println("ERROR: DS18B20 not detected (-127 C)");
  } else if (temperatureC == 85.0f) {
    setCooler(false, "invalid sensor reading");
    Serial.println("WARNING: DS18B20 returned 85 C; check wiring/power");
  } else {
    currentTemperatureC = temperatureC;
    updateTemperatureControl(temperatureC);
    uploadTelemetry(addTemperature(temperatureC));
    Serial.print("Bucket wall: ");
    Serial.print(temperatureC, 2);
    Serial.println(" C");
  }
}
