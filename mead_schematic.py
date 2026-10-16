"""生成恒温柜控制板原理图：python3 mead_schematic.py → mead_schematic.png / .svg"""
import schemdraw
import schemdraw.elements as elm

FONT = 'Arial Unicode MS'
TOP, BOT = 14, 0  # +12V 母线、GND 母线 y 坐标

d = schemdraw.Drawing(show=False)
d.config(font=FONT, fontsize=11, unit=2.5)


def pin(name, side, anchor=None):
    return elm.IcPin(name=name, side=side, anchorname=anchor or name)


def wire(p1, p2, shape='-'):
    d.add(elm.Wire(shape).at(p1).to(p2))


def dot(p):
    d.add(elm.Dot().at(p))


# ---- J1 电源输入 ----
j1 = d.add(elm.Ic(pins=[pin('−', 'right', 'N'), pin('+', 'right', 'P')],
                  pinspacing=2, edgepadH=0.6, size=(1.6, 3))
           .theta(0).at((0, 6)).label('J1\nDC 5.5×2.1\n12V / 5A\n电源输入', 'center', fontsize=12))
wire(j1.P, (1.5, TOP), '|-')
f1 = d.add(elm.Fuse().right().at((1.5, TOP)).length(3)
           .label('F1  5A', 'top').label('保险', 'bottom', fontsize=12))
wire(j1.N, (1.5, BOT), '|-')

# 母线（终点在负载画完后确定，见文件末尾）
d.add(elm.Label().at((6, TOP + 0.5)).label('+12V', color='#c62828', fontsize=13))
d.add(elm.Label().at((6, BOT - 0.6)).label('GND（公共地）', fontsize=13))
d.add(elm.Ground().at((3, BOT)))

# ---- U2 降压模块 ----
u2 = d.add(elm.Ic(pins=[pin('IN−', 'left', 'INN'), pin('IN+', 'left', 'INP'),
                        pin('OUT−', 'right', 'OUTN'), pin('OUT+', 'right', 'OUTP')],
                  pinspacing=2, edgepadH=0.8, size=(3.2, 3.6))
           .theta(0).at((9, 6)).label('U2  降压模块\n12V→5V ≥1A\nMP1584 / MP2307', 'top', fontsize=12))
dot((7.5, TOP)); wire((7.5, TOP), u2.INP, '|-')
dot((7.5, BOT)); wire((7.5, BOT), u2.INN, '|-')
dot((13.8, BOT)); wire(u2.OUTN, (13.8, BOT), '-|')

# D1：5V 防倒灌
d1 = d.add(elm.Schottky().right().at(u2.OUTP).length(3.5)
           .label('D1  SS34', 'top', fontsize=12))
d.add(elm.Label().at((d1.end[0] + 0.2, d1.end[1] + 0.45)).label('+5V', fontsize=14, halign="left"))

# ---- U1 ESP32 DevKit ----
PS = 1.5
u1 = d.add(elm.Ic(pins=[pin('GND', 'left', 'GNDL'), pin('5V (VIN)', 'left', 'V5'),
                        pin('GND', 'right', 'GNDR'), pin('GPIO4 (D4)', 'right', 'D4'),
                        pin('3V3', 'right', 'V33'), pin('GPIO13 (D13)', 'right', 'D13')],
                  pinspacing=PS, edgepadH=0.8, size=(5, 6.5))
           .theta(0).anchor('V5').at((d1.end[0] + 1.8, d1.end[1]))
           .label('U1\nESP32 DevKit\n(esp32dev)', 'center', fontsize=13))
wire(d1.end, u1.V5)
gx = u1.GNDL[0] - 1.2
dot((gx, BOT)); wire(u1.GNDL, (gx, BOT), '-|')

# ---- J5 DS18B20 探头 + R1 上拉 ----
xr = u1.D4[0] + 2.2
j5 = d.add(elm.Ic(pins=[pin('GND', 'left', 'G'), pin('DQ', 'left', 'DQ'), pin('VDD', 'left', 'VDD')],
                  pinspacing=PS, edgepadH=0.6, size=(4.5, 4))
           .theta(0).anchor('VDD').at((xr + 3.5, u1.V33[1]))
           .label('J5  3P 端子 → DS18B20 探头', 'top', fontsize=12))
wire(u1.V33, j5.VDD); wire(u1.D4, j5.DQ); wire(u1.GNDR, j5.G)
dot((xr, u1.V33[1])); dot((xr, u1.D4[1]))
d.add(elm.Resistor().down().at((xr, u1.V33[1])).to((xr, u1.D4[1]))
      .label('R1\n4.7kΩ', 'left', fontsize=12))
xg = j5.G[0] - 0.8
dot((xg, j5.G[1])); dot((xg, BOT)); wire((xg, j5.G[1]), (xg, BOT))
d.add(elm.Label().at(((u1.V33[0] + xr) / 2, u1.V33[1] + 0.35)).label('+3V3', fontsize=13))
d.add(elm.Label().at(((xr + j5.DQ[0]) / 2, u1.D4[1] + 0.35)).label('ONEWIRE', fontsize=13))

# ---- U3 MOSFET 模块（光耦隔离，低端开关） ----
xm = j5.VDD[0] + 7.5
u3 = d.add(elm.Ic(pins=[pin('GND', 'left', 'CG'), pin('PWM', 'left', 'PWM'),
                        pin('−', 'right', 'VN'), pin('LOAD', 'right', 'LD'), pin('+', 'right', 'VP')],
                  pinspacing=1.4, edgepadH=0.8, size=(5, 4.4))
           .theta(0).anchor('PWM').at((xm, u1.D13[1]))
           .label('U3  MOSFET 模块\n（LR7843 / AOD4184，光耦隔离）', 'top', fontsize=12))
wire(u1.D13, u3.PWM)
d.add(elm.Label().at(((u1.D13[0] + u3.PWM[0]) / 2, u1.D13[1] + 0.35)).label('COOL_EN', fontsize=13))
xc = u3.CG[0] - 0.9
dot((xc, BOT)); wire(u3.CG, (xc, u3.CG[1])); wire((xc, u3.CG[1]), (xc, BOT))
xo = u3.VP[0] + 1.0
dot((xo, TOP)); wire(u3.VP, (xo, u3.VP[1])); wire((xo, u3.VP[1]), (xo, TOP))
dot((xo, BOT)); wire(u3.VN, (xo, u3.VN[1])); wire((xo, u3.VN[1]), (xo, BOT))

# ---- 受控负载：TEC + 两个风扇并联在 +12V 与 LOAD 之间 ----
YL = 4.5  # LOAD 节点（负载负极汇流）
xl = u3.LD[0] + 2.2
wire(u3.LD, (xl, u3.LD[1])); wire((xl, u3.LD[1]), (xl, YL))
d.add(elm.Label().at((xl + 0.3, YL - 0.5)).label('LOAD（负载负极）', fontsize=13, halign='left', color='#6a1b9a'))
loads = [
    (xl + 5, 'rbox', 'J2 → TEC1\nTEC1-12703\n≈3A'),
    (xl + 11, 'motor', 'J3 → M1\n热端风扇\n12V'),
    (xl + 17, 'motor', 'J4 → M2\n冷端风扇\n12V'),
    (xl + 23, 'diode', 'D2  SS34\n续流二极管'),
]
for x, kind, text in loads:
    dot((x, TOP))
    if kind == 'rbox':
        e = elm.RBox().down().at((x, 10.5)).length(3)
    elif kind == 'motor':
        e = elm.Motor().down().at((x, 10.5)).length(3)
    else:
        e = elm.Schottky().up().at((x, 7.5)).length(3)  # 阳极接 LOAD，阴极接 +12V
    e = d.add(e)
    top_pt, bot_pt = (e.start, e.end) if kind != 'diode' else (e.end, e.start)
    wire((x, TOP), top_pt); wire(bot_pt, (x, YL))
    if x != loads[-1][0]:
        dot((x, YL))
    d.add(elm.Label().at((x + 0.9, 9)).label(text, fontsize=14, halign='left'))
d.add(elm.Line().at((xl, YL)).to((loads[-1][0], YL)).color('#6a1b9a'))
X_END = loads[-1][0]

# ---- 标题与说明 ----
d.add(elm.Label().at((0, TOP + 3)).label('4 L 蜂蜜酒恒温柜 · 控制板原理图（洞洞板版）', fontsize=22, halign='left'))
d.add(elm.Label().at((0, TOP + 1.9)).label('固件：esp32_ds18b20_test/src/main.cpp   SENSOR_PIN = 4，MOSFET_PIN = 13   ≥19℃ 开 / ≤17℃ 关', fontsize=12, halign='left', color='#555'))
notes = [
    '说明：',
    '1. TEC1、M1、M2 并联接在 U3 的 + 与 LOAD 之间，一起受控：D13 HIGH → 制冷 + 两个风扇同时运行；LOW → 全部停止。',
    '2. 粗线电流路径（J1 → F1 → U3 → 负载，约 3.5 A）用 1–1.5 mm² 软线 / WAGO 端子，不走洞洞板细线。',
    '3. U3 为光耦隔离模块，信号 GND 与 − 板上不相通；本板由 U2 从 12V 取电，ESP32 GND 本来就与 12V − 共地。',
    '4. 负载负极只接 LOAD，不得接公共 GND；12V 不得接 ESP32 任何引脚。D2 跨接负载，吸收风扇断开时的反向尖峰。',
    '5. U2 首次上电前空载调至 5.0 V；D1 防止 USB 烧录时与降压 5V 倒灌。R1 跨接 3V3 与 DQ。',
]
for i, t in enumerate(notes):
    d.add(elm.Label().at((0, BOT - 2 - i * 0.75)).label(t, fontsize=14, halign="left"))

d.add(elm.Line().at(f1.end).to((X_END, TOP)).color('#c62828'))
d.add(elm.Line().at((1.5, BOT)).to((X_END + 3, BOT)).color('#37474f'))

d.save('mead_schematic.svg')
d.save('mead_schematic.png', dpi=200)
