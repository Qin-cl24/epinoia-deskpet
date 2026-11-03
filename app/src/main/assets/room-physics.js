/* 小屋物理层 —— cannon-es 刚体 + 真实重力 9.8 m/s²
 *
 * 由 room.html 引入（<script src="vendor/cannon-es.js"> + <script src="room-physics.js">）。
 * 给「底部家具」（床 / 饭碗 / 收音机 / 台灯）各挂一个刚体 + 立方体碰撞体，
 * 开场时全部悬在半空，靠重力自由下落，撞到地板（静态碰撞体）后停住。
 *
 * ── 两套坐标系要换算 ──
 *   CSS 小屋：x 向右(0..420)、y 向下（地板 y=0，负数是「上」）、z 进深(0..500)
 *   物理世界：Y 向上，所以  phys.y = -css.y / S
 *   尺度 S = 100 CSS px = 1 米（房间 4.2 × 5 × 3 米、家具尺寸正好是现实尺度），
 *   这样重力就能老老实实用 9.8 m/s²，下落时间 ≈ 真实手感，不用瞎调系数。
 *
 * ── 为什么 fixedRotation ──
 *   家具是「一张立面 + 顶面 + 侧面」拼出来的立体错觉，不是真盒子；
 *   让它翻滚会立刻露馅（侧墙会跟着歪）。所以只做平动下落，落地永远正着。
 *
 * ── 位置怎么对上 ──
 *   .item  -> translate3d(刚体 x, 0, 刚体 z)   永远贴地：影子、光斑留在原地
 *   .sprite -> translateY(-离地高度)            家具本体随刚体上升/下落
 *   离地越高阴影越小越淡，落地瞬间正好 100%，这就是「砸到地板」的观感。
 */
(function () {
  'use strict';

  function log(s) {
    try { window.RoomBridge && RoomBridge.note(s); } catch (e) { /* 没有桥就算了 */ }
  }

  var C = window.CANNON;
  if (!C) { log('phys: CANNON 没加载，家具保持静态摆放'); return; }

  var S = 100;                 // 1 米 = 100 CSS px
  var GRAVITY = 9.8;           // m/s²
  var FIXED = 1 / 60;          // 固定步长

  var world = new C.World({ gravity: new C.Vec3(0, -GRAVITY, 0), allowSleep: true });
  world.broadphase = new C.SAPBroadphase(world);
  world.defaultContactMaterial.friction = 0.35;
  world.defaultContactMaterial.restitution = 0.02;   // 落地基本不弹，闷闷的一下
  world.solver.iterations = 10;

  /* ── 静态碰撞体：地板 + 后墙 + 左墙（房间尺寸与 build-room.py 里的 W/D/H 一致）──
     cy 用「离地高度」写（正数向上），内部再换成物理坐标。 */
  var ROOM_W = 420, ROOM_D = 500, ROOM_H = 300;
  function addStatic(wPx, hPx, dPx, cx, cy, cz) {
    var body = new C.Body({
      mass: 0,
      type: C.Body.STATIC,
      shape: new C.Box(new C.Vec3(wPx / S / 2, hPx / S / 2, dPx / S / 2))
    });
    body.position.set(cx / S, cy / S, cz / S);
    world.addBody(body);
    return body;
  }
  addStatic(ROOM_W, 56, ROOM_D, ROOM_W / 2, -28, ROOM_D / 2);   // 地板：56px 厚的板，顶面正好在 y=0
  addStatic(ROOM_W, ROOM_H, 36, ROOM_W / 2, ROOM_H / 2, -18);   // 后墙（z=0 面外侧）
  addStatic(36, ROOM_H, ROOM_D, -18, ROOM_H / 2, ROOM_D / 2);   // 左墙（x=0 面外侧）

  /* ── 家具刚体：尺寸/位置都从 DOM 的 data-* 读，布局仍然只有生成器一个源头 ── */
  var items = [];
  function setupItem(el) {
    var dims = (el.dataset.phys || '').split(',').map(parseFloat);   // w(px), d(px), h(px)
    if (dims.length < 3 || !isFinite(dims[0])) return;
    var wPx = dims[0], dPx = dims[1], hPx = dims[2];
    var x0 = parseFloat(el.dataset.x) || 0;
    var z0 = parseFloat(el.dataset.z) || 0;
    var dropPx = parseFloat(el.dataset.drop || 200);
    var mass = parseFloat(el.dataset.mass || 5);

    var body = new C.Body({
      mass: mass,
      shape: new C.Box(new C.Vec3(wPx / S / 2, hPx / S / 2, dPx / S / 2)),
      position: new C.Vec3(x0 / S, (hPx / 2 + dropPx) / S, z0 / S),
      fixedRotation: true,        // 只平动：立方体错觉经不起翻滚
      allowSleep: true,
      sleepSpeedLimit: 0.08,
      sleepTimeLimit: 0.3,
      linearDamping: 0.02
    });
    world.addBody(body);

    items.push({
      id: el.id,
      el: el,
      body: body,
      halfH: hPx / 2,
      dropPx: dropPx,
      sprite: el.querySelector('.sprite'),
      shadow: el.querySelector('.pshadow')
    });
  }
  [].forEach.call(document.querySelectorAll('[data-phys]'), setupItem);

  /* ── 刚体 -> DOM ── */
  function sync() {
    var awake = 0;
    for (var i = 0; i < items.length; i++) {
      var f = items[i], b = f.body;
      var px = b.position.x * S, py = b.position.y * S, pz = b.position.z * S;
      var up = py - f.halfH;                       // 离地高度（px，向上为正）
      if (up < 0.05) up = 0;                       // 落地后别再抖出亚像素
      f.el.style.transform = 'translate3d(' + px.toFixed(2) + 'px,0,' + pz.toFixed(2) + 'px)';
      if (f.sprite) f.sprite.style.transform = 'translateX(-50%) translateY(' + (-up).toFixed(2) + 'px)';
      if (f.shadow) {
        var k = Math.max(0, Math.min(1, 1 - up / 240));   // 1 = 贴地
        f.shadow.style.transform = 'rotateX(-90deg) scale(' + (0.55 + 0.45 * k).toFixed(3) + ')';
        f.shadow.style.opacity = (0.3 + 0.7 * k).toFixed(3);
      }
      if (b.sleepState !== C.Body.SLEEPING) awake++;
    }
    return awake;
  }

  /* ── 主循环：全部睡着就停 RAF，别白烧电 ── */
  var running = false, lastT = 0, acc = 0, frameNo = 0;
  function tick(t) {
    if (!running) return;
    try {
      var dt = lastT ? Math.min(0.05, (t - lastT) / 1000) : FIXED;
      lastT = t;
      acc += dt;
      var n = 0;
      while (acc >= FIXED && n < 5) { world.step(FIXED); acc -= FIXED; n++; }
      var awake = sync();
      frameNo++;
      if (frameNo % 30 === 0) log('phys 心跳 #' + frameNo + ' awake=' + awake + ' ' + heights());
      if (!awake) { running = false; lastT = 0; report(); return; }
      requestAnimationFrame(tick);
    } catch (err) {
      running = false; lastT = 0;
      log('phys 异常 ' + (err && err.message ? err.message : err));
    }
  }
  function heights() {
    var s = [];
    for (var i = 0; i < items.length; i++) {
      var f = items[i];
      s.push(f.id.replace('item', '') + '=' + (f.body.position.y * S - f.halfH).toFixed(1));
    }
    return s.join(' ');
  }
  function start() {
    if (running) return;
    running = true; lastT = 0; acc = 0; frameNo = 0;
    log('phys start rAF');
    requestAnimationFrame(tick);
  }
  function report() {
    var out = [];
    for (var i = 0; i < items.length; i++) {
      var f = items[i];
      out.push(f.id + '=' + (f.body.position.y * S - f.halfH).toFixed(1) + 'px@'
        + (f.body.position.x * S).toFixed(0) + ',' + (f.body.position.z * S).toFixed(0));
    }
    log('phys settled 离地高@x,z ' + out.join(' | '));
  }

  /* ── 重新落一遍（点地毯触发，调试也用它）── */
  function drop() {
    for (var i = 0; i < items.length; i++) {
      var f = items[i];
      f.body.wakeUp();
      f.body.velocity.set(0, 0, 0);
      f.body.angularVelocity.set(0, 0, 0);
      f.body.position.set(
        (parseFloat(f.el.dataset.x) || 0) / S,
        (f.halfH + f.dropPx) / S,
        (parseFloat(f.el.dataset.z) || 0) / S
      );
      f.body.force.set(0, 0, 0);
    }
    sync();
    start();
    log('phys drop 重放 ' + items.length + ' 件');
  }

  sync();                        // 先把家具摆到半空（首帧就位，不会有「先落地再弹起」的跳变）
  window.RoomPhys = { drop: drop, world: world, items: items };
  setTimeout(start, 240);        // 让页面先画出来，再开始掉
  log('phys ready ' + items.length + ' 件家具 gravity=' + GRAVITY + 'm/s² 尺度=' + S + 'px/m');
})();
