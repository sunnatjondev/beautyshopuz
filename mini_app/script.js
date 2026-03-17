const tg = window.Telegram?.WebApp;
const app = document.getElementById("app");
const toast = document.getElementById("toast");
const backToBotTop = document.getElementById("backToBotTop");
const apiBase =
  (new URLSearchParams(window.location.search).get("api")
    || document.querySelector('meta[name="mini-app-api-base"]')?.content
    || window.location.origin)
    .replace(/\/$/, "");

const state = {
  loading: true,
  error: "",
  busy: false,
  step: "home",
  config: null,
  profile: null,
  serviceId: "",
  masterId: "",
  date: "",
  time: "",
  phone: "",
  name: "",
  slots: [],
  booking: null,
};

const steps = ["service", "master", "date", "time", "contact", "confirm"];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function closeApp() {
  if (tg?.close) {
    tg.close();
    return;
  }
  window.history.back();
}

function openBot() {
  const botLink = state.config?.botLink;
  if (botLink && tg?.openTelegramLink) {
    tg.openTelegramLink(botLink);
    return;
  }
  closeApp();
}

async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({ ok: false, error: "Server javobi noto'g'ri." }));
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "Server xatosi.");
  }
  return data;
}

async function post(path, payload) {
  return api(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

function getSelectedService() {
  return state.config?.services.find((service) => service.id === state.serviceId) || null;
}

function getSelectedMaster() {
  return state.config?.masters.find((master) => master.id === state.masterId) || null;
}

function formatCurrency(amount) {
  return Number(amount || 0).toLocaleString("ru-RU").replaceAll(",", " ");
}

function renderProgress() {
  return `
    <div class="progress">
      ${steps
        .map(
          (step, index) => `
            <span class="progress-pill ${step === state.step ? "active" : ""}">
              ${index + 1}
            </span>
          `
        )
        .join("")}
    </div>
  `;
}

function getDateOptions() {
  const today = new Date(state.config?.today || new Date().toISOString().slice(0, 10));
  const days = Math.min(18, Number(state.config?.bookingWindowDays || 14));
  return Array.from({ length: days }, (_, index) => {
    const value = new Date(today);
    value.setDate(today.getDate() + index);
    const iso = value.toISOString().slice(0, 10);
    const label = value.toLocaleDateString("uz-UZ", {
      day: "2-digit",
      month: "short",
      weekday: "short",
    });
    return { iso, label };
  });
}

function renderLoading(message = "Mini App yuklanmoqda...") {
  app.innerHTML = `
    <section class="loading-card">
      <div class="spinner"></div>
      <p>${escapeHtml(message)}</p>
    </section>
  `;
}

function renderError(message) {
  app.innerHTML = `
    <section class="panel stage-panel">
      <div class="step-header">
        <div>
          <h3>Xatolik yuz berdi</h3>
          <p>Mini App hozircha ishga tushmadi.</p>
        </div>
      </div>
      <div class="status-banner error">${escapeHtml(message)}</div>
      <div class="step-actions" style="margin-top: 16px;">
        <button class="primary-button" data-action="retry" type="button">Qayta urinish</button>
        <button class="secondary-button" data-action="close-app" type="button">Botga qaytish</button>
      </div>
    </section>
  `;
}

function renderHome() {
  const profile = state.profile || {};
  const upcoming = (profile.upcoming || [])
    .map(
      (booking) => `
        <div class="profile-card">
          <h4>${escapeHtml(booking.service)}</h4>
          <p>${escapeHtml(booking.dateLabel)} • ${escapeHtml(booking.time)}</p>
          <p>${escapeHtml(booking.master)}</p>
        </div>
      `
    )
    .join("");

  app.innerHTML = `
    <section class="panel hero">
      <div class="hero-copy">
        <h2>Go'zallik, mehr va qulay yozilish.</h2>
        <p>
          Salom! 🌸 Sizni ko'rganimizdan xursandmiz. O'zingizga mos xizmatni tanlang va bir necha bosqichda yoziling.
        </p>
        <div class="hero-actions">
          <button class="primary-button" data-action="start-booking" type="button">💅 Yozilish</button>
          <button class="secondary-button" data-action="close-app" type="button">Botga qaytish</button>
        </div>
      </div>
    </section>

    <section class="panel stage-panel">
      <div class="dashboard">
        <button class="card-button" data-action="start-booking" type="button">
          <strong>🌸 Xizmatlar</strong>
          <span>${state.config?.services?.length || 0} ta xizmat, bonus +${formatCurrency(state.config?.bonusPerBooking)} UZS</span>
        </button>
        <button class="card-button" data-action="show-profile" type="button">
          <strong>👑 VIP & Bonus</strong>
          <span>${formatCurrency(profile.bonus)} UZS • ${profile.vipStatus || "Mehmon 🌸"}</span>
        </button>
        <button class="card-button" data-action="show-location" type="button">
          <strong>📍 Manzil</strong>
          <span>${escapeHtml(state.config?.address || "")}</span>
        </button>
        <button class="card-button" data-action="show-hours" type="button">
          <strong>🪷 Ish vaqti</strong>
          <span>${escapeHtml(state.config?.workingHours || "")}</span>
        </button>
      </div>
    </section>

    ${
      upcoming
        ? `
          <section class="panel stage-panel">
            <div class="step-header">
              <div>
                <h3>Kelgusi yozilishlar</h3>
                <p>Kabinetdagi faol beauty yozuvlaringiz.</p>
              </div>
            </div>
            <div class="profile-grid">${upcoming}</div>
          </section>
        `
        : ""
    }
  `;
}

function renderServiceStep() {
  app.innerHTML = `
    <section class="panel stage-panel">
      <div class="step-header">
        <div>
          <h3>1. 🌸 Xizmatni tanlang</h3>
          <p>O'zingizga mos beauty xizmatni tanlang.</p>
        </div>
        ${renderProgress()}
      </div>
      <div class="grid-cards">
        ${state.config.services
          .map(
            (service) => `
              <button class="choice-card ${state.serviceId === service.id ? "active" : ""}" data-action="pick-service" data-id="${service.id}" type="button">
                <h4>${escapeHtml(service.name)}</h4>
                <p>${escapeHtml(service.description)}</p>
                <p class="price">${formatCurrency(service.price)} UZS • ${service.duration} daqiqa</p>
              </button>
            `
          )
          .join("")}
      </div>
      <div class="step-actions" style="margin-top: 18px;">
        <button class="secondary-button" data-action="go-home" type="button">Orqaga</button>
      </div>
    </section>
  `;
}

function renderMasterStep() {
  app.innerHTML = `
    <section class="panel stage-panel">
      <div class="step-header">
        <div>
          <h3>2. ✨ Ustani tanlang</h3>
          <p>${escapeHtml(getSelectedService()?.name || "")}</p>
        </div>
        ${renderProgress()}
      </div>
      <div class="grid-cards">
        ${state.config.masters
          .map(
            (master) => `
              <button class="choice-card ${state.masterId === master.id ? "active" : ""}" data-action="pick-master" data-id="${master.id}" type="button">
                <h4>${escapeHtml(master.emoji)} ${escapeHtml(master.name)}</h4>
                <p>${escapeHtml(master.title)}</p>
                <p style="margin-top: 10px;">${escapeHtml(master.about)}</p>
              </button>
            `
          )
          .join("")}
      </div>
      <div class="step-actions" style="margin-top: 18px;">
        <button class="secondary-button" data-action="back-service" type="button">Orqaga</button>
      </div>
    </section>
  `;
}

function renderDateStep() {
  const options = getDateOptions();
  app.innerHTML = `
    <section class="panel stage-panel">
      <div class="step-header">
        <div>
          <h3>3. 🪷 Kunni tanlang</h3>
          <p>${escapeHtml(getSelectedMaster()?.name || "")} uchun qulay kunlar.</p>
        </div>
        ${renderProgress()}
      </div>
      <div class="date-grid">
        ${options
          .map(
            (item) => `
              <button class="date-card ${state.date === item.iso ? "active" : ""}" data-action="pick-date" data-id="${item.iso}" type="button">
                <strong>${escapeHtml(item.label)}</strong>
                <p>${escapeHtml(item.iso)}</p>
              </button>
            `
          )
          .join("")}
      </div>
      <div class="step-actions" style="margin-top: 18px;">
        <button class="secondary-button" data-action="back-master" type="button">Orqaga</button>
      </div>
    </section>
  `;
}

function renderTimeStep() {
  app.innerHTML = `
    <section class="panel stage-panel">
      <div class="step-header">
        <div>
          <h3>4. 💗 Vaqtni tanlang</h3>
          <p>${escapeHtml(state.date)} • ${escapeHtml(getSelectedMaster()?.name || "")}</p>
        </div>
        ${renderProgress()}
      </div>
      <div class="time-grid">
        ${state.slots
          .map(
            (slot) => `
              <button class="slot-card ${state.time === slot.time ? "active" : ""} ${slot.available ? "" : "unavailable"}" ${slot.available ? "" : "disabled"} data-action="pick-time" data-id="${slot.time}" type="button">
                <strong>${slot.available ? "🟢" : "🔴"} ${escapeHtml(slot.time)}</strong>
                <p>${slot.available ? "Bo'sh" : "Band"}</p>
              </button>
            `
          )
          .join("")}
      </div>
      <div class="step-actions" style="margin-top: 18px;">
        <button class="secondary-button" data-action="back-date" type="button">Orqaga</button>
      </div>
    </section>
  `;
}

function renderContactStep() {
  app.innerHTML = `
    <section class="panel stage-panel">
      <div class="step-header">
        <div>
          <h3>5. Kontaktni tasdiqlang</h3>
          <p>Telegram orqali raqam yuborish yoki qo'lda kiritish mumkin.</p>
        </div>
        ${renderProgress()}
      </div>

      <div class="contact-grid">
        <div class="contact-card">
          <h4>Telegram orqali yuborish</h4>
          <p>Telefon raqamingizni xavfsiz tarzda ulashing.</p>
          <div class="step-actions" style="margin-top: 14px;">
            <button class="primary-button" data-action="share-contact" type="button">💗 Raqamni yuborish</button>
            <button class="chip-button" data-action="refresh-profile" type="button">Qayta tekshirish</button>
          </div>
          <div class="contact-note">
            Agar Telegram darhol raqamni bermasa, pastdagi maydonga qo'lda yozishingiz mumkin.
          </div>
        </div>

        <div class="contact-card">
          <h4>Ma'lumotlar</h4>
          <div class="field">
            <label for="nameInput">Ism</label>
            <input id="nameInput" type="text" value="${escapeHtml(state.name)}" placeholder="Ismingiz">
          </div>
          <div class="field" style="margin-top: 12px;">
            <label for="phoneInput">Telefon raqam</label>
            <input id="phoneInput" type="tel" value="${escapeHtml(state.phone)}" placeholder="+998 90 123 45 67">
          </div>
        </div>
      </div>

      <div class="step-actions" style="margin-top: 18px;">
        <button class="secondary-button" data-action="back-time" type="button">Orqaga</button>
        <button class="primary-button" data-action="go-confirm" type="button">Tasdiqlashga o'tish</button>
      </div>
    </section>
  `;
}

function renderConfirmStep() {
  const service = getSelectedService();
  const master = getSelectedMaster();
  app.innerHTML = `
    <section class="panel stage-panel">
      <div class="step-header">
        <div>
          <h3>6. Tasdiqlash</h3>
          <p>Barcha ma'lumotlar to'g'riligini tekshiring.</p>
        </div>
        ${renderProgress()}
      </div>

      <div class="summary-grid">
        <div class="summary-card">
          <h4>Bron tafsilotlari</h4>
          <p>💗 ${escapeHtml(service?.name || "")}</p>
          <p>✨ ${escapeHtml(master?.name || "")}</p>
          <p>📅 ${escapeHtml(state.date)}</p>
          <p>🕒 ${escapeHtml(state.time)}</p>
        </div>
          <div class="summary-card">
            <h4>Mijoz</h4>
            <p>👤 ${escapeHtml(state.name)}</p>
            <p>📱 ${escapeHtml(state.phone)}</p>
            <p>👑 VIP mijoz bonusi!</p>
            <p>💗 Bonus: +${formatCurrency(state.config?.bonusPerBooking)} UZS</p>
          </div>
      </div>

      <div class="step-actions" style="margin-top: 18px;">
        <button class="secondary-button" data-action="back-contact" type="button">Orqaga</button>
        <button class="primary-button" data-action="confirm-booking" type="button">
          ${state.busy ? "Yuborilmoqda..." : "Muvoffaqiyatli yozilish"}
        </button>
      </div>
    </section>
  `;
}

function renderSuccessStep() {
  app.innerHTML = `
    <section class="panel stage-panel">
      <div class="success-shell">
        <h2>Muvoffaqiyatli!</h2>
        <p>
          ${escapeHtml(state.booking?.dateLabel || state.booking?.date || "")} • ${escapeHtml(state.booking?.time || "")}
        </p>
        <div class="summary-grid" style="margin-top: 16px;">
          <div class="summary-card">
            <h4>${escapeHtml(state.booking?.service || "")}</h4>
            <p>✨ Usta: ${escapeHtml(state.booking?.master || "")}</p>
          </div>
          <div class="summary-card">
            <h4>👑 VIP mijoz bonusi!</h4>
            <p>Bonus +${formatCurrency(state.config?.bonusPerBooking)}</p>
            <p>Umumiy bonus: ${formatCurrency(state.booking?.bonus || 0)} UZS</p>
            ${state.booking?.discountPercent ? `<p>VIP chegirma: ${state.booking.discountPercent}% • ${formatCurrency(state.booking.finalPrice)} UZS</p>` : ""}
            <p>Keyingi bepul xizmat: yana ${state.booking?.remainingForFree ?? 0} tashrif</p>
          </div>
        </div>
        <div class="footer-actions" style="margin-top: 22px;">
          <button class="primary-button" data-action="open-bot" type="button">Ochiq bot</button>
          <button class="secondary-button" data-action="close-app" type="button">Botga qaytish</button>
          <button class="chip-button" data-action="go-home" type="button">Asosiy ekran</button>
        </div>
      </div>
    </section>
  `;
}

function render() {
  if (state.loading) {
    renderLoading();
    return;
  }

  if (state.error) {
    renderError(state.error);
    return;
  }

  switch (state.step) {
    case "service":
      renderServiceStep();
      break;
    case "master":
      renderMasterStep();
      break;
    case "date":
      renderDateStep();
      break;
    case "time":
      renderTimeStep();
      break;
    case "contact":
      renderContactStep();
      break;
    case "confirm":
      renderConfirmStep();
      break;
    case "success":
      renderSuccessStep();
      break;
    default:
      renderHome();
  }
}

async function loadSlots() {
  if (!state.masterId || !state.date) {
    return;
  }
  state.loading = true;
  render();
  try {
    const query = new URLSearchParams({ master_id: state.masterId, date: state.date });
    const response = await api(`/api/slots?${query.toString()}`);
    state.slots = response.slots;
    state.loading = false;
    state.step = "time";
    render();
  } catch (error) {
    state.loading = false;
    showToast(error.message);
    render();
  }
}

async function refreshProfile() {
  if (!tg?.initData) {
    return;
  }
  const response = await post("/api/profile", { initData: tg.initData });
  state.profile = response.profile;
  if (!state.phone && response.profile.phone) {
    state.phone = response.profile.phone;
  }
}

async function pollPhone() {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1200));
    try {
      await refreshProfile();
      if (state.profile?.phone) {
        state.phone = state.profile.phone;
        render();
        showToast("Telefon raqami qabul qilindi.");
        return;
      }
    } catch (error) {
      console.error(error);
    }
  }
  showToast("Telefon raqami hali kelmadi. Uni qo'lda kiritishingiz mumkin.");
}

function handleInputChange() {
  const nameInput = document.getElementById("nameInput");
  const phoneInput = document.getElementById("phoneInput");
  if (nameInput) {
    nameInput.addEventListener("input", () => {
      state.name = nameInput.value.trim();
    });
  }
  if (phoneInput) {
    phoneInput.addEventListener("input", () => {
      state.phone = phoneInput.value.trim();
    });
  }
}

async function initialize() {
  backToBotTop.addEventListener("click", closeApp);
  if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor?.("#081114");
    tg.setBackgroundColor?.("#081114");
  }

  try {
    const response = await post("/api/init", { initData: tg?.initData || "" });
    state.config = response.config;
    state.profile = response.profile;
    state.phone = response.profile.phone || "";
    state.name = response.profile.name || tg?.initDataUnsafe?.user?.first_name || "";
    state.loading = false;
    state.step = "home";
    render();
  } catch (error) {
    state.loading = false;
    state.error = error.message;
    render();
  }
}

app.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) {
    return;
  }

  const action = button.dataset.action;
  const id = button.dataset.id;

  try {
    if (action === "retry") {
      state.error = "";
      state.loading = true;
      render();
      await initialize();
      return;
    }

    if (action === "close-app") {
      closeApp();
      return;
    }

    if (action === "open-bot") {
      openBot();
      return;
    }

    if (action === "go-home") {
      state.step = "home";
      render();
      return;
    }

    if (action === "start-booking") {
      state.step = "service";
      render();
      return;
    }

    if (action === "show-profile") {
      showToast(`${state.profile?.vipStatus || "Mehmon 🌸"} • ${formatCurrency(state.profile?.bonus || 0)} UZS`);
      return;
    }

    if (action === "show-location") {
      showToast(state.config?.address || "Manzil topilmadi.");
      return;
    }

    if (action === "show-hours") {
      showToast(state.config?.workingHours || "Ish vaqti topilmadi.");
      return;
    }

    if (action === "pick-service") {
      state.serviceId = id;
      state.masterId = "";
      state.date = "";
      state.time = "";
      state.step = "master";
      render();
      return;
    }

    if (action === "pick-master") {
      state.masterId = id;
      state.date = "";
      state.time = "";
      state.step = "date";
      render();
      return;
    }

    if (action === "pick-date") {
      state.date = id;
      state.time = "";
      await loadSlots();
      return;
    }

    if (action === "pick-time") {
      state.time = id;
      state.step = "contact";
      render();
      handleInputChange();
      return;
    }

    if (action === "share-contact") {
      if (!tg?.requestContact) {
        showToast("Telegram contact API topilmadi. Raqamni qo'lda kiriting.");
        return;
      }
      try {
        tg.requestContact(() => {
          pollPhone();
        });
      } catch (error) {
        console.error(error);
        showToast("Kontakt so'rovini ochib bo'lmadi.");
      }
      return;
    }

    if (action === "refresh-profile") {
      await refreshProfile();
      state.phone = state.profile?.phone || state.phone;
      render();
      handleInputChange();
      showToast("Profil yangilandi.");
      return;
    }

    if (action === "go-confirm") {
      if (!state.name.trim()) {
        showToast("Ismingizni kiriting.");
        return;
      }
      if (!state.phone.trim()) {
        showToast("Telefon raqamingizni yuboring yoki qo'lda kiriting.");
        return;
      }
      state.step = "confirm";
      render();
      return;
    }

    if (action === "confirm-booking") {
      if (state.busy) {
        return;
      }
      state.busy = true;
      render();
      try {
        const response = await post("/api/book", {
          initData: tg?.initData || "",
          serviceId: state.serviceId,
          masterId: state.masterId,
          date: state.date,
          time: state.time,
          phone: state.phone,
          name: state.name,
        });
        state.booking = response.booking;
        await refreshProfile().catch(() => {});
        state.step = "success";
        state.busy = false;
        render();
      } catch (error) {
        state.busy = false;
        render();
        showToast(error.message);
      }
      return;
    }

    if (action === "back-service") {
      state.step = "service";
      render();
      return;
    }

    if (action === "back-master") {
      state.step = "master";
      render();
      return;
    }

    if (action === "back-date") {
      state.step = "date";
      render();
      return;
    }

    if (action === "back-time") {
      state.step = "time";
      render();
      return;
    }

    if (action === "back-contact") {
      state.step = "contact";
      render();
      handleInputChange();
    }
  } catch (error) {
    console.error(error);
    showToast(error.message || "Kutilmagan xatolik.");
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "nameInput") {
    state.name = event.target.value;
  }
  if (event.target.id === "phoneInput") {
    state.phone = event.target.value;
  }
});

initialize();
