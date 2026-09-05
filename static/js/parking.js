/**
 * ParkVoice AI - Visual Parking Map & A* Navigation Route Renderer
 * ================================================================
 * Features:
 * - 4x3 Grid (P01–P12) with dedicated Entrance Gate (4, 1)
 * - On-Demand Any-Slot A* Route Tracing (clickable bays & voice tracing)
 * - Multi-Vehicle Booking Support (concurrent per-vehicle reservations)
 * - Animated SVG Routes (Cyan preview trace vs Purple confirmed route)
 * - 3-second live telemetry polling
 * - Per-vehicle elapsed parking timers
 * - Dynamic slot recommendation & alternative options
 */

let cachedSlots = [];
let cachedActiveBookings = [];
let currentActiveBooking = null;
let bookingTimerInterval = null;
let currentDrawnPath = [];
let currentPreviewPath = [];
let currentRecommendedSlot = null;
let selectedModalSlot = null;

document.addEventListener("DOMContentLoaded", () => {
  reloadParkingMap();
  checkActiveBooking();

  // Polling every 3 seconds for live simulation and multi-client updates
  setInterval(() => {
    reloadParkingMap(true);
    checkActiveBooking();
  }, 3000);

  // Window resize re-draws active and preview SVG routes
  window.addEventListener("resize", () => {
    if (currentDrawnPath && currentDrawnPath.length > 0) {
      renderSvgRoute(currentDrawnPath, false);
    }
    if (currentPreviewPath && currentPreviewPath.length > 0) {
      renderSvgRoute(currentPreviewPath, true);
    }
  });

  // Modal Action Buttons
  const btnModalRoute = document.getElementById("modalBtnRoute");
  if (btnModalRoute) {
    btnModalRoute.addEventListener("click", () => {
      if (selectedModalSlot) {
        traceRouteToSlot(selectedModalSlot.slot_number, true);
      }
    });
  }

  const btnModalBook = document.getElementById("modalBtnBook");
  if (btnModalBook) {
    btnModalBook.addEventListener("click", () => {
      if (selectedModalSlot) {
        handleModalBookingSubmit();
      }
    });
  }

  // Modal vehicle select change updates conflict banner
  const modalVehSelect = document.getElementById("modalVehicleSelect");
  if (modalVehSelect) {
    modalVehSelect.addEventListener("change", () => {
      updateModalBookingState();
    });
  }

  // Recommendation Card Confirm Button
  const btnBookRec = document.getElementById("btnBookRecommended");
  if (btnBookRec) {
    btnBookRec.addEventListener("click", () => {
      if (currentRecommendedSlot) {
        executeBooking(currentRecommendedSlot.slot_number, currentRecommendedSlot.id);
      }
    });
  }

  const btnTraceRec = document.getElementById("btnTraceRecSlot");
  if (btnTraceRec) {
    btnTraceRec.addEventListener("click", () => {
      if (currentRecommendedSlot) {
        traceRouteToSlot(currentRecommendedSlot.slot_number, true);
      }
    });
  }
});

// Fetch and render the 4x3 parking grid
async function reloadParkingMap(isBackgroundPoll = false) {
  try {
    const res = await fetch("/api/parking/slots");
    const data = await res.json();
    if (!data.success) return;

    cachedSlots = data.slots;
    updateStatsBar(data.slots);
    render4x3Grid(data.slots);

    if (!isBackgroundPoll) {
      checkActiveBooking();
      runSlotRecommendation();
    }
  } catch (err) {
    console.error("Failed to load parking slots:", err);
  }
}

// Update Top Stats Bar
function updateStatsBar(slots) {
  const avail = slots.filter(s => s.status === "AVAILABLE").length;
  const occ = slots.filter(s => s.status === "OCCUPIED").length;
  const res = slots.filter(s => s.status === "RESERVED").length;

  const elAvail = document.getElementById("statAvailableCount");
  const elOcc = document.getElementById("statOccupiedCount");
  const elRes = document.getElementById("statReservedCount");

  if (elAvail) elAvail.innerText = avail;
  if (elOcc) elOcc.innerText = occ;
  if (elRes) elRes.innerText = res;
}

// Render 4x3 Grid (Every slot is clickable for on-demand A* tracing)
function render4x3Grid(slots) {
  const gridContainer = document.getElementById("parkingGrid");
  if (!gridContainer) return;

  gridContainer.innerHTML = slots.map(slot => {
    const isRecommended = currentRecommendedSlot && currentRecommendedSlot.slot_number === slot.slot_number;
    let badgeText = slot.status;
    let badgeClass = "badge-available";

    if (slot.status === "OCCUPIED") {
      badgeClass = "badge-occupied";
    } else if (slot.status === "RESERVED") {
      badgeClass = "badge-reserved";
    }

    const evIndicator = slot.has_ev_charger
      ? `<span class="ev-tag">⚡ EV FAST</span>`
      : ``;

    return `
      <div id="slot-card-${slot.slot_number}" 
           class="parking-slot-card status-${slot.status} ${isRecommended ? 'is-recommended' : ''}"
           data-slot="${slot.slot_number}"
           data-row="${slot.row_index}"
           data-col="${slot.col_index}"
           title="Click to trace A* path to ${slot.slot_number}"
           onclick="handleSlotClick('${slot.slot_number}')">
        
        <div class="slot-top">
          <span class="slot-id">${slot.slot_number}</span>
          <span class="slot-badge ${badgeClass}">${badgeText}</span>
        </div>

        <div class="slot-center">
          ${evIndicator}
          <span>${slot.slot_type}</span>
        </div>

        <div class="slot-bottom">
          <span>$${slot.price_per_hour.toFixed(2)}/hr</span>
          <span>(${slot.row_index}, ${slot.col_index})</span>
        </div>
      </div>
    `;
  }).join("");

  // Re-draw SVG route points if active
  if (currentDrawnPath && currentDrawnPath.length > 0) {
    requestAnimationFrame(() => renderSvgRoute(currentDrawnPath, false));
  }
  if (currentPreviewPath && currentPreviewPath.length > 0) {
    requestAnimationFrame(() => renderSvgRoute(currentPreviewPath, true));
  }
}

// Feature 2: Handle click on ANY slot (Available, Reserved, or Occupied)
async function handleSlotClick(slotNumber) {
  // 1. Trace A* Route on-demand (Preview in distinct Cyan dashed line)
  await traceRouteToSlot(slotNumber, true);

  // 2. Open Inspection & Booking Modal
  openSlotModal(slotNumber);
}

// Trace A* Route to any specific slot via API
async function traceRouteToSlot(slotNumber, isPreview = true) {
  try {
    const res = await fetch("/api/parking/path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot_number: slotNumber })
    });

    const data = await res.json();
    if (data.success && data.path && data.path.length > 0) {
      if (isPreview) {
        currentPreviewPath = data.path;
        renderSvgRoute(data.path, true);
      } else {
        currentDrawnPath = data.path;
        renderSvgRoute(data.path, false);
      }

      const estSec = Math.max(15, data.distance * 12);
      const statusText = document.getElementById("routeStatusText");
      if (statusText) {
        statusText.innerText = `A* Path to ${slotNumber}: ${data.distance} steps (~${estSec}s drive) ${isPreview ? '• Preview' : ''}`;
      }

      // Update in modal if open
      const distEl = document.getElementById("modalSlotDist");
      if (distEl) distEl.innerText = `${data.distance} steps (~${estSec}s)`;

      showToast(`A* path traced to ${slotNumber} (${data.distance} steps, ~${estSec}s)`, "info");
      return data;
    } else {
      showToast(`No clear path found to slot ${slotNumber}`, "warning");
      return null;
    }
  } catch (err) {
    console.error("Error tracing route:", err);
    return null;
  }
}

// Render SVG Polyline across Grid Coordinates
function renderSvgRoute(path, isPreview = false) {
  const stage = document.getElementById("gridStage");
  const polyline = document.getElementById(isPreview ? "previewPolyline" : "routePolyline");
  const entranceEl = document.getElementById("entranceGate");

  if (!stage || !polyline || !entranceEl || !path || path.length === 0) return;

  const stageRect = stage.getBoundingClientRect();
  const points = [];

  // Remove existing path markers of this type
  const removeClass = isPreview ? "on-preview-route" : "on-route";
  const addClass = isPreview ? "on-preview-route" : "on-route";
  document.querySelectorAll(".parking-slot-card").forEach(el => el.classList.remove(removeClass));

  path.forEach((coord) => {
    const [r, c] = coord;

    if (r === 4 && c === 1) {
      // Entrance Gate center
      const gateRect = entranceEl.getBoundingClientRect();
      const x = (gateRect.left + gateRect.width / 2) - stageRect.left;
      const y = (gateRect.top + gateRect.height / 2) - stageRect.top;
      points.push(`${x},${y}`);
    } else {
      // Match with slot card if in 4x3 range
      const slot = cachedSlots.find(s => s.row_index === r && s.col_index === c);
      if (slot) {
        const slotEl = document.getElementById(`slot-card-${slot.slot_number}`);
        if (slotEl) {
          slotEl.classList.add(addClass);
          const rect = slotEl.getBoundingClientRect();
          const x = (rect.left + rect.width / 2) - stageRect.left;
          const y = (rect.top + rect.height / 2) - stageRect.top;
          points.push(`${x},${y}`);
        }
      } else {
        // Aisle waypoint
        const colWidth = stageRect.width / 3;
        const rowHeight = (stageRect.height - 80) / 4;
        const x = Math.max(20, Math.min(stageRect.width - 20, (c + 0.5) * colWidth));
        const y = Math.max(20, (r + 0.5) * rowHeight);
        points.push(`${x},${y}`);
      }
    }
  });

  polyline.setAttribute("points", points.join(" "));
}

// Clear preview trace
function clearPreviewRoute() {
  currentPreviewPath = [];
  const polyline = document.getElementById("previewPolyline");
  if (polyline) polyline.setAttribute("points", "");
  document.querySelectorAll(".parking-slot-card").forEach(el => el.classList.remove("on-preview-route"));
}

// Highlight Recommended Slot & Trace A* Route
function highlightRecommendedSlot(slot, path, distance) {
  currentRecommendedSlot = slot;
  currentDrawnPath = path;

  // Show recommendation card in right column
  const card = document.getElementById("recommendationCard");
  if (card) {
    card.style.display = "block";
    document.getElementById("recSlotNumber").innerText = slot.slot_number;
    document.getElementById("recPriceTag").innerText = `$${slot.price_per_hour.toFixed(2)}/hr`;
    document.getElementById("recDistPill").innerText = `📍 ${distance} steps from entrance`;
    document.getElementById("recTypePill").innerText = `${slot.slot_type}${slot.has_ev_charger ? ' • EV Fast Charger' : ''}`;
    
    const vName = currentSelectedVehicleType || "Vehicle";
    const vPill = document.getElementById("recVehiclePill");
    if (vPill) vPill.innerText = `For: ${vName}`;

    document.getElementById("recReasonText").innerText = `Optimal navigable slot for your ${vName} via A* Manhattan distance.`;
    document.getElementById("recTimeStr").innerText = `~${Math.max(15, distance * 12)} sec drive`;
  }

  // Re-render grid to apply pulse effect
  render4x3Grid(cachedSlots);
  renderSvgRoute(path, false);

  const statusText = document.getElementById("routeStatusText");
  if (statusText) {
    statusText.innerText = `A* Path to ${slot.slot_number}: ${distance} steps`;
  }
}

// Run dynamic recommendation for active vehicle
async function runSlotRecommendation() {
  try {
    const payload = {};
    if (currentSelectedVehicleId) {
      payload.vehicle_id = parseInt(currentSelectedVehicleId);
    }
    if (currentSelectedVehicleType) {
      payload.vehicle_type = currentSelectedVehicleType;
    }

    const res = await fetch("/api/parking/find-parking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.success && data.recommendation && data.recommendation.recommended_slot) {
      const rec = data.recommendation;
      highlightRecommendedSlot(rec.recommended_slot, rec.path, rec.distance);

      // Render alternative candidate options if any
      const altBox = document.getElementById("recAlternativesBox");
      const altList = document.getElementById("recAlternativesList");
      if (altBox && altList && rec.all_candidates && rec.all_candidates.length > 1) {
        altBox.style.display = "block";
        const alternatives = rec.all_candidates.slice(1, 4);
        altList.innerHTML = alternatives.map(c => 
          `<button type="button" class="btn btn-secondary btn-sm" style="font-size: 0.72rem; padding: 2px 7px;" onclick="traceRouteToSlot('${c.slot_number}', true)">
            ${c.slot_number} (${c.distance} steps)
          </button>`
        ).join("");
      }
    }
  } catch (err) {
    console.error("Error running slot recommendation:", err);
  }
}

// Feature 1: Multi-Vehicle Active Bookings Checker & Live Timers
async function checkActiveBooking() {
  try {
    const res = await fetch("/api/bookings/active");
    const data = await res.json();
    const section = document.getElementById("activeBookingsSection");

    if (data.success && data.active_bookings && data.active_bookings.length > 0) {
      cachedActiveBookings = data.active_bookings;
      if (section) section.style.display = "block";

      renderActiveBookingsList(data.active_bookings);

      // Start multi-timer tick
      startMultiBookingTimers();

      // If active vehicle has a booking, show its route by default
      const activeVehBooking = data.active_bookings.find(b => strEqual(b.vehicle_id, currentSelectedVehicleId)) || data.active_bookings[0];
      if (activeVehBooking && activeVehBooking.path && activeVehBooking.path.length > 0) {
        currentDrawnPath = activeVehBooking.path;
        renderSvgRoute(activeVehBooking.path, false);
      }
    } else {
      cachedActiveBookings = [];
      if (section) section.style.display = "none";
      if (bookingTimerInterval) clearInterval(bookingTimerInterval);
    }
  } catch (err) {
    console.error("Error checking active bookings:", err);
  }
}

// Render multi-vehicle active reservation cards
function renderActiveBookingsList(bookings) {
  const container = document.getElementById("activeBookingsList");
  const countBadge = document.getElementById("activeReservationsCountBadge");
  if (!container) return;

  if (countBadge) {
    countBadge.innerText = `${bookings.length} Vehicle${bookings.length > 1 ? 's' : ''} Active`;
  }

  container.innerHTML = bookings.map(b => {
    const isSelected = strEqual(b.vehicle_id, currentSelectedVehicleId);
    return `
      <div class="multi-booking-item ${isSelected ? 'is-active-vehicle' : ''}" id="booking-card-${b.id}">
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
          <div style="display: flex; align-items: baseline; gap: 0.5rem;">
            <strong style="font-size: 1.3rem; color: var(--text-primary); font-weight: 800;">${b.slot_number}</strong>
            <span class="booking-code-tag" style="font-size: 0.72rem; padding: 1px 6px;">${b.booking_code}</span>
          </div>
          <span class="booking-live-elapsed" data-start="${b.start_time}" style="font-size: 0.8rem; font-weight: 700; color: #fbbf24;">00:00:00</span>
        </div>

        <div style="font-size: 0.8rem; color: var(--text-secondary); display: flex; justify-content: space-between;">
          <span>🚗 <strong>${b.plate_number}</strong> (${b.vehicle_type} - ${b.model})</span>
          <span>$${b.price_per_hour.toFixed(2)}/hr</span>
        </div>

        <div style="display: flex; gap: 0.4rem; margin-top: 0.4rem;">
          <button class="btn btn-secondary btn-sm" style="flex: 1; font-size: 0.72rem; padding: 3px 6px;" onclick="focusBookingRoute(${b.id})">
            Trace Route
          </button>
          <button class="btn btn-secondary btn-sm" style="flex: 1; font-size: 0.72rem; padding: 3px 6px;" onclick="cancelSpecificBooking(${b.id}, '${b.slot_number}')">
            Cancel
          </button>
          <button class="btn btn-primary btn-sm" style="flex: 1.2; font-size: 0.72rem; padding: 3px 6px;" onclick="releaseSpecificBooking(${b.id}, '${b.slot_number}')">
            Leave & Pay
          </button>
        </div>
      </div>
    `;
  }).join("");
}

// Focus route on map for a specific active reservation
function focusBookingRoute(bookingId) {
  const b = cachedActiveBookings.find(x => x.id === bookingId);
  if (!b) return;

  if (b.path && b.path.length > 0) {
    currentDrawnPath = b.path;
    renderSvgRoute(b.path, false);
    const statusText = document.getElementById("routeStatusText");
    if (statusText) {
      statusText.innerText = `Active Route: ${b.slot_number} for ${b.plate_number} (${b.distance} steps)`;
    }
    showToast(`Displaying navigation route for ${b.slot_number} (${b.plate_number})`, "info");
  } else {
    traceRouteToSlot(b.slot_number, false);
  }
}

// Cancel a specific vehicle's booking
async function cancelSpecificBooking(bookingId, slotNumber) {
  if (!confirm(`Are you sure you want to cancel the active reservation for slot ${slotNumber}?`)) {
    return;
  }

  try {
    const res = await fetch("/api/bookings/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ booking_id: bookingId })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(`Booking for slot ${slotNumber} cancelled.`, "info");
      speakResponse(`Booking for slot ${slotNumber} has been cancelled.`);
      await reloadParkingMap();
      await checkActiveBooking();
    } else {
      showToast(data.error || "Failed to cancel booking", "danger");
    }
  } catch (err) {
    console.error("Cancel booking error:", err);
  }
}

// Release and complete a specific vehicle's booking
async function releaseSpecificBooking(bookingId, slotNumber) {
  if (!confirm(`Complete parking session for slot ${slotNumber} and depart?`)) {
    return;
  }

  try {
    const res = await fetch("/api/bookings/release", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ booking_id: bookingId })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(`Completed! Duration: ${data.duration_minutes} min, Total: $${data.fee_paid.toFixed(2)}`, "success");
      speakResponse(`Session complete for slot ${slotNumber}. Fee is $${data.fee_paid.toFixed(2)}.`);
      await reloadParkingMap();
      await checkActiveBooking();
    } else {
      showToast(data.error || "Failed to release parking session", "danger");
    }
  } catch (err) {
    console.error("Release booking error:", err);
  }
}

// Live Elapsed Timers for all active bookings
function startMultiBookingTimers() {
  if (bookingTimerInterval) clearInterval(bookingTimerInterval);

  const update = () => {
    const nowMs = Date.now();
    document.querySelectorAll(".booking-live-elapsed").forEach(el => {
      const startMs = new Date(el.getAttribute("data-start")).getTime();
      if (!startMs) return;

      const diffSec = Math.max(0, Math.floor((nowMs - startMs) / 1000));
      const hrs = String(Math.floor(diffSec / 3600)).padStart(2, "0");
      const mins = String(Math.floor((diffSec % 3600) / 60)).padStart(2, "0");
      const secs = String(diffSec % 60).padStart(2, "0");
      el.innerText = `${hrs}:${mins}:${secs}`;
    });
  };

  update();
  bookingTimerInterval = setInterval(update, 1000);
}

// Slot Inspection & Booking Modal
function openSlotModal(slotNumber) {
  const slot = cachedSlots.find(s => s.slot_number === slotNumber);
  if (!slot) return;

  selectedModalSlot = slot;
  document.getElementById("modalSlotTitle").innerText = `Slot ${slot.slot_number}`;
  
  const badgeEl = document.getElementById("modalHeaderBadge");
  if (badgeEl) {
    badgeEl.innerText = slot.status;
    badgeEl.className = `slot-badge ${slot.status === 'AVAILABLE' ? 'badge-available' : slot.status === 'OCCUPIED' ? 'badge-occupied' : 'badge-reserved'}`;
  }

  document.getElementById("modalSlotPrice").innerText = `$${slot.price_per_hour.toFixed(2)}/hr`;
  document.getElementById("modalSlotType").innerText = slot.slot_type;
  document.getElementById("modalSlotEV").innerText = slot.has_ev_charger ? "⚡ Equipped (Fast Charge)" : "Standard";

  // Populate vehicle selector in modal
  populateModalVehiclesDropdown();

  // Occupant info if unavailable
  const occupantEl = document.getElementById("modalSlotOccupant");
  if (slot.status !== "AVAILABLE" && slot.booked_by_name) {
    occupantEl.style.display = "block";
    document.getElementById("modalOccupantName").innerText = `${slot.status}: ${slot.booked_by_name} (${slot.plate_number || 'Vehicle'})`;
  } else {
    occupantEl.style.display = "none";
  }

  // Update modal booking state & alerts
  updateModalBookingState();

  document.getElementById("slotModal").style.display = "flex";
}

function closeSlotModal() {
  document.getElementById("slotModal").style.display = "none";
  selectedModalSlot = null;
}

// Populate Vehicle Dropdown inside Slot Booking Modal
function populateModalVehiclesDropdown() {
  const select = document.getElementById("modalVehicleSelect");
  if (!select) return;

  if (cachedUserVehicles && cachedUserVehicles.length > 0) {
    select.innerHTML = cachedUserVehicles.map(v => {
      const activeRes = cachedActiveBookings.find(b => strEqual(b.vehicle_id, v.id));
      const statusNote = activeRes ? ` (Already Booked: ${activeRes.slot_number})` : "";
      const isSelected = strEqual(v.id, currentSelectedVehicleId);
      return `<option value="${v.id}" data-type="${v.vehicle_type}" ${isSelected ? 'selected' : ''}>
        ${v.plate_number} (${v.vehicle_type} - ${v.model})${statusNote}
      </option>`;
    }).join("");
  } else {
    select.innerHTML = `<option value="">No vehicles found - please add one in Garage</option>`;
  }
}

// Update modal button state and warning alerts
function updateModalBookingState() {
  const slot = selectedModalSlot;
  if (!slot) return;

  const bookBtn = document.getElementById("modalBtnBook");
  const alertEl = document.getElementById("modalAlertMessage");
  const vSelect = document.getElementById("modalVehicleSelect");
  const selectedVehId = vSelect ? vSelect.value : currentSelectedVehicleId;

  if (alertEl) {
    alertEl.style.display = "none";
    alertEl.innerHTML = "";
  }

  if (slot.status !== "AVAILABLE") {
    // Slot is already occupied or reserved
    if (bookBtn) {
      bookBtn.style.display = "inline-flex";
      bookBtn.disabled = true;
      bookBtn.innerText = "Slot Unavailable";
      bookBtn.style.opacity = "0.5";
    }

    if (alertEl) {
      alertEl.style.display = "block";
      alertEl.className = "alert alert-warning";
      alertEl.innerHTML = `⚠️ <strong>Notice:</strong> This parking bay is currently ${slot.status.toLowerCase()}. You can view its A* navigation route on the map.`;
    }
    return;
  }

  // Slot is AVAILABLE
  if (bookBtn) {
    bookBtn.style.display = "inline-flex";
    bookBtn.disabled = false;
    bookBtn.style.opacity = "1";
    bookBtn.innerText = "Confirm & Reserve Slot";
  }

  // Check if selected vehicle already has an active reservation
  const existingForVeh = cachedActiveBookings.find(b => strEqual(b.vehicle_id, selectedVehId));
  if (existingForVeh) {
    if (alertEl) {
      alertEl.style.display = "block";
      alertEl.className = "alert alert-warning";
      alertEl.innerHTML = `⚠️ This vehicle already has an active reservation for <strong>Slot ${existingForVeh.slot_number}</strong> (${existingForVeh.booking_code}). Please complete or cancel it first, or choose another vehicle from your garage above.`;
    }
    if (bookBtn) {
      bookBtn.disabled = true;
      bookBtn.innerText = "Vehicle Already Booked";
      bookBtn.style.opacity = "0.6";
    }
  }
}

// Handle Modal Booking Submission
async function handleModalBookingSubmit() {
  if (!selectedModalSlot) return;

  const vSelect = document.getElementById("modalVehicleSelect");
  const vehicleId = vSelect ? vSelect.value : currentSelectedVehicleId;

  if (!vehicleId) {
    alert("Please select a vehicle from your garage first.");
    return;
  }

  const bookBtn = document.getElementById("modalBtnBook");
  if (bookBtn) {
    bookBtn.disabled = true;
    bookBtn.innerText = "Reserving...";
  }

  await executeBooking(selectedModalSlot.slot_number, selectedModalSlot.id, vehicleId);

  if (bookBtn) {
    bookBtn.disabled = false;
    bookBtn.innerText = "Confirm & Reserve Slot";
  }
}

// Close Booking Success Modal
function closeSuccessModal() {
  const modal = document.getElementById("bookingSuccessModal");
  if (modal) modal.style.display = "none";
}

// Helper: String equality for IDs
function strEqual(a, b) {
  return String(a) === String(b);
}
