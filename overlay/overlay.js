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
	if (!values || values.length === 0) {
		return;
	}
	const width = canvas.width;
	const height = canvas.height;
	const mid = height / 2;
	// Integer edges so each column, including the last, meets its neighbor.
	const barWidth = width / values.length;
	context.fillStyle = color;
	for (let index = 0; index < values.length; index += 1) {
		const value = values[index];
		if (value == null) {
			continue;
		}

		const barHeight = value * height * 0.82; // bar leaves 0.09 of the canvas clear above and below.
		const left = Math.floor(index * barWidth);
		const right = Math.floor((index + 1) * barWidth);
		context.fillRect(left, mid - barHeight / 2, right - left, barHeight);
	}
}

function draw() {
	context.clearRect(0, 0, canvas.width, canvas.height);
	if (state.mode === "idle") {
		return;
	}
	if (state.mode === "recording" || state.mode === "result") {
		drawWave(state.reference, "rgba(170, 170, 170, 0.5)");
		drawWave(state.live, "rgba(92, 230, 150, 0.95)");
	} else {
		drawWave(state.reference, "rgba(255, 255, 255, 0.95)");
	}
}

// apply the message from overlay_server.py to the state
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

// connect overlay_server.py with overlay.js through WebSocket
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
