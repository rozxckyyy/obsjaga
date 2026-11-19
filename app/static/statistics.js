const periodForm = document.getElementById("stats-period-form");
const pageUrl = new URL(window.location.href);
if (pageUrl.searchParams.has("date_from") || pageUrl.searchParams.has("date_to")) {
  pageUrl.searchParams.delete("date_from");
  pageUrl.searchParams.delete("date_to");
  window.history.replaceState(window.history.state, "", pageUrl);
}

periodForm.addEventListener("change", () => {
  if (periodForm.checkValidity()) periodForm.requestSubmit();
});

const timeline = Array.from(document.querySelectorAll("#stats-daily-counts tbody tr"), (row) => ({
  label: row.cells[0].dataset.tick,
  period: row.cells[0].textContent.trim(),
  count: Number(row.cells[1].textContent),
}));
const statuses = Array.from(document.querySelectorAll("#stats-status-counts li"), (item) => ({
  count: Number(item.dataset.count),
  color: getComputedStyle(item).getPropertyValue("--chart-color").trim(),
}));

function responsiveCanvas(canvas, draw) {
  const context = canvas.getContext("2d");
  if (!context) return;
  canvas.hidden = false;

  const resize = () => {
    const { width, height } = canvas.getBoundingClientRect();
    if (width < 1 || height < 1) return;
    const scale = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    context.setTransform(scale, 0, 0, scale, 0, 0);
    draw(context, width, height);
  };
  new ResizeObserver(resize).observe(canvas);
  resize();
}

function drawTimeline(context, width, height) {
  const peak = Math.max(1, ...timeline.map((point) => point.count));
  const approximateStep = Math.max(1, peak / 4);
  const magnitude = 10 ** Math.floor(Math.log10(approximateStep));
  const step = [1, 2, 5, 10].map((n) => n * magnitude).find((n) => n >= approximateStep);
  const ceiling = Math.ceil(peak / step) * step;
  const fontFamily = getComputedStyle(document.body).fontFamily;
  context.font = `12px ${fontFamily}`;

  const left = context.measureText(String(ceiling)).width + 12;
  const right = width - 24;
  const top = 12;
  const bottom = height - 29;
  const plotWidth = right - left;
  const x = (index) => timeline.length === 1
    ? left + plotWidth / 2
    : left + (index * plotWidth) / (timeline.length - 1);
  const y = (count) => bottom - (count / ceiling) * (bottom - top);
  const points = timeline.map((point, index) => ({ ...point, x: x(index), y: y(point.count) }));

  context.strokeStyle = "#dfe6ef";
  context.fillStyle = "#526178";
  context.textAlign = "right";
  context.textBaseline = "middle";
  context.beginPath();
  for (let count = 0; count <= ceiling; count += step) {
    const position = y(count);
    context.moveTo(left, position);
    context.lineTo(right, position);
    context.fillText(String(count), left - 8, position);
  }
  context.stroke();

  context.textAlign = "center";
  const labelCount = Math.min(timeline.length, Math.max(2, Math.floor(plotWidth / 72)));
  for (let labelIndex = 0; labelIndex < labelCount; labelIndex++) {
    const index = Math.round(labelIndex * (timeline.length - 1) / Math.max(1, labelCount - 1));
    const label = timeline[index].label;
    const halfWidth = context.measureText(label).width / 2;
    const labelX = Math.max(halfWidth, Math.min(width - halfWidth, x(index)));
    context.fillText(label, labelX, bottom + 17);
  }

  context.beginPath();
  context.moveTo(points[0].x, points[0].y);
  points.slice(1).forEach((point) => context.lineTo(point.x, point.y));
  context.strokeStyle = "#006c63";
  context.lineWidth = 2;
  context.lineJoin = "round";
  context.stroke();
  context.lineTo(points.at(-1).x, bottom);
  context.lineTo(points[0].x, bottom);
  context.closePath();
  context.fillStyle = "#006c6320";
  context.fill();

  context.fillStyle = "#006c63";
  points.forEach((point) => {
    context.beginPath();
    context.arc(point.x, point.y, 3, 0, Math.PI * 2);
    context.fill();
  });
  return points;
}

function enableTimeline(canvas) {
  const tooltip = document.getElementById("stats-tooltip");
  const period = tooltip.querySelector("span");
  const value = tooltip.querySelector("strong");
  let points = [];

  const hideTooltip = () => { tooltip.hidden = true; };
  const showPoint = (event) => {
    const bounds = canvas.getBoundingClientRect();
    const pointerX = event.clientX - bounds.left;
    const pointerY = event.clientY - bounds.top;
    let nearest;
    let distanceLimit = 14 ** 2;
    for (const point of points) {
      const distance = (pointerX - point.x) ** 2 + (pointerY - point.y) ** 2;
      if (distance < distanceLimit) {
        nearest = point;
        distanceLimit = distance;
      }
    }
    if (!nearest) {
      hideTooltip();
      return;
    }

    period.textContent = nearest.period;
    value.textContent = `Заявок — ${nearest.count}`;
    tooltip.hidden = false;
    const left = Math.min(bounds.width - tooltip.offsetWidth, Math.max(0, nearest.x - tooltip.offsetWidth / 2));
    const above = nearest.y - tooltip.offsetHeight - 10;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${above >= 0 ? above : nearest.y + 10}px`;
  };

  responsiveCanvas(canvas, (context, width, height) => {
    points = drawTimeline(context, width, height);
    hideTooltip();
  });
  canvas.addEventListener("pointermove", showPoint);
  canvas.addEventListener("pointerdown", showPoint);
  canvas.addEventListener("pointerleave", hideTooltip);
  canvas.addEventListener("pointercancel", hideTooltip);
}

function drawRing(context, width, height) {
  const radius = Math.min(width, height) * 0.4;
  const total = statuses.reduce((sum, item) => sum + item.count, 0);
  const turn = Math.PI * 2;
  let angle = -Math.PI / 2;

  context.lineWidth = radius * 0.32;
  context.beginPath();
  context.arc(width / 2, height / 2, radius, 0, turn);
  context.strokeStyle = "#e9eff5";
  context.stroke();

  for (const item of statuses) {
    if (!item.count) continue;
    const nextAngle = angle + (item.count / total) * turn;
    context.beginPath();
    context.arc(width / 2, height / 2, radius, angle, nextAngle);
    context.strokeStyle = item.color;
    context.stroke();
    angle = nextAngle;
  }
}

const lineCanvas = document.getElementById("stats-line");
if (lineCanvas) {
  enableTimeline(lineCanvas);
  responsiveCanvas(document.getElementById("stats-ring"), drawRing);
}
