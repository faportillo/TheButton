import { solvePow, fetchPowChallenge } from "/pow.js";

console.log("main.js loaded");
const API_BASE = "http://localhost:8000";

const button = document.getElementById("the-button");
const stateDisplay = document.getElementById("state-display");
const phaseDisplay = document.getElementById("phase-display");

function updateBackgroundColor(phase) {
  // Phase colors: CALM (cool) → WARM → HOT → CHAOS (intense)
  const phaseColors = {
    0: "#e3f2fe", // CALM - Light blue
    1: "#fff3e0", // WARM - Light orange
    2: "#ffebee", // HOT - Light red
    3: "#f3e5f5", // CHAOS - Light purple
  };

  const color = phaseColors[phase] || "#ffffff";
  document.body.style.backgroundColor = color;
}

function renderState(state) {
  // Backend sends: { id, last_applied_offset, counter, phase, entropy, ... }
  stateDisplay.textContent = `Global presses: ${state.counter}`;

  // Phase is an enum: 0=CALM, 1=WARM, 2=HOT, 3=CHAOS
  const phaseNames = ["CALM", "WARM", "HOT", "CHAOS"];
  const phaseValue =
    typeof state.phase === "number" ? state.phase : parseInt(state.phase);
  phaseDisplay.textContent = phaseNames[phaseValue] || state.phase;

  // Update background color based on phase
  updateBackgroundColor(phaseValue);
}

// Fetch initial state immediately when page loads
async function fetchInitialState() {
  try {
    const response = await fetch(`${API_BASE}/v1/states/current`);
    if (!response.ok) {
      if (response.status === 404) {
        stateDisplay.textContent = "No state yet - press the button to start!";
        phaseDisplay.textContent = "WAITING";
        updateBackgroundColor(0); // Default to CALM color
        return;
      }
      throw new Error(`Failed to fetch initial state: ${response.status}`);
    }
    const state = await response.json();
    console.log("Initial state loaded:", state);
    renderState(state);
  } catch (err) {
    console.error("Failed to fetch initial state:", err);
    stateDisplay.textContent = "Error loading state";
    phaseDisplay.textContent = "ERROR";
    updateBackgroundColor(0); // Default to CALM color on error
  }
}

function startStateStream() {
  const source = new EventSource(`${API_BASE}/v1/states/stream`);

  // Listen for custom event type 'state_update' (backend sends: event: state_update)
  source.addEventListener("state_update", (event) => {
    try {
      const data = JSON.parse(event.data);
      console.log("SSE state update:", data);
      renderState(data);
    } catch (err) {
      console.error("Failed to parse SSE data:", err, "raw:", event.data);
    }
  });

  // Also listen for error events from the server
  source.addEventListener("error", (event) => {
    try {
      const errorData = JSON.parse(event.data);
      console.error("SSE error event:", errorData);
    } catch (err) {
      console.error("SSE error (non-JSON):", event.data);
    }
  });

  // Connection-level error handling
  source.onerror = (err) => {
    console.error("SSE connection error:", err);
    console.log("Connection state:", source.readyState);
    // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
    if (source.readyState === EventSource.CLOSED) {
      console.log("SSE connection closed. Will attempt to reconnect...");
    }
  };

  // Log when connection opens
  source.onopen = () => {
    console.log("SSE connection opened successfully");
  };
}

// Initialize: fetch current state first, then start streaming for updates
async function initializeState() {
  await fetchInitialState();
  startStateStream();
}

// =============================================================================
// Event Listeners
// =============================================================================

let pressInFlight = false;

button.addEventListener("click", async () => {
  if (pressInFlight) return;

  pressInFlight = true;
  button.disabled = true;

  // visual press animation
  button.classList.add("pressed");
  setTimeout(() => {
    button.classList.remove("pressed");
  }, 100);

  try {
    const challenge = await fetchPowChallenge(API_BASE);

    const nonce = await solvePow(challenge);

    const body = {
      challenge_id: challenge.challenge_id,
      difficulty: challenge.difficulty,
      expires_at: challenge.expires_at,
      signature: challenge.signature,
      nonce: nonce, // string
    };

    const response = await fetch(`${API_BASE}/v1/events/press`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body), // or omit if no body
    });

    if (response.status === 429) {
      stateDisplay.textContent = "Rate limited – slow down!";
      return;
    }

    if (!response.ok) {
      throw new Error(`Server error: ${response.status}`);
    }

    // No need to manually refresh state — SSE will push it.
  } catch (err) {
    console.error("Failed to press button:", err);
    stateDisplay.textContent = "Error sending press to server.";
  } finally {
    pressInFlight = false;
    button.disabled = false;
  }
});

// =============================================================================
// Initialization
// =============================================================================

// Start everything when page loads
initializeState();
