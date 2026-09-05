/**
 * ParkVoice AI - Admin Telemetry, Live Simulation & Analytics Engine
 * =================================================================
 * Features:
 * - Simulation controls (Car Entry, Car Exit, Demo Booking, Full Reset)
 * - Real-time slot state switches (Available / Occupied / Reserved)
 * - Live active bookings management
 * - Chart.js real-time analytics graphs
 */

let chartOccupancyInstance = null;
let chartPeakHoursInstance = null;
let chartDailyTrendInstance = null;
let chartSlotUsageInstance = null;

document.addEventListener("DOMContentLoaded", () => {
  loadAdminTelemetry();
  loadAdminSlotsMatrix();
  loadAnalyticsCharts();

  // Periodic refresh
  setInterval(() => {
    loadAdminTelemetry();
    loadAdminSlotsMatrix();
  }, 4000);
});

// Log message to the admin telemetry console banner
function logTelemetry(msg, isSuccess = true) {
  const banner = document.getElementById("simLogText");
  if (banner) {
    const time = new Date().toLocaleTimeString();
    banner.innerHTML = `<span style="color: ${isSuccess ? '#34d399' : '#f87171'};">[${time}]</span> ${msg}`;
  }
}

// Fetch general stats and update stat counters
async function loadAdminTelemetry() {
  try {
    const res = await fetch("/api/admin/stats");
    const data = await res.json();
    if (!data.success) return;

    const s = data.stats;
    document.getElementById("admStatTotal").innerText = s.total_slots;
    document.getElementById("admStatAvail").innerText = s.available;
    document.getElementById("admStatOcc").innerText = s.occupied;
    document.getElementById("admStatRes").innerText = s.reserved;
    document.getElementById("admStatUsers").innerText = s.total_users;
    document.getElementById("admStatActive").innerText = s.active_bookings;

    updateOccupancyChart(s.available, s.occupied, s.reserved);
  } catch (err) {
    console.error("Failed to load admin stats:", err);
  }
}

// Load Slot Management Matrix & Active Bookings Table
async function loadAdminSlotsMatrix() {
  try {
    const res = await fetch("/api/parking/slots");
    const data = await res.json();
    if (!data.success) return;

    const matrix = document.getElementById("adminSlotMatrix");
    const tbody = document.getElementById("adminActiveBookingsBody");

    // 1. Render Matrix
    if (matrix) {
      matrix.innerHTML = data.slots.map(s => {
        const isAvail = s.status === "AVAILABLE";
        const isOcc = s.status === "OCCUPIED";
        const isRes = s.status === "RESERVED";

        return `
          <div class="admin-slot-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <strong>${s.slot_number}</strong>
              <span style="font-size: 0.72rem; color: var(--text-muted);">${s.slot_type}${s.has_ev_charger ? ' ⚡' : ''}</span>
            </div>
            <div class="admin-btn-group">
              <button class="${isAvail ? 'active-avail' : ''}" onclick="toggleSlotStatus('${s.slot_number}', 'AVAILABLE')">Free</button>
              <button class="${isOcc ? 'active-occ' : ''}" onclick="toggleSlotStatus('${s.slot_number}', 'OCCUPIED')">Occ</button>
              <button class="${isRes ? 'active-res' : ''}" onclick="toggleSlotStatus('${s.slot_number}', 'RESERVED')">Res</button>
            </div>
          </div>
        `;
      }).join("");
    }

    // 2. Render Active Bookings
    const activeSlots = data.slots.filter(s => s.status === "RESERVED" && s.booking_code);
    if (tbody) {
      if (activeSlots.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-secondary); padding: 1.5rem;">No active reservations at the moment.</td></tr>`;
      } else {
        tbody.innerHTML = activeSlots.map(s => `
          <tr>
            <td><code style="color: #fbbf24; font-weight: 700;">${s.booking_code}</code></td>
            <td><strong>${s.slot_number}</strong></td>
            <td>${s.booked_by_name || 'Driver'}</td>
            <td>${s.plate_number || '--'} (${s.vehicle_type || 'Car'})</td>
            <td>In Progress</td>
            <td>
              <button class="btn btn-secondary btn-sm" style="color: #34d399;" onclick="forceCompleteSlot('${s.slot_number}')">Complete</button>
              <button class="btn btn-secondary btn-sm" style="color: #f87171;" onclick="forceCancelSlot('${s.slot_number}')">Cancel</button>
            </td>
          </tr>
        `).join("");
      }
    }

  } catch (err) {
    console.error("Failed to load slots matrix:", err);
  }
}

// -------------------------------------------------------------
// LIVE SIMULATION TRIGGERS
// -------------------------------------------------------------

async function simulateCarEntry() {
  try {
    const res = await fetch("/api/admin/simulate/entry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.success) {
      logTelemetry(`Vehicle entered and occupied ${data.slot_number}.`);
      showToast(`Vehicle entered &rarr; Slot ${data.slot_number} occupied`, "info");
      loadAdminTelemetry();
      loadAdminSlotsMatrix();
    } else {
      logTelemetry(data.error || "Simulation failed", false);
    }
  } catch (err) {
    console.error(err);
  }
}

async function simulateCarExit() {
  try {
    const res = await fetch("/api/admin/simulate/exit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.success) {
      logTelemetry(`Vehicle departed from ${data.slot_number}. Slot is now free.`);
      showToast(`Vehicle departed &rarr; Slot ${data.slot_number} free`, "success");
      loadAdminTelemetry();
      loadAdminSlotsMatrix();
    } else {
      logTelemetry(data.error || "Simulation failed", false);
    }
  } catch (err) {
    console.error(err);
  }
}

async function generateSimulatedBooking() {
  try {
    const res = await fetch("/api/admin/simulate/generate-booking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.success) {
      logTelemetry(`Simulated booking ${data.booking_code} placed on ${data.slot_number}.`);
      showToast(`Simulated booking: ${data.slot_number} (${data.booking_code})`, "warning");
      loadAdminTelemetry();
      loadAdminSlotsMatrix();
    } else {
      logTelemetry(data.error || "Could not generate booking", false);
    }
  } catch (err) {
    console.error(err);
  }
}

async function resetAllSlots() {
  if (!confirm("Are you sure you want to reset all slots to AVAILABLE?")) return;
  try {
    const res = await fetch("/api/admin/simulate/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.success) {
      logTelemetry("All 12 parking slots reset to AVAILABLE.");
      showToast("Parking lot reset to available", "success");
      loadAdminTelemetry();
      loadAdminSlotsMatrix();
    }
  } catch (err) {
    console.error(err);
  }
}

async function toggleSlotStatus(slotNumber, status) {
  try {
    const res = await fetch("/api/admin/simulate/toggle-slot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot_number: slotNumber, status: status })
    });
    const data = await res.json();
    if (data.success) {
      logTelemetry(`Slot ${slotNumber} status updated to ${status}.`);
      loadAdminTelemetry();
      loadAdminSlotsMatrix();
    }
  } catch (err) {
    console.error(err);
  }
}

async function forceCompleteSlot(slotNumber) {
  toggleSlotStatus(slotNumber, "AVAILABLE");
}

async function forceCancelSlot(slotNumber) {
  toggleSlotStatus(slotNumber, "AVAILABLE");
}

// -------------------------------------------------------------
// ANALYTICS & CHART.JS INTEGRATION
// -------------------------------------------------------------

async function loadAnalyticsCharts() {
  try {
    const res = await fetch("/api/admin/analytics");
    const data = await res.json();
    if (!data.success) return;

    // 1. Occupancy Breakdown Doughnut
    initOccupancyChart();

    // 2. Peak Hours Bar Chart
    const ctxPeak = document.getElementById("chartPeakHours");
    if (ctxPeak) {
      chartPeakHoursInstance = new Chart(ctxPeak, {
        type: "bar",
        data: {
          labels: data.peak_hours.labels,
          datasets: [{
            label: "Bookings",
            data: data.peak_hours.counts,
            backgroundColor: "rgba(99, 102, 241, 0.6)",
            borderColor: "#6366f1",
            borderWidth: 1,
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" } },
            x: { grid: { display: false } }
          }
        }
      });
    }

    // 3. Daily Trend Line Chart
    const ctxDaily = document.getElementById("chartDailyTrend");
    if (ctxDaily) {
      chartDailyTrendInstance = new Chart(ctxDaily, {
        type: "line",
        data: {
          labels: data.daily_trend.labels,
          datasets: [{
            label: "Daily Bookings",
            data: data.daily_trend.counts,
            borderColor: "#10b981",
            backgroundColor: "rgba(16, 185, 129, 0.15)",
            borderWidth: 2,
            tension: 0.3,
            fill: true
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" } },
            x: { grid: { display: false } }
          }
        }
      });
    }

    // 4. Slot Usage Frequency Bar Chart
    const ctxSlot = document.getElementById("chartSlotUsage");
    if (ctxSlot) {
      chartSlotUsageInstance = new Chart(ctxSlot, {
        type: "bar",
        data: {
          labels: data.slot_usage.labels,
          datasets: [{
            label: "Usage Count",
            data: data.slot_usage.counts,
            backgroundColor: "rgba(168, 85, 247, 0.6)",
            borderColor: "#a855f7",
            borderWidth: 1,
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" } },
            x: { grid: { display: false } }
          }
        }
      });
    }

  } catch (err) {
    console.error("Failed to load analytics charts:", err);
  }
}

function initOccupancyChart() {
  const ctx = document.getElementById("chartOccupancy");
  if (!ctx) return;

  chartOccupancyInstance = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Available", "Occupied", "Reserved"],
      datasets: [{
        data: [12, 0, 0],
        backgroundColor: ["#10b981", "#ef4444", "#f59e0b"],
        borderColor: "#111827",
        borderWidth: 3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "#94a3b8", font: { size: 11 } }
        }
      }
    }
  });
}

function updateOccupancyChart(avail, occ, res) {
  if (chartOccupancyInstance) {
    chartOccupancyInstance.data.datasets[0].data = [avail, occ, res];
    chartOccupancyInstance.update();
  }
}
