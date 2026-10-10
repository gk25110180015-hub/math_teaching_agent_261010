function draw(ctx, t, p) {
  var W = 960, H = 540;
  var z = Number(t);
  if (!isFinite(z)) z = 0;
  z = Math.max(0, Math.min(1, z));
  var mag = Number(p && p.h);
  if (!isFinite(mag)) mag = 0.5;
  mag = Math.max(0.01, Math.min(1, mag));
  var preset = Number(p && p.preset);
  preset = preset >= 0.5 ? 1 : 0;
  var display = Math.round(Number(p && p.display));
  if (!isFinite(display)) display = 0;
  display = Math.max(0, Math.min(2, display));

  var sec = z * 34;
  var scene = sec < 10 ? 1 : (sec < 22 ? 2 : 3);
  var local = scene === 1 ? sec / 10 : (scene === 2 ? (sec - 10) / 12 : (sec - 22) / 12);
  var isX2 = preset === 0;
  var a = 1;
  function f(x) { return isX2 ? x * x : 2 * x + 1; }
  function derivative() { return 2; }
  function fmt(x, n) { return (isFinite(x) ? x : 0).toFixed(n || 2); }
  function txt(s, x, y, size, color, align) {
    ctx.font = (size || 17) + 'px sans-serif';
    ctx.fillStyle = color || '#263238';
    ctx.textAlign = align || 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(s), x, y);
  }
  function line(x1, y1, x2, y2, color, width, dash) {
    ctx.save();
    ctx.strokeStyle = color || '#263238';
    ctx.lineWidth = width || 2;
    ctx.setLineDash(dash || []);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.restore();
  }
  function dot(x, y, r, color) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }

  var h;
  if (scene === 1) {
    h = mag * (1 - 0.55 * Math.min(1, local));
  } else if (scene === 2) {
    var q = local < 0.5 ? local * 2 : (local - 0.5) * 2;
    var side = local < 0.5 ? 1 : -1;
    h = side * (0.02 + mag * (1 - q));
  } else {
    var seq = [1, 0.5, 0.1, 0.01];
    var k = Math.min(3, Math.floor(local * 4));
    h = seq[k];
  }
  if (Math.abs(h) < 0.001) h = h < 0 ? -0.001 : 0.001;

  var ya = f(a), xb = a + h, yb = f(xb), dy = yb - ya;
  var slope = dy / h, tangent = derivative();
  var hp = scene === 2 ? Math.abs(h) : Math.max(0.01, Math.abs(h));
  var ym = (f(a - hp) - f(a)) / (-hp);
  var yp = (f(a + hp) - f(a)) / hp;

  ctx.fillStyle = '#f8fbff';
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(35, 85, 890, 350);
  ctx.strokeStyle = '#d2e0ea';
  ctx.lineWidth = 1;
  ctx.strokeRect(35, 85, 890, 350);

  var title = scene === 1 ? '第1幕：两点确定割线' : (scene === 2 ? '第2幕：双侧逼近切线' : '第3幕：具体计算');
  txt(title, 55, 103, 21, '#6b3fa0');

  var left = 65, top = 120, bottom = 390, plotW = 575, plotH = 255;
  var xmin = -1, xmax = 3.2, ymin = -1, ymax = 10;
  function X(x) { return left + (x - xmin) / (xmax - xmin) * plotW; }
  function Y(y) { return bottom - (y - ymin) / (ymax - ymin) * plotH; }

  for (var gx = -1; gx <= 3; gx++) line(X(gx), Y(ymin), X(gx), Y(ymax), '#e6eef4', 1);
  for (var gy = 0; gy <= 10; gy += 2) line(X(xmin), Y(gy), X(xmax), Y(gy), '#e6eef4', 1);
  line(X(xmin), Y(0), X(xmax), Y(0), '#40566b', 2);
  line(X(0), Y(ymin), X(0), Y(ymax), '#40566b', 2);
  for (gx = -1; gx <= 3; gx++) txt(gx, X(gx), Y(0) + 16, 14, '#526b7a', 'center');
  for (gy = 0; gy <= 10; gy += 2) txt(gy, X(0) - 9, Y(gy), 14, '#526b7a', 'right');
  txt('x', X(xmax) + 12, Y(0), 17, '#263238');
  txt('y', X(0), Y(ymax) - 8, 17, '#263238');

  ctx.save();
  ctx.strokeStyle = '#2878c8';
  ctx.lineWidth = 3;
  ctx.beginPath();
  var started = false;
  for (var i = 0; i <= 260; i++) {
    var xx = xmin + (xmax - xmin) * i / 260;
    var yy = f(xx);
    if (yy >= ymin && yy <= ymax) {
      if (!started) { ctx.moveTo(X(xx), Y(yy)); started = true; }
      else ctx.lineTo(X(xx), Y(yy));
    }
  }
  ctx.stroke();
  ctx.restore();
  txt(isX2 ? 'y=f(x)=x²' : 'y=f(x)=2x+1', 455, 137, 18, '#2878c8');

  var Ax = X(a), Ay = Y(ya), Bx = X(xb), By = Y(yb);
  var tangentVisible = scene === 3 || (scene === 2 && Math.abs(h) < 0.18);
  if (tangentVisible) {
    ctx.save();
    ctx.globalAlpha = scene === 3 ? 1 : Math.max(0, Math.min(1, (0.18 - Math.abs(h)) / 0.16));
    line(X(xmin), Y(ya + tangent * (xmin - a)), X(xmax), Y(ya + tangent * (xmax - a)), '#8d4bbb', 3, [8, 5]);
    ctx.restore();
  }

  line(Ax, Ay, Bx, By, '#ee8b2d', 4);
  line(Ax, Ay, Bx, Ay, '#ee8b2d', 2, [5, 4]);
  line(Bx, Ay, Bx, By, '#ee8b2d', 2, [5, 4]);
  dot(Ax, Ay, 6, '#17324d');
  dot(Bx, By, 6, '#ee8b2d');
  txt('A=(1,' + fmt(ya) + ')', Ax + 10, Ay - 17, 16, '#17324d');
  txt('B=(1+h,' + fmt(yb) + ')', Bx + 8, By - 17, 16, '#b55b12');
  txt('h=' + fmt(h), (Ax + Bx) / 2, Ay + 20, 17, '#b55b12', 'center');
  txt('Δy=' + fmt(dy), Bx + 38, (Ay + By) / 2, 16, '#b55b12', 'center');

  var px = 675, py = 120, pw = 230, ph = 270;
  ctx.fillStyle = '#fdfefe';
  ctx.fillRect(px, py, pw, ph);
  ctx.strokeStyle = '#c5d8e5';
  ctx.strokeRect(px, py, pw, ph);
  txt('数值与公式', px + pw / 2, py + 22, 19, '#17324d', 'center');

  if (scene === 1) {
    txt('m割 = Δy / h', px + 15, py + 58, 18, '#b55b12');
    txt('m割 = ' + fmt(slope, 4), px + 15, py + 88, 19, '#b55b12');
    txt('Δx = h ≠ 0', px + 15, py + 119, 17, '#263238');
    txt('平均变化率', px + 15, py + 151, 17, '#2878c8');
    txt('h=0 不参与差商', px + 15, py + 184, 16, '#6b3fa0');
    txt('割线 AB 已高亮', px + 15, py + 218, 16, '#ee8b2d');
  } else if (scene === 2) {
    txt('f′(a)=lim h→0 差商', px + 15, py + 55, 16, '#6b3fa0');
    txt('当前 h=' + fmt(h), px + 15, py + 84, 17, '#b55b12');
    txt('当前差商=' + fmt(slope, 4), px + 15, py + 112, 17, '#b55b12');
    txt('右侧 h>0：' + fmt(yp, 4), px + 15, py + 148, 16, '#2878c8');
    txt('左侧 h<0：' + fmt(ym, 4), px + 15, py + 177, 16, '#8d4bbb');
    txt('两侧都趋向 2', px + 15, py + 210, 17, '#17324d');
    txt('h=0：极限位置', px + 15, py + 239, 16, '#6b3fa0');
  } else {
    if (display === 0) {
      txt('h=' + fmt(h), px + 15, py + 55, 18, '#b55b12');
      txt('差商=' + fmt(slope, 4), px + 15, py + 87, 18, '#b55b12');
      txt('有限差商不等于极限', px + 15, py + 122, 16, '#6b3fa0');
    } else if (display === 1 && isX2) {
      txt('[f(1+h)-f(1)]/h', px + 15, py + 52, 16, '#263238');
      txt('=[(1+h)²−1]/h', px + 15, py + 82, 16, '#263238');
      txt('=[2h+h²]/h', px + 15, py + 112, 17, '#263238');
      txt('=2+h（h≠0）', px + 15, py + 144, 18, '#b55b12');
    } else if (display === 1) {
      txt('[2(1+h)+1−3]/h', px + 15, py + 60, 16, '#263238');
      txt('=2h/h=2（h≠0）', px + 15, py + 94, 17, '#b55b12');
      txt('两侧差商均为 2', px + 15, py + 130, 17, '#6b3fa0');
    } else {
      txt('切线斜率 f′(1)=2', px + 15, py + 55, 18, '#6b3fa0');
      txt(isX2 ? 'y−1=2(x−1)' : 'y−3=2(x−1)', px + 15, py + 91, 20, '#2878c8');
      txt('h=0 仅为极限位置', px + 15, py + 130, 16, '#b55b12');
      txt('双侧极限相同 ⇒ 可导', px + 15, py + 166, 16, '#6b3fa0');
    }
    txt('序列：1，0.5，0.1，0.01', px + 15, py + 218, 15, '#263238');
    txt('当前步骤 ' + (Math.min(3, Math.floor(local * 4) + 1)) + ' / 4', px + 15, py + 246, 16, '#2878c8');
  }

  var functionText = isX2 ? '预设①：f(x)=x²，a=1' : '预设②：f(x)=2x+1，a=1';
  txt(functionText, 55, 413, 16, '#263238');
  txt('时间 ' + fmt(sec, 1) + ' / 34 秒', 905, 413, 16, '#526b7a', 'right');

  return {
    metrics: {
      scene: scene,
      h: h,
      delta_y: dy,
      secant_slope: isFinite(slope) ? slope : 0,
      right_secant_slope: isFinite(yp) ? yp : 0,
      left_secant_slope: isFinite(ym) ? ym : 0,
      derivative: tangent,
      function: isX2 ? 'x^2' : '2x+1',
      seconds: sec
    }
  };
}