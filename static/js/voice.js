/**
 * ParkVoice AI - Web Speech API Voice Engine & Intent Parser
 * ==========================================================
 * Features:
 * - SpeechRecognition (webkitSpeechRecognition) continuous/single input
 * - SpeechSynthesis TTS with mute toggle
 * - Rule-based intent classification for 9 competition commands
 * - Multi-turn conversational flow (Find -> Recommend -> Book -> Confirm)
 * - Robust fallback error handling (Mic blocked, Network error, etc.)
 */

// Voice Engine State
const VoiceState = {
  isListening: false,
  isSpeaking: false,
  ttsEnabled: true,
  lastRecommendedSlot: null,
  pendingConfirmation: false,
  recognition: null,
  synth: window.speechSynthesis || null
};

// Initialize SpeechRecognition
function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    console.warn("[VoiceEngine] Web Speech API not supported in this browser.");
    updateVoiceStatus("Speech API not supported", "Please use Chrome, Edge, or Safari for voice commands.");
    return null;
  }

  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "en-US";

  recognition.onstart = () => {
    VoiceState.isListening = true;
    updateVoiceUIState(true);
    updateVoiceStatus("Listening...", "Speak your command clearly");
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript.trim();
    console.log(`[VoiceEngine] Heard: "${transcript}"`);
    addChatBubble(transcript, "user");
    processVoiceIntent(transcript);
  };

  recognition.onerror = (event) => {
    console.error("[VoiceEngine] Recognition error:", event.error);
    VoiceState.isListening = false;
    updateVoiceUIState(false);

    if (event.error === "not-allowed") {
      updateVoiceStatus("Microphone access blocked", "Please enable mic permissions in your browser bar.");
      showToast("Microphone permission denied. Please allow microphone access.", "danger");
    } else if (event.error === "no-speech") {
      updateVoiceStatus("No speech detected", "Click the mic icon to try again.");
    } else {
      updateVoiceStatus("Voice error", `Error: ${event.error}. Click mic to retry.`);
    }
  };

  recognition.onend = () => {
    VoiceState.isListening = false;
    updateVoiceUIState(false);
  };

  return recognition;
}

// Speak response via SpeechSynthesis
function speakResponse(text, callback = null) {
  if (!VoiceState.synth) return;

  // If muted, just run callback
  if (!VoiceState.ttsEnabled) {
    if (callback) callback();
    return;
  }

  VoiceState.synth.cancel(); // Stop any ongoing speech

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  utterance.rate = 1.0;
  utterance.pitch = 1.0;

  // Try selecting a natural English voice if available
  const voices = VoiceState.synth.getVoices();
  const naturalVoice = voices.find(v => v.lang.startsWith("en") && (v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Samantha")));
  if (naturalVoice) {
    utterance.voice = naturalVoice;
  }

  utterance.onstart = () => {
    VoiceState.isSpeaking = true;
    const badge = document.getElementById("voiceBadge");
    if (badge) badge.innerText = "SPEAKING";
  };

  utterance.onend = () => {
    VoiceState.isSpeaking = false;
    const badge = document.getElementById("voiceBadge");
    if (badge) badge.innerText = "IDLE";
    if (callback) callback();
  };

  utterance.onerror = () => {
    VoiceState.isSpeaking = false;
    if (callback) callback();
  };

  VoiceState.synth.speak(utterance);
}

// Word to number mapping for spoken slot commands (e.g. "slot nine" -> "P09")
const WORD_TO_NUM = {
  "one": "01", "two": "02", "three": "03", "four": "04", "five": "05", "six": "06",
  "seven": "07", "eight": "08", "nine": "09", "ten": "10", "eleven": "11", "twelve": "12",
  "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06",
  "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12"
};

// Normalize spoken slot token into canonical "P01"-"P12" format
function parseSlotNumberFromText(token) {
  if (!token) return null;
  const clean = token.toLowerCase().trim().replace(/^p\s*/, "");
  if (WORD_TO_NUM[clean]) {
    return "P" + WORD_TO_NUM[clean];
  }
  const num = parseInt(clean, 10);
  if (!isNaN(num) && num >= 1 && num <= 12) {
    return "P" + (num < 10 ? "0" + num : num);
  }
  return null;
}

// Rule-Based Intent Parser
function classifyIntent(transcript) {
  const text = transcript.toLowerCase().replace(/[.,\/#!$%\^&\*;:{}=\-_`~()]/g, "");

  // 0. TRACE / TRACK ANY PARKING BAY ON DEMAND (Feature 2)
  // e.g. "trace route to P05", "trace slot 9", "show path to slot four", "navigate to P03"
  const tracePattern = /(?:trace|show\s+route|show\s+path|track|path\s+to|route\s+to|navigate\s+to|how\s+do\s+i\s+get\s+to)\s+(?:route\s+to\s+|path\s+to\s+|to\s+)?(?:slot\s+)?(p\s*\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,2})/i;
  const traceMatch = text.match(tracePattern);
  if (traceMatch) {
    const slotNum = parseSlotNumberFromText(traceMatch[1]);
    if (slotNum) {
      return { intent: "TRACE_SLOT", slot_number: slotNum };
    }
  }

  // Clear preview route
  if (text.includes("clear route") || text.includes("clear path") || text.includes("clear preview") || text.includes("hide route")) {
    return { intent: "CLEAR_ROUTE" };
  }

  // 1. BOOK SPECIFIC SLOT (e.g. "book p07", "reserve p3", "book slot 12", "book slot nine")
  const specificSlotMatch = text.match(/(?:book|reserve|park\s+at|take)\s+(?:slot\s+)?(p\s*\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,2})/i);
  if (specificSlotMatch) {
    const slotNum = parseSlotNumberFromText(specificSlotMatch[1]);
    if (slotNum) {
      return { intent: "BOOK_SLOT", slot_number: slotNum };
    }
  }

  // 2. BOOK RECOMMENDED / CONFIRM
  if (
    text.includes("book recommended") ||
    text.includes("book the recommended") ||
    text.includes("confirm booking") ||
    text.includes("yes book it") ||
    text.includes("book it") ||
    (VoiceState.pendingConfirmation && (text.includes("yes") || text.includes("sure") || text.includes("confirm") || text.includes("okay") || text.includes("ok")))
  ) {
    return { intent: "BOOK_RECOMMENDED" };
  }

  // 3. VEHICLE-SPECIFIC SEARCH INTENTS
  if (text.includes("ev") || text.includes("electric") || text.includes("charge") || text.includes("charging")) {
    return { intent: "FIND_PARKING_EV" };
  }

  if (text.includes("suv") || text.includes("large vehicle") || text.includes("truck")) {
    return { intent: "FIND_PARKING_SUV" };
  }

  if (text.includes("bike") || text.includes("two wheeler") || text.includes("motorcycle") || text.includes("compact")) {
    return { intent: "FIND_PARKING_BIKE" };
  }

  if (text.includes("car") || text.includes("sedan") || text.includes("standard")) {
    return { intent: "FIND_PARKING_CAR" };
  }

  if (text.includes("nearest") || text.includes("closest")) {
    return { intent: "FIND_NEAREST" };
  }

  // 4. FIND PARKING (GENERAL / CURRENT ACTIVE VEHICLE)
  if (
    text.includes("find parking") ||
    text.includes("find a slot") ||
    text.includes("find a spot") ||
    text.includes("search parking") ||
    text.includes("need a slot") ||
    text.includes("where can i park") ||
    text.includes("park my") ||
    text.includes("park vehicle") ||
    text.includes("recommend parking")
  ) {
    return { intent: "FIND_PARKING" };
  }

  // 5. SHOW AVAILABLE SLOTS
  if (
    text.includes("show available") ||
    text.includes("how many spots") ||
    text.includes("how many free") ||
    text.includes("check free") ||
    text.includes("available slots")
  ) {
    return { intent: "SHOW_AVAILABLE" };
  }

  // 6. SHOW MY BOOKING
  if (
    text.includes("show my booking") ||
    text.includes("where is my car") ||
    text.includes("my booking") ||
    text.includes("active booking") ||
    text.includes("current reservation") ||
    text.includes("my reservations")
  ) {
    return { intent: "SHOW_BOOKING" };
  }

  // 7. CANCEL BOOKING
  if (
    text.includes("cancel my booking") ||
    text.includes("cancel booking") ||
    text.includes("cancel reservation") ||
    text.includes("cancel spot")
  ) {
    return { intent: "CANCEL_BOOKING" };
  }

  // 8. RELEASE PARKING / LEAVE
  if (
    text.includes("release parking") ||
    text.includes("leave parking") ||
    text.includes("i am leaving") ||
    text.includes("check out") ||
    text.includes("complete parking")
  ) {
    return { intent: "RELEASE_PARKING" };
  }

  // 9. LOGOUT
  if (text.includes("log out") || text.includes("sign out")) {
    return { intent: "LOGOUT" };
  }

  return { intent: "UNKNOWN" };
}

// Process classified voice intent
async function processVoiceIntent(transcript) {
  const result = classifyIntent(transcript);
  console.log("[VoiceEngine] Classified intent:", result);

  switch (result.intent) {
    case "TRACE_SLOT":
      await handleTraceSlotIntent(result.slot_number);
      break;

    case "CLEAR_ROUTE":
      handleClearRouteIntent();
      break;

    case "FIND_PARKING":
      await handleFindParkingIntent(null);
      break;

    case "FIND_PARKING_EV":
      await handleFindParkingIntent("EV");
      break;

    case "FIND_PARKING_CAR":
      await handleFindParkingIntent("Car");
      break;

    case "FIND_PARKING_SUV":
      await handleFindParkingIntent("SUV");
      break;

    case "FIND_PARKING_BIKE":
      await handleFindParkingIntent("Bike");
      break;

    case "FIND_NEAREST":
      await handleFindParkingIntent(null);
      break;

    case "BOOK_RECOMMENDED":
      await handleBookRecommendedIntent();
      break;

    case "BOOK_SLOT":
      await handleBookSpecificSlotIntent(result.slot_number);
      break;

    case "SHOW_AVAILABLE":
      await handleShowAvailableIntent();
      break;

    case "SHOW_BOOKING":
      await handleShowBookingIntent();
      break;

    case "CANCEL_BOOKING":
      await handleCancelBookingIntent();
      break;

    case "RELEASE_PARKING":
      await handleReleaseParkingIntent();
      break;

    case "LOGOUT":
      addChatBubble("Signing you out of ParkVoice AI.", "ai");
      speakResponse("Signing you out.", () => {
        window.location.href = "/logout";
      });
      break;

    default:
      const msg = "Sorry, I didn't recognize that command. Try saying 'Find car parking', 'Trace route to P05', 'Book P07', or 'Show my booking'.";
      addChatBubble(msg, "ai");
      speakResponse(msg);
      updateVoiceStatus("Command not recognized", "Try: 'Trace route to P05' or 'Find car parking'");
      break;
  }
}

// Handler: Trace / Track any parking bay on demand (Feature 2)
async function handleTraceSlotIntent(slotNumber) {
  updateVoiceStatus(`Tracing A* route to ${slotNumber}...`, "Computing Manhattan distance from Entrance");

  if (window.ParkVoiceParking && typeof window.ParkVoiceParking.traceRouteToSlot === "function") {
    const result = await window.ParkVoiceParking.traceRouteToSlot(slotNumber, true);
    if (result && result.success) {
      const speechMsg = `Tracing route to ${slotNumber}. It is ${result.distance} steps from the entrance gate.`;
      const chatMsg = `🗺️ <strong>Tracing Route to ${slotNumber}</strong><br>A* algorithm calculated the optimal path (${result.distance} steps from Entrance Gate). Preview line shown in cyan on the map.`;
      addChatBubble(chatMsg, "ai");
      speakResponse(speechMsg);
      updateVoiceStatus(`Traced ${slotNumber}`, "Cyan dashed line preview on map");
    } else {
      const msg = `Unable to trace route to ${slotNumber}. Please check if the slot is valid.`;
      addChatBubble(msg, "ai");
      speakResponse(msg);
    }
  } else if (typeof traceRouteToSlot === "function") {
    const result = await traceRouteToSlot(slotNumber, true);
    if (result && result.success) {
      const speechMsg = `Tracing route to ${slotNumber}. Distance is ${result.distance} steps.`;
      addChatBubble(`🗺️ <strong>Tracing Route to ${slotNumber}</strong> (${result.distance} steps)`, "ai");
      speakResponse(speechMsg);
    }
  }
}

// Handler: Clear Route Preview
function handleClearRouteIntent() {
  if (window.ParkVoiceParking && typeof window.ParkVoiceParking.clearPreviewRoute === "function") {
    window.ParkVoiceParking.clearPreviewRoute();
  } else if (typeof clearPreviewRoute === "function") {
    clearPreviewRoute();
  }
  const msg = "Cleared preview navigation route.";
  addChatBubble(msg, "ai");
  speakResponse(msg);
  updateVoiceStatus("Route cleared", "Ready for voice command");
}

// Handler: Find Parking with Vehicle Awareness
async function handleFindParkingIntent(vehicleTypeParam = null) {
  const typeLabel = vehicleTypeParam ? `${vehicleTypeParam} ` : "";
  updateVoiceStatus(`Finding optimal ${typeLabel}slot with A*...`, "Analyzing live grid & distance");
  
  try {
    const payload = {};
    if (vehicleTypeParam) {
      payload.vehicle_type = vehicleTypeParam;
    } else if (typeof currentSelectedVehicleId !== "undefined" && currentSelectedVehicleId) {
      payload.vehicle_id = parseInt(currentSelectedVehicleId);
    }

    const res = await fetch("/api/parking/find-parking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!data.success || !data.recommendation.recommended_slot) {
      const errMsg = data.recommendation ? data.recommendation.reason : `No ${typeLabel}parking slots are currently available.`;
      addChatBubble(errMsg, "ai");
      speakResponse(errMsg);
      updateVoiceStatus("No slots available", errMsg);
      return;
    }

    const rec = data.recommendation;
    const slot = rec.recommended_slot;
    VoiceState.lastRecommendedSlot = slot;
    VoiceState.pendingConfirmation = true;

    // Trigger visual A* route drawing in parking.js
    if (typeof highlightRecommendedSlot === "function") {
      highlightRecommendedSlot(slot, rec.path, rec.distance);
    }

    const speechMsg = `I found the best ${rec.slot_type} slot for you: ${slot.slot_number}. It is ${rec.distance} units away, approximately ${rec.est_time_str} drive. Would you like me to book it?`;
    const chatMsg = `🎯 <strong>Recommended: ${slot.slot_number}</strong> (${rec.slot_type}${slot.has_ev_charger ? ' &bull; EV Fast Charge' : ''})<br>${rec.reason}<br><em>Say "Book recommended" or "Yes" to confirm!</em>`;

    addChatBubble(chatMsg, "ai");
    speakResponse(speechMsg);
    updateVoiceStatus(`Recommended ${slot.slot_number}`, "Say 'Book recommended' or click confirm to reserve");

  } catch (err) {
    console.error("Find parking error:", err);
    const msg = "Unable to connect to the parking server. Please try again.";
    addChatBubble(msg, "ai");
    speakResponse(msg);
  }
}

// Handler: Book Recommended
async function handleBookRecommendedIntent() {
  if (!VoiceState.lastRecommendedSlot) {
    const msg = "No slot has been recommended yet. Say 'Find parking' first.";
    addChatBubble(msg, "ai");
    speakResponse(msg);
    return;
  }

  await executeBooking(VoiceState.lastRecommendedSlot.slot_number, VoiceState.lastRecommendedSlot.id);
}

// Handler: Book Specific Slot (e.g. "Book P07")
async function handleBookSpecificSlotIntent(slotNumber) {
  await executeBooking(slotNumber, null);
}

// Core Booking Executor with Multi-Vehicle Support and Double-Booking Validation
async function executeBooking(slotNumber, slotId, vehicleId = null) {
  updateVoiceStatus(`Booking slot ${slotNumber}...`, "Verifying availability with database");

  try {
    const payload = {};
    if (slotId) payload.slot_id = slotId;
    else payload.slot_number = slotNumber;

    const vId = vehicleId || (typeof currentSelectedVehicleId !== "undefined" ? currentSelectedVehicleId : null);
    if (vId) {
      payload.vehicle_id = parseInt(vId);
    }

    const res = await fetch("/api/bookings/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok && data.success) {
      VoiceState.pendingConfirmation = false;
      const b = data.booking;
      const speechMsg = `Slot ${b.slot_number} successfully booked! Your booking code is ${b.booking_code}. The navigation route is active.`;
      const chatMsg = `✅ <strong>Booking Confirmed!</strong><br>Slot: <strong>${b.slot_number}</strong> &bull; Code: <code>${b.booking_code}</code><br>Vehicle: ${b.plate_number || ''} (${b.model || ''}) &bull; Rate: $${b.price_per_hour.toFixed(2)}/hr`;

      addChatBubble(chatMsg, "ai");
      speakResponse(speechMsg);
      showToast(`Reserved ${b.slot_number} (${b.booking_code})`, "success");

      // Close slot details modal if open
      if (typeof closeSlotModal === "function") {
        closeSlotModal();
      }

      // Show success modal if present
      const successModal = document.getElementById("bookingSuccessModal");
      if (successModal) {
        const slotTag = document.getElementById("successSlotTag");
        const codeTag = document.getElementById("successBookingCode");
        const vehInfo = document.getElementById("successVehicleInfo");
        const rateInfo = document.getElementById("successRateInfo");
        const distInfo = document.getElementById("successDistInfo");

        if (slotTag) slotTag.innerText = b.slot_number;
        if (codeTag) codeTag.innerText = b.booking_code;
        if (vehInfo) vehInfo.innerText = `${b.plate_number || ''} (${b.vehicle_type || ''} - ${b.model || ''})`;
        if (rateInfo) rateInfo.innerText = `$${b.price_per_hour.toFixed(2)}/hr`;
        if (distInfo && b.distance) distInfo.innerText = `${b.distance} steps from entrance`;
        successModal.style.display = "flex";
      }

      // Reload live parking map and active bookings
      if (typeof reloadParkingMap === "function") {
        reloadParkingMap();
      }
      if (typeof checkActiveBooking === "function") {
        checkActiveBooking();
      }

    } else if (res.status === 409) {
      // Double booking conflict!
      VoiceState.pendingConfirmation = false;
      const conflictMsg = `Slot ${slotNumber} was just taken by another driver. Please choose another slot.`;
      addChatBubble(conflictMsg, "ai");
      speakResponse(conflictMsg);
      showToast(data.error || "Slot conflict", "danger");
      if (typeof reloadParkingMap === "function") reloadParkingMap();

    } else {
      const errMsg = data.error || "Booking failed.";
      addChatBubble(errMsg, "ai");
      speakResponse(errMsg);
      showToast(errMsg, "danger");
    }

  } catch (err) {
    console.error("Booking error:", err);
    const msg = "Network error while completing booking.";
    addChatBubble(msg, "ai");
    speakResponse(msg);
  }
}

// Handler: Show Available Slots
async function handleShowAvailableIntent() {
  try {
    const res = await fetch("/api/parking/slots");
    const data = await res.json();
    if (data.success) {
      const available = data.slots.filter(s => s.status === "AVAILABLE");
      const evCount = available.filter(s => s.has_ev_charger).length;
      const msg = `There are currently ${available.length} free parking slots available, including ${evCount} with EV chargers.`;
      addChatBubble(`📊 ${msg}`, "ai");
      speakResponse(msg);
    }
  } catch (err) {
    console.error(err);
  }
}

// Handler: Show My Booking (Multi-Vehicle Aware)
async function handleShowBookingIntent() {
  try {
    const res = await fetch("/api/bookings/active");
    const data = await res.json();

    if (data.success && data.active_bookings && data.active_bookings.length > 0) {
      if (data.active_bookings.length === 1) {
        const b = data.active_bookings[0];
        const msg = `You have an active booking for slot ${b.slot_number} with code ${b.booking_code}, assigned to your ${b.model || b.plate_number}.`;
        addChatBubble(`📍 <strong>Active Booking:</strong> Slot ${b.slot_number} (<code>${b.booking_code}</code>) for ${b.plate_number} (${b.model})`, "ai");
        speakResponse(msg);
      } else {
        const count = data.active_bookings.length;
        const details = data.active_bookings.map(b => `Slot ${b.slot_number} for ${b.plate_number}`).join(", ");
        const speechMsg = `You have ${count} active bookings: ${details}.`;
        const chatMsg = `📍 <strong>${count} Active Bookings:</strong><br>` + data.active_bookings.map(b => `&bull; Slot <strong>${b.slot_number}</strong> (<code>${b.booking_code}</code>) &bull; ${b.plate_number} (${b.model})`).join("<br>");
        addChatBubble(chatMsg, "ai");
        speakResponse(speechMsg);
      }
    } else if (data.success && data.active_booking) {
      const b = data.active_booking;
      const msg = `You have an active booking for slot ${b.slot_number} with code ${b.booking_code}, assigned to your ${b.model || b.plate_number}.`;
      addChatBubble(`📍 <strong>Active Booking:</strong> Slot ${b.slot_number} (${b.booking_code}) for ${b.model}`, "ai");
      speakResponse(msg);
    } else {
      const msg = "You do not have any active bookings right now. Say 'Find parking' or click any bay to reserve.";
      addChatBubble(msg, "ai");
      speakResponse(msg);
    }
  } catch (err) {
    console.error(err);
  }
}

// Handler: Cancel Booking
async function handleCancelBookingIntent() {
  try {
    const payload = {};
    if (typeof currentSelectedVehicleId !== "undefined" && currentSelectedVehicleId) {
      payload.vehicle_id = parseInt(currentSelectedVehicleId);
    }

    const res = await fetch("/api/bookings/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (res.ok && data.success) {
      const msg = "Your booking has been cancelled and the parking slot is now free.";
      addChatBubble(`❌ ${msg}`, "ai");
      speakResponse(msg);
      showToast("Booking cancelled successfully.", "info");

      if (typeof reloadParkingMap === "function") reloadParkingMap();
      if (typeof checkActiveBooking === "function") checkActiveBooking();
    } else {
      const errMsg = data.error || "No active booking found to cancel.";
      addChatBubble(errMsg, "ai");
      speakResponse(errMsg);
    }
  } catch (err) {
    console.error(err);
  }
}

// Handler: Release Parking / Leave
async function handleReleaseParkingIntent() {
  try {
    const payload = {};
    if (typeof currentSelectedVehicleId !== "undefined" && currentSelectedVehicleId) {
      payload.vehicle_id = parseInt(currentSelectedVehicleId);
    }

    const res = await fetch("/api/bookings/release", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if (res.ok && data.success) {
      const msg = `Thank you! Your parking session is complete. Duration: ${data.duration_minutes} minutes, total fee: $${data.fee_paid.toFixed(2)}.`;
      addChatBubble(`🚗 ${msg}`, "ai");
      speakResponse(msg);
      showToast("Parking session completed.", "success");

      if (typeof reloadParkingMap === "function") reloadParkingMap();
      if (typeof checkActiveBooking === "function") checkActiveBooking();
    } else {
      const errMsg = data.error || "No active session found to release.";
      addChatBubble(errMsg, "ai");
      speakResponse(errMsg);
    }
  } catch (err) {
    console.error(err);
  }
}

// Helper: Programmatically simulate a voice command
function simulateVoiceCommand(commandText) {
  addChatBubble(commandText, "user");
  processVoiceIntent(commandText);
}

// UI Helpers
function updateVoiceStatus(statusText, subtext) {
  const lbl = document.getElementById("voiceStatusLabel");
  const sub = document.getElementById("voiceTranscriptPreview");
  if (lbl) lbl.innerText = statusText;
  if (sub && subtext) sub.innerText = subtext;
}

function updateVoiceUIState(isListening) {
  const container = document.getElementById("voiceOrbContainer");
  const badge = document.getElementById("voiceBadge");
  if (container) {
    if (isListening) container.classList.add("is-listening");
    else container.classList.remove("is-listening");
  }
  if (badge) {
    badge.innerText = isListening ? "LISTENING" : "IDLE";
    badge.style.background = isListening ? "rgba(239, 68, 68, 0.2)" : "rgba(99, 102, 241, 0.2)";
    badge.style.color = isListening ? "#f87171" : "#a5b4fc";
  }
}

function addChatBubble(text, sender = "ai") {
  const box = document.getElementById("transcriptBox");
  if (!box) return;

  const bubble = document.createElement("div");
  bubble.className = `chat-bubble bubble-${sender}`;
  bubble.innerHTML = text;
  box.appendChild(bubble);
  box.scrollTop = box.scrollHeight;
}

// Setup Voice Event Listeners on DOM Load
document.addEventListener("DOMContentLoaded", () => {
  VoiceState.recognition = initSpeechRecognition();

  const micBtn = document.getElementById("micButton");
  if (micBtn) {
    micBtn.addEventListener("click", () => {
      if (!VoiceState.recognition) {
        VoiceState.recognition = initSpeechRecognition();
      }

      if (!VoiceState.recognition) {
        alert("Web Speech API is not supported in this browser. Please use Chrome, Edge, or Safari.");
        return;
      }

      if (VoiceState.isListening) {
        VoiceState.recognition.stop();
      } else {
        try {
          VoiceState.recognition.start();
        } catch (err) {
          console.warn("Speech recognition already running:", err);
        }
      }
    });
  }

  // TTS Mute/Unmute Toggle
  const ttsBtn = document.getElementById("voiceTtsToggle");
  const ttsIcon = document.getElementById("ttsSoundIcon");
  if (ttsBtn) {
    // Restore preference
    const saved = localStorage.getItem("parkvoice_tts_enabled");
    if (saved !== null) {
      VoiceState.ttsEnabled = saved === "true";
    }

    const updateIcon = () => {
      if (VoiceState.ttsEnabled) {
        ttsBtn.classList.remove("btn-danger");
        ttsBtn.classList.add("btn-secondary");
        ttsBtn.title = "Voice audio response: ENABLED (Click to mute)";
        if (ttsIcon) ttsIcon.innerHTML = `<path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>`;
      } else {
        ttsBtn.classList.remove("btn-secondary");
        ttsBtn.classList.add("btn-danger");
        ttsBtn.title = "Voice audio response: MUTED (Click to enable)";
        if (ttsIcon) ttsIcon.innerHTML = `<path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>`;
      }
    };

    updateIcon();

    ttsBtn.addEventListener("click", () => {
      VoiceState.ttsEnabled = !VoiceState.ttsEnabled;
      localStorage.setItem("parkvoice_tts_enabled", VoiceState.ttsEnabled);
      updateIcon();
      showToast(`Voice speech response ${VoiceState.ttsEnabled ? 'enabled' : 'muted'}`, "info");
      if (!VoiceState.ttsEnabled && VoiceState.synth) {
        VoiceState.synth.cancel();
      }
    });
  }
});

// Expose global ParkVoiceEngine namespace
window.ParkVoiceEngine = {
  VoiceState,
  classifyIntent,
  processVoiceIntent,
  simulateVoiceCommand,
  executeBooking,
  handleFindParkingIntent,
  handleTraceSlotIntent,
  handleClearRouteIntent
};
