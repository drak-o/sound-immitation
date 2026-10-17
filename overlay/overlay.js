const canvas = document.getElementById("wave");
const countdownNode = document.getElementById("countdown");
const resultNode = document.getElementById("result");
const attemptNode = document.getElementById("attempt");
const context = canvas.getContext("2d");

const state = {
  mode: "idle",
  reference: null,
  live: null,
};

function resize() {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(canvas.clientWidth * ratio));
  canvas.height = Math.max(1, Math.floor(canvas.clientHeight * ratio));
  draw();
}

function drawWave(values, color) {
  if (!values || values.length < 2) {
    return;
  }
  const width = canvas.width;
  const height = canvas.height;
  const mid = height / 2;
  const last = values.length - 1;
  context.beginPath();
  let moved = false;
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (value == null) {
      break;
    }
    const x = (index / last) * width;
    const y = mid - value * mid * 0.82;
    if (!moved) {
      context.moveTo(x, y);
      moved = true;
    } else {
      context.lineTo(x, y);
    }
  }
  if (!moved) {
    return;
  }
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const value = values[index];
    if (value == null) {
      continue;
    }
    const x = (index / last) * width;
    const y = mid + value * mid * 0.82;
    context.lineTo(x, y);
  }
  context.closePath();
  context.fillStyle = color;
  context.fill();
}

function draw() {
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (state.mode === "idle") {
    return;
  }
  const referenceColor = state.mode === "recording" || state.mode === "result"
    ? "rgba(170, 170, 170, 0.5)"
    : "rgba(255, 255, 255, 0.95)";
  drawWave(state.reference, referenceColor);
  if (state.mode === "recording" || state.mode === "result") {
    drawWave(state.live, "rgba(92, 230, 150, 0.95)");
  }
}

function apply(message) {
  if (message.type === "idle") {
    state.mode = "idle";
    state.reference = null;
    state.live = null;
    countdownNode.textContent = "";
    resultNode.textContent = "";
    attemptNode.textContent = "";
  } else if (message.type === "reference") {
    state.mode = "reference";
    state.reference = message.peaks;
    state.live = null;
    countdownNode.textContent = "";
    resultNode.textContent = "";
    attemptNode.textContent = `Attempt ${message.attempt}`;
  } else if (message.type === "countdown") {
    state.mode = "countdown";
    countdownNode.textContent = String(message.n);
    resultNode.textContent = "";
  } else if (message.type === "recording") {
    state.mode = "recording";
    state.live = message.livePeaks;
    countdownNode.textContent = "";
  } else if (message.type === "result") {
    state.mode = "result";
    const verdict = message.passed ? "Passed" : "Failed";
    resultNode.textContent = `${verdict} ${message.percent}%`;
    resultNode.dataset.passed = message.passed ? "true" : "false";
  }
  draw();
}

function connect() {
  const socket = new WebSocket(`ws://${location.host}/ws`);
  socket.addEventListener("message", (event) => {
    try {
      apply(JSON.parse(event.data));
    } catch (_error) {
      /* Ignore a malformed frame and keep the socket. */
    }
  });
  socket.addEventListener("close", () => {
    window.setTimeout(connect, 500);
  });
}

window.addEventListener("resize", resize);
new ResizeObserver(resize).observe(canvas);
resize();
connect();
