async function sha256Hex(input) {
  const encoder = new TextEncoder();
  const data = encoder.encode(input); // string → bytes

  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer)); // bytes → array

  // Convert each byte to 2-digit hex and join
  const hashHex = hashArray
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return hashHex;
}

export async function fetchPowChallenge(apiBase = "http://localhost:8000") {
  const response = await fetch(`${apiBase}/v1/challenge`);

  if (!response.ok) {
    throw new Error(`Failed to fetch PoW challenge: ${response.status}`);
  }

  const challenge = await response.json();
  console.log("Got PoW challenge:", challenge);
  return challenge;
}

export async function solvePow(challenge) {
  const prefix = "0".repeat(challenge.difficulty);
  let nonce = 0;

  while (true) {
    const payload = `${challenge.challenge_id}:${nonce}`;
    const hash = await sha256Hex(payload);

    if (hash.startsWith(prefix)) {
      console.log("Found PoW solution:", { nonce, hash });
      return nonce.toString(); // your API wants nonce as string
    }

    nonce++;

    // Be kind to the browser: yield every 1000 iterations
    if (nonce % 1000 === 0) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  }
}
