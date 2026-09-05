/**
 * ParkVoice AI - Core Client Application Utilities
 */

// Global Toast Notification Helper
function showToast(message, type = "info") {
  let toastContainer = document.getElementById("toastContainer");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "toastContainer";
    toastContainer.style.position = "fixed";
    toastContainer.style.bottom = "24px";
    toastContainer.style.right = "24px";
    toastContainer.style.zIndex = "9999";
    toastContainer.style.display = "flex";
    toastContainer.style.flexDirection = "column";
    toastContainer.style.gap = "8px";
    document.body.appendChild(toastContainer);
  }

  const toast = document.createElement("div");
  toast.className = `alert alert-${type}`;
  toast.style.margin = "0";
  toast.style.boxShadow = "0 10px 25px rgba(0,0,0,0.5)";
  toast.style.animation = "modalFadeIn 0.3s ease";
  toast.innerHTML = `<span>${message}</span>`;

  toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Global active vehicle storage & vehicle cache
let currentSelectedVehicleId = null;
let currentSelectedVehicleType = "Car";
let cachedUserVehicles = [];

// Load user vehicles into select element if present
async function populateVehicleDropdown(selectId = "userVehicleSelect") {
  const select = document.getElementById(selectId);
  if (!select) return;

  try {
    const res = await fetch("/api/vehicles");
    const data = await res.json();
    if (data.success && data.vehicles.length > 0) {
      cachedUserVehicles = data.vehicles;
      select.innerHTML = data.vehicles.map(v => 
        `<option value="${v.id}" data-type="${v.vehicle_type}" ${v.is_default ? 'selected' : ''}>
          ${v.plate_number} (${v.vehicle_type} - ${v.model})
        </option>`
      ).join("");

      // Find selected option
      let selectedOpt = select.querySelector("option[selected]") || select.options[0];
      if (selectedOpt) {
        select.value = selectedOpt.value;
        currentSelectedVehicleId = selectedOpt.value;
        currentSelectedVehicleType = selectedOpt.getAttribute("data-type") || "Car";
        updateVehicleBadgeText(selectedOpt.text);
      }

      select.addEventListener("change", async (e) => {
        const opt = e.target.options[e.target.selectedIndex];
        currentSelectedVehicleId = opt.value;
        currentSelectedVehicleType = opt.getAttribute("data-type") || "Car";
        updateVehicleBadgeText(opt.text);
        showToast(`Active vehicle switched to ${opt.text}`, "info");

        // Persist preference in backend
        try {
          fetch(`/api/vehicles/${currentSelectedVehicleId}/set-default`, { method: "POST" });
        } catch (err) {
          console.warn("Could not persist default vehicle:", err);
        }

        // Re-trigger slot recommendation and route display for this vehicle
        if (typeof runSlotRecommendation === "function") {
          runSlotRecommendation();
        }
        if (typeof checkActiveBooking === "function") {
          checkActiveBooking();
        }
      });
    } else {
      cachedUserVehicles = [];
      select.innerHTML = `<option value="">No registered vehicles (Default: Car)</option>`;
      updateVehicleBadgeText("Default Car");
    }
  } catch (err) {
    console.error("Failed to populate vehicles:", err);
  }
}

function updateVehicleBadgeText(text) {
  const badge = document.getElementById("showingRouteBadge");
  if (badge) {
    badge.innerText = `Focus: ${text.split('(')[0].trim()}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  populateVehicleDropdown();
});
