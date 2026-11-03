/* 无头验证小屋物理：假 DOM + 虚拟时钟驱动 requestAnimationFrame
 * 用法：node phys-test.js   （在 assets 目录跑；数据全部取自真实产物 room.html）
 */
const fs = require('fs');
const ASSETS = '/data/data/com.termux/files/home/AI-Live-Overflow/app/src/main/assets/';
const html = fs.readFileSync(ASSETS + 'room.html', 'utf8');

// ---- 1. 从产物里抓出挂物理的家具（真实 data-* 值）----
const found = [];
const itemRe = /<div class="item[^"]*"\s+id="([\w]+)"([\s\S]*?)style="/g;
let m;
while ((m = itemRe.exec(html))) {
  const id = m[1], attrs = m[2];
  if (!/data-phys=/.test(attrs)) continue;
  const get = (k) => { const r = attrs.match(new RegExp(k + '="([^"]+)"')); return r ? r[1] : null; };
  found.push({ id, phys: get('data-phys'), x: get('data-x'), z: get('data-z'), drop: get('data-drop'), mass: get('data-mass') });
}
console.log('从 room.html 读到家具：', found.map(f => f.id + '(' + f.phys + ')').join(' '));

// ---- 2. 假 DOM ----
const logs = [];
function mkEl(desc) {
  const el = {
    id: desc.id,
    dataset: { phys: desc.phys, x: desc.x, z: desc.z, drop: desc.drop, mass: desc.mass },
    style: {},
    classList: { toggle: () => false, add() {}, remove() {} },
    _sprite: { style: {} },
    _shadow: { style: {} },
    querySelector(sel) { return sel === '.sprite' ? this._sprite : sel === '.pshadow' ? this._shadow : null; }
  };
  return el;
}
const els = found.map(mkEl);
const byId = {};
els.forEach(e => { byId[e.id] = e; });

global.window = global;
global.document = {
  querySelectorAll: (sel) => (sel === '[data-phys]' ? els : []),
  getElementById: (id) => byId[id] || null
};
global.RoomBridge = { note: (s) => logs.push(s) };

// 虚拟时钟：收集 RAF 回调，由驱动循环按虚拟时间喂进去
let rafQueue = [];
global.requestAnimationFrame = (fn) => { rafQueue.push(fn); return rafQueue.length; };
const timers = [];
global.setTimeout = (fn, ms) => { timers.push({ fn, at: ms }); return timers.length; };

// ---- 3. 装载引擎 + 物理层（真实文件，不是复刻）----
eval(fs.readFileSync(ASSETS + 'vendor/cannon-es.js', 'utf8'));
eval(fs.readFileSync(ASSETS + 'room-physics.js', 'utf8'));

// ---- 4. 驱动 ----
let vnow = 0;
const STEP = 1000 / 60;
let frames = 0;
// 先跑定时器（physics 里 setTimeout(start, 240)）
timers.splice(0).forEach(t => { if (t.at <= 240) rafQueue.length; });
// 简化：直接把统计起点定在 240ms 之后
vnow = 240;
// 触发最初的 start()：rebuild 时 setTimers 已收集，直接手动再调一次
// （room-physics 暴露 window.RoomPhys，但 start 是内部的 —— 走 drop() 同样能起循环）
const t0 = Date.now();
for (let i = 0; i < 600; i++) {
  vnow += STEP;
  const q = rafQueue; rafQueue = [];
  if (!q.length) { window.RoomPhys.drop(); vnow += STEP; continue; }   // 循环没起来就踢一脚
  q.forEach(fn => fn(vnow));
  frames++;
  // 全部睡死之后 rafQueue 会空，下一轮上面会 drop 重新跑一遍 —— 用来测重放
  if (logs.some(s => s.includes('settled')) && frames > 5) break;
}

// ---- 5. 断言 ----
let bad = 0;
console.log('\n=== 落地结果（离地高度应为 0.0px，位置应等于设计坐标）===');
found.forEach((f, i) => {
  const el = byId[f.id];
  const t = el._sprite.style.transform || '';
  const mUp = t.match(/translateY\(([-\d.]+)px\)/);
  const up = mUp ? -parseFloat(mUp[1]) : NaN;
  const item = el.style.transform || '';
  const mPos = item.match(/translate3d\(([-\d.]+)px,0,([-\d.]+)px\)/);
  const px = mPos ? parseFloat(mPos[1]) : NaN;
  const pz = mPos ? parseFloat(mPos[2]) : NaN;
  const okUp = Math.abs(up) < 0.06;
  const okX = Math.abs(px - parseFloat(f.x)) < 0.06;
  const okZ = Math.abs(pz - parseFloat(f.z)) < 0.06;
  if (!(okUp && okX && okZ)) bad++;
  console.log(
    (okUp && okX && okZ ? '  ✓ ' : '  ✗ ') + f.id.padEnd(9) +
    ' 离地 ' + up.toFixed(2).padStart(6) + 'px' +
    '  落点 ' + px.toFixed(1) + ',' + pz.toFixed(1) +
    ' (设计 ' + f.x + ',' + f.z + ')'
  );
});

console.log('\n=== 物理层日志 ===');
logs.slice(0, 4).forEach(s => console.log('  ' + s));
const settled = logs.find(s => s.includes('settled'));
if (settled) console.log('  ' + settled);
console.log('\n驱动帧数 ' + frames + '，虚拟时长 ' + (vnow / 1000).toFixed(2) + 's，真实耗时 ' + (Date.now() - t0) + 'ms');
process.exit(bad ? 1 : 0);
