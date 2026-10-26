(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const state = {
    data: null,
    days: new Map(),
    noticeFilter: "tutti",
    noticeQuery: ""
  };

  const CATEGORY_LABELS = {
    viabilita: "Viabilità",
    navigazione: "Navigazione",
    calendario: "Calendario"
  };

  const STATUS_LABELS = {
    APERTA: "Aperta",
    CHIUSA: "Chiusa",
    CHIUSURA_NOTTURNA: "Chiusura notturna",
    NON_DEFINITA: "Non definita"
  };

  const KIND_LABELS = {
    battello: "Battello",
    traghetto: "Traghetto"
  };

  const dateLong = new Intl.DateTimeFormat("it-IT", {
    timeZone: "Europe/Rome",
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric"
  });

  const dateShort = new Intl.DateTimeFormat("it-IT", {
    timeZone: "Europe/Rome",
    weekday: "short",
    day: "numeric",
    month: "short"
  });

  const datePlain = new Intl.DateTimeFormat("it-IT", {
    timeZone: "Europe/Rome",
    day: "numeric",
    month: "long",
    year: "numeric"
  });

  const dateNumeric = new Intl.DateTimeFormat("it-IT", {
    timeZone: "Europe/Rome",
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  });

  const dateMonth = new Intl.DateTimeFormat("it-IT", {
    timeZone: "Europe/Rome",
    day: "numeric",
    month: "long"
  });

  const timeShort = new Intl.DateTimeFormat("it-IT", {
    timeZone: "Europe/Rome",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23"
  });

  const romeFormatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Rome",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23"
  });

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    setupNavigation();
    setupDialog();
    setupNoticeControls();
    setupServiceWorker();

    try {
      const response = await fetch("data.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      hydrate(data);
    } catch (error) {
      console.error("Impossibile caricare data.json", error);
      renderLoadError();
    }

    alignHashTarget();
  }

  // I contenuti arrivano dopo il primo layout: il browser ha già risolto l'ancora
  // sull'altezza provvisoria della pagina, quindi la riallineiamo a dati caricati.
  function alignHashTarget() {
    let id = "";
    try {
      id = decodeURIComponent(window.location.hash.slice(1));
    } catch {
      id = "";
    }
    if (!id) return;

    const target = document.getElementById(id);
    if (!target) return;

    const root = document.documentElement;
    const previous = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";
    target.scrollIntoView({ block: "start" });
    root.style.scrollBehavior = previous;
  }

  function hydrate(data) {
    if (!data || !data.calendar || !Array.isArray(data.calendar.days)) {
      renderLoadError();
      return;
    }

    state.data = data;
    state.days = new Map(data.calendar.days.map((day) => [day.date, day]));

    $("#data-error").hidden = true;
    $("#status-card").setAttribute("aria-busy", "false");

    renderStatus();
    renderStats();
    renderNights();
    renderCalendar();
    renderServices();
    renderNotices();
    renderTimetables();
    renderSources();
    renderFreshness();
    updateCalendarMarkers();

    window.setInterval(() => {
      renderStatus();
      renderStats();
      renderNights();
      updateCalendarMarkers();
    }, 60000);
  }

  function getRomeNow() {
    const parts = Object.fromEntries(
      romeFormatter
        .formatToParts(new Date())
        .filter((part) => part.type !== "literal")
        .map((part) => [part.type, part.value])
    );

    return {
      date: `${parts.year}-${parts.month}-${parts.day}`,
      hour: Number(parts.hour),
      minute: Number(parts.minute)
    };
  }

  function addDays(isoDate, amount) {
    const date = new Date(`${isoDate}T12:00:00Z`);
    date.setUTCDate(date.getUTCDate() + amount);
    return date.toISOString().slice(0, 10);
  }

  function currentNightContext() {
    const now = getRomeNow();
    const key = now.hour < 5 ? addDays(now.date, -1) : now.date;
    const day = state.days.get(key) || null;
    const closure = state.data?.calendar?.closure_window || {};
    const startHour = Number((closure.start || "21:00").split(":")[0]);
    const endHour = Number((closure.end || "05:00").split(":")[0]);
    const inWindow =
      startHour > endHour
        ? now.hour >= startHour || now.hour < endHour
        : now.hour >= startHour && now.hour < endHour;

    return {
      ...now,
      key,
      day,
      closure,
      inWindow,
      active: Boolean(day?.night_closed && inWindow)
    };
  }

  function statusTone(day) {
    if (!day || day.status === "NON_DEFINITA") return "unknown";
    if (day.status === "APERTA") return "open";
    if (day.night_closed) return "closed";
    return "pending";
  }

  function renderStatus() {
    if (!state.data) return;

    const context = currentNightContext();
    const badge = $("#status-badge");
    const title = $("#status-title");
    const detail = $("#status-detail");
    const windowValue = $("#status-window strong");
    const link = $("#status-link");
    const source = $(".status-source");
    const day = context.day;
    const tone = statusTone(day);
    const closureLabel = `${context.closure?.start || "21:00"} → ${context.closure?.end || "05:00"}`;

    windowValue.textContent = closureLabel;

    if (!day) {
      badge.className = "status-badge status-unknown";
      badge.textContent = "Fuori calendario";
      title.textContent = "Notte non coperta dal calendario";
      detail.textContent =
        "Il calendario ufficiale non contiene questa notte. Controlla la fonte prima di metterti in viaggio.";
      link.textContent = "Apri il calendario";
    } else if (tone === "open") {
      badge.className = "status-badge status-open";
      badge.textContent = "SS34 aperta";
      title.textContent = "Nessuna chiusura stanotte";
      detail.textContent =
        "La strada resta aperta. I servizi via lago restano consultabili, ma non sono necessari per aggirare la chiusura.";
      link.textContent = "Vedi la notte sul calendario";
    } else if (tone === "closed" && context.active) {
      badge.className = "status-badge status-closed";
      badge.textContent = "Chiusura in corso";
      title.textContent = "SS34 chiusa dalle 21:00";
      detail.textContent = `La chiusura notturna è in corso e termina alle ${context.closure?.end || "05:00"}. Usa i servizi via lago o attendi la riapertura.`;
      link.textContent = "Vedi dettagli e fonte";
    } else if (tone === "closed") {
      badge.className = "status-badge status-closed";
      badge.textContent = "Chiusura prevista";
      title.textContent = "SS34 chiusa questa notte";
      detail.textContent = `La strada chiuderà alle ${context.closure?.start || "21:00"} fino alle ${context.closure?.end || "05:00"}. I servizi via lago sono attivi.`;
      link.textContent = "Vedi dettagli e fonte";
    } else {
      badge.className = "status-badge status-unknown";
      badge.textContent = "Dato non definito";
      title.textContent = "Stato da verificare";
      detail.textContent =
        "Il calendario non riporta uno stato definitivo per questa notte. Consulta la fonte ufficiale.";
      link.textContent = "Apri il calendario";
    }

    if (source) {
      const sourceDate = formatDay(state.data.calendar.updated_at);
      source.textContent = sourceDate
        ? `Fonte: Comune di Verbania · calendario del ${sourceDate}`
        : "Fonte: Comune di Verbania";
    }
  }

  function renderStats() {
    if (!state.data) return;

    const context = currentNightContext();
    const day = context.day;
    const services = state.data.services || [];
    const departures = services.reduce((total, service) => total + (service.times?.length || 0), 0);
    const nightDate = day ? dateShort.format(new Date(`${day.date}T12:00:00Z`)) : "—";
    const nightNote = day
      ? `${STATUS_LABELS[day.status] || day.status_label || "Stato"} · ${day.night_closed ? `${context.closure?.start || "21:00"}–${context.closure?.end || "05:00"}` : "nessuna chiusura"}`
      : "Fuori calendario";

    $("#stat-night").textContent = nightDate;
    $("#stat-night-note").textContent = nightNote;
    $("#stat-window").textContent = `${context.closure?.start || "21:00"}–${context.closure?.end || "05:00"}`;
    $("#stat-services").textContent = `${services.length} ${services.length === 1 ? "tratta" : "tratte"}`;
    $("#stat-services + .stat-note").textContent = `${departures} ${departures === 1 ? "partenza serale" : "partenze serali"}`;
  }

  function renderNights() {
    if (!state.data) return;

    const container = $("#night-grid");
    const context = currentNightContext();
    const sourceUrl = state.data.calendar.source_url;
    const items = [];

    for (let offset = 0; offset <= 30 && items.length < 3; offset += 1) {
      const key = addDays(context.key, offset);
      const day = state.days.get(key);
      if (day) items.push(day);
    }

    if (!items.length) {
      container.innerHTML = `<div class="empty-state"><strong>Calendario non disponibile.</strong><span>Apri la fonte ufficiale per conoscere lo stato della SS34.</span></div>`;
      return;
    }

    container.innerHTML = items
      .map((day) => {
        const tone = statusTone(day);
        const isCurrent = day.date === context.key;
        const status = STATUS_LABELS[day.status] || day.status_label || "Stato";
        const windowLabel = day.night_closed
          ? `${context.closure?.start || "21:00"} → ${context.closure?.end || "05:00"}`
          : "Nessuna chiusura";
        const topLabel = isCurrent
          ? context.active
            ? "Chiusura in corso"
            : "Stanotte"
          : `Notte di ${dateLong.format(new Date(`${day.date}T12:00:00Z`))}`;

        return `
          <article class="night-card is-${tone}${isCurrent ? " is-current" : ""}">
            <div class="night-top">
              <span class="night-date">${escapeHtml(topLabel)}</span>
            </div>
            <div class="night-day">
              <strong>${day.day}</strong>
              <span>${escapeHtml(dateMonth.format(new Date(`${day.date}T12:00:00Z`)).replace(/^\d+\s/, ""))}</span>
            </div>
            <span class="night-status">${escapeHtml(status)}</span>
            <div class="night-window">
              <span>${day.night_closed ? "Chiusura" : "Stato"}</span>
              <strong>${escapeHtml(windowLabel)}</strong>
            </div>
            <a class="night-source" href="${escapeHtml(safeUrl(sourceUrl))}" target="_blank" rel="noopener noreferrer">Fonte: Comune di Verbania ↗</a>
          </article>
        `;
      })
      .join("");

    const sourceChip = $("#nights-source");
    sourceChip.href = safeUrl(sourceUrl);
    sourceChip.target = "_blank";
    sourceChip.rel = "noopener noreferrer";
  }

  function renderCalendar() {
    if (!state.data) return;

    const calendar = state.data.calendar;
    const container = $("#calendar-grid");
    const sourceUrl = safeUrl(calendar.source_url);
    const context = currentNightContext();
    const today = context.date;

    $("#calendar-updated").textContent = calendar.updated_label
      ? `Aggiornato dal Comune il ${calendar.updated_label}. ${calendar.days.length} notti nel calendario.`
      : `${calendar.days.length} notti nel calendario operativo.`;

    const calendarSource = $("#calendar-source");
    calendarSource.href = sourceUrl;
    calendarSource.target = "_blank";
    calendarSource.rel = "noopener noreferrer";

    container.innerHTML = (calendar.months || [])
      .map((month) => {
        const rows = (month.weeks || [])
          .map((week) => {
            const cells = week
              .map((day) => {
                if (!day) return `<td class="cal-empty" aria-hidden="true"></td>`;
                const isCurrent = day.date === context.key;
                const isToday = day.date === today;
                const status = STATUS_LABELS[day.status] || day.status_label || "Stato";
                const aria = `${dateLong.format(new Date(`${day.date}T12:00:00Z`))}, ${status}`;

                return `
                  <td>
                    <button
                      class="cal-day status-${statusClass(day.status)}${isCurrent ? " is-current" : ""}${isToday ? " is-today" : ""}"
                      type="button"
                      data-date="${day.date}"
                      aria-label="${escapeHtml(aria)}. Apri i dettagli"
                      title="${escapeHtml(aria)}"
                    >
                      <span class="cal-num">${day.day}</span>
                      <span class="cal-status">${escapeHtml(shortStatus(day.status))}</span>
                    </button>
                  </td>
                `;
              })
              .join("");
            return `<tr>${cells}</tr>`;
          })
          .join("");

        const headers = (month.weekdays || ["lun", "mar", "mer", "gio", "ven", "sab", "dom"])
          .map((weekday) => `<th scope="col">${escapeHtml(weekday)}</th>`)
          .join("");

        return `
          <article class="month-card">
            <div class="month-head">
              <h3>${escapeHtml(month.label || `${month.month}/${month.year}`)}</h3>
              <a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer" aria-label="Apri la fonte del calendario per ${escapeHtml(month.label)}">fonte ↗</a>
            </div>
            <table class="month-table">
              <thead><tr>${headers}</tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </article>
        `;
      })
      .join("");

    container.addEventListener("click", (event) => {
      const button = event.target.closest("[data-date]");
      if (button) openDay(button.dataset.date);
    });
  }

  function updateCalendarMarkers() {
    if (!state.data) return;

    const context = currentNightContext();
    $$(".cal-day").forEach((button) => {
      button.classList.toggle("is-current", button.dataset.date === context.key);
      button.classList.toggle("is-today", button.dataset.date === context.date);
    });
  }

  function renderServices() {
    if (!state.data) return;

    const container = $("#services-grid");
    const alertContainer = $("#services-alert");
    const services = state.data.services || [];
    const sourceChip = $("#services-source");

    if (services.length) {
      const firstSource = services.find((service) => service.source_urls?.length)?.source_urls?.[0];
      if (firstSource) {
        sourceChip.href = safeUrl(firstSource);
        sourceChip.innerHTML = `<span>Fonte: Comune di Verbania</span><span aria-hidden="true">↗</span>`;
      }
    }

    const navigationAlert = [...(state.data.notices || [])]
      .filter((notice) => /apertura\s+ss\.?\s*34/i.test(notice.title))
      .sort((a, b) => String(b.published_at || "").localeCompare(String(a.published_at || "")))[0];

    if (navigationAlert) {
      const summary = String(navigationAlert.summary || navigationAlert.body_text || "")
        .replace(/^NAVIGAZIONE LAGO MAGGIORE[\s\S]*?AVVISO AL PUBBLICO\s*n[°º]?\s*\d+\/\d+\s*/i, "")
        .trim();
      const shortSummary = summary.length > 420 ? `${summary.slice(0, 417).trimEnd()}…` : summary;

      alertContainer.innerHTML = `
        <div class="callout service-alert">
          <div class="callout-icon" aria-hidden="true">!</div>
          <div>
            <strong>Avviso ${escapeHtml(navigationAlert.source)}: ${escapeHtml(navigationAlert.title)}</strong>
            <p>${escapeHtml(shortSummary)}</p>
            <a href="${escapeHtml(safeUrl(navigationAlert.source_url))}" target="_blank" rel="noopener noreferrer">Leggi l’avviso ufficiale ↗</a>
          </div>
        </div>
      `;
    } else {
      alertContainer.innerHTML = "";
    }

    if (!services.length) {
      container.innerHTML = `<div class="empty-state"><strong>Nessun servizio via lago indicato.</strong><span>Consulta Navigazione Laghi per gli orari aggiornati.</span></div>`;
      return;
    }

    container.innerHTML = services
      .map((service) => {
        const sources = (service.source_urls || [])
          .map(
            (url, index) =>
              `<a href="${escapeHtml(safeUrl(url))}" target="_blank" rel="noopener noreferrer">Fonte ${index + 1} ↗</a>`
          )
          .join("");

        return `
          <article class="service-card">
            <div class="service-top">
              <span class="service-kind">${escapeHtml(KIND_LABELS[service.kind] || service.kind || "Servizio")}</span>
              <span class="service-times-label">${service.times?.length === 1 ? "1 corsa" : `${service.times?.length || 0} corse`}</span>
            </div>
            <div class="service-route">
              <span>${escapeHtml(service.from)}</span>
              <span class="arrow" aria-hidden="true">→</span>
              <span>${escapeHtml(service.to)}</span>
            </div>
            <div class="time-list">
              ${(service.times || []).map((time) => `<span class="time-chip">${escapeHtml(time)}</span>`).join("")}
            </div>
            ${service.notes ? `<p class="service-note">${escapeHtml(service.notes)}</p>` : ""}
            <div class="source-row">${sources || `<span class="service-note">Fonte: Comune di Verbania</span>`}</div>
          </article>
        `;
      })
      .join("");
  }

  function renderNotices() {
    if (!state.data) return;

    const container = $("#notice-list");
    const empty = $("#notice-empty");
    const all = [...(state.data.notices || [])].sort((a, b) =>
      String(b.published_at || "").localeCompare(String(a.published_at || ""))
    );
    const query = normalize(state.noticeQuery);
    const filtered = all.filter((notice) => {
      if (state.noticeFilter !== "tutti" && notice.category !== state.noticeFilter) return false;
      if (!query) return true;
      const haystack = normalize(
        [notice.title, notice.summary, notice.body_text, notice.source, ...(notice.tags || [])].join(" ")
      );
      const compactHaystack = haystack.replace(/[^a-z0-9]+/g, "");
      const compactQuery = query.replace(/[^a-z0-9]+/g, "");
      return haystack.includes(query) || (compactQuery && compactHaystack.includes(compactQuery));
    });

    $("#notice-count").textContent = `${filtered.length} ${filtered.length === 1 ? "avviso" : "avvisi"}`;
    empty.hidden = filtered.length > 0;

    if (!filtered.length) {
      container.innerHTML = "";
      return;
    }

    container.innerHTML = filtered
      .map((notice) => {
        const tags = (notice.tags || [])
          .slice(0, 4)
          .map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`)
          .join("");

        return `
          <article class="notice-card">
            <div class="notice-top">
              <span class="source-pill">${escapeHtml(notice.source)}</span>
              <span class="notice-date">${escapeHtml(formatTimestamp(notice.published_at))}</span>
            </div>
            <h3>${escapeHtml(notice.title)}</h3>
            <p class="notice-summary">${escapeHtml(notice.summary || notice.body_text || "")}</p>
            <div class="tag-list">${tags}</div>
            <div class="notice-actions">
              <a href="${escapeHtml(safeUrl(notice.source_url))}" target="_blank" rel="noopener noreferrer">Fonte ufficiale ↗</a>
              <button type="button" data-open-notice="${escapeHtml(notice.id)}">Leggi i dettagli</button>
            </div>
          </article>
        `;
      })
      .join("");
  }

  function renderTimetables() {
    if (!state.data) return;

    const container = $("#timetable-grid");
    const timetables = state.data.timetables || [];

    if (!timetables.length) {
      container.innerHTML = `<div class="empty-state"><strong>Nessun PDF disponibile.</strong><span>Apri la pagina orari di Navigazione Laghi.</span></div>`;
      return;
    }

    container.innerHTML = timetables
      .map(
        (timetable) => `
          <article class="timetable-card">
            <h3>${escapeHtml(timetable.route)}</h3>
            <p class="timetable-meta">
              ${escapeHtml(KIND_LABELS[timetable.kind] || timetable.kind || "Orario")}
              ${timetable.valid_from && timetable.valid_until
                ? ` · valido dal ${escapeHtml(formatDate(timetable.valid_from))} all’${escapeHtml(formatDate(timetable.valid_until))}`
                : ""}
            </p>
            <a class="pdf-button" href="${escapeHtml(safeUrl(timetable.pdf_url))}" target="_blank" rel="noopener noreferrer">
              <span>Apri il PDF ufficiale</span>
              <span aria-hidden="true">PDF ↗</span>
            </a>
            <div class="source-row">
              <a href="${escapeHtml(safeUrl(timetable.source_page))}" target="_blank" rel="noopener noreferrer">Pagina orari Navigazione Laghi ↗</a>
            </div>
          </article>
        `
      )
      .join("");
  }

  function renderSources() {
    const container = $("#sources-list");
    const sources = state.data?.meta?.sources || [];

    if (!sources.length) {
      container.innerHTML = "";
      return;
    }

    container.innerHTML = sources
      .map(
        (source) => `
          <article class="source-card">
            <strong>${escapeHtml(source.name)}</strong>
            <p>${escapeHtml(source.kind || "Fonte ufficiale")}${source.license ? ` · ${escapeHtml(source.license)}` : ""}</p>
            <a href="${escapeHtml(safeUrl(source.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.url)} ↗</a>
          </article>
        `
      )
      .join("");
  }

  function renderFreshness() {
    const meta = state.data.meta || {};
    const generated = formatTimestamp(meta.generated_at);

    const sync = $("#sync-line");
    sync.classList.remove("is-error");
    sync.innerHTML = `<span class="sync-dot"></span><span>Ultimo controllo: ${escapeHtml(generated)}</span>`;

    $("#footer-updated").textContent = `Ultimo controllo: ${generated}.`;
  }

  function openNotice(id) {
    if (!state.data) return;

    const notice = (state.data.notices || []).find((item) => item.id === id);
    if (!notice) return;

    const tags = (notice.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
    const services = (notice.services || [])
      .map(
        (service) =>
          `<li><strong>${escapeHtml(service.route)}</strong>: ${(service.times || []).map((time) => escapeHtml(time)).join(", ")}</li>`
      )
      .join("");
    const valid =
      notice.valid_from || notice.valid_until
        ? `<div class="dialog-section"><h3>Validità</h3><p>${escapeHtml(formatDateRange(notice.valid_from, notice.valid_until))}</p></div>`
        : "";
    const window =
      notice.closure_window?.start && notice.closure_window?.end
        ? `<div class="dialog-section"><h3>Finestra di chiusura</h3><div class="dialog-window">${escapeHtml(notice.closure_window.start)} → ${escapeHtml(notice.closure_window.end)}</div></div>`
        : "";
    const body = notice.body_text
      ? `<div class="dialog-section"><h3>Testo dell’avviso</h3><p>${escapeHtml(notice.body_text)}</p></div>`
      : "";

    openDialog(`
      <h2 id="detail-title">${escapeHtml(notice.title)}</h2>
      <div class="dialog-meta">
        <span>${escapeHtml(notice.source)}</span>
        <span>${escapeHtml(CATEGORY_LABELS[notice.category] || notice.category || "Avviso")}</span>
        <span>Pubblicato ${escapeHtml(formatTimestamp(notice.published_at))}</span>
      </div>
      ${notice.summary ? `<div class="dialog-section"><h3>In sintesi</h3><p>${escapeHtml(notice.summary)}</p></div>` : ""}
      ${body}
      ${window}
      ${valid}
      ${services ? `<div class="dialog-section"><h3>Servizi collegati</h3><ul>${services}</ul></div>` : ""}
      ${tags ? `<div class="dialog-section"><h3>Tag</h3><div class="tag-list">${tags}</div></div>` : ""}
      <a class="dialog-source" href="${escapeHtml(safeUrl(notice.source_url))}" target="_blank" rel="noopener noreferrer">Apri la fonte ufficiale ↗</a>
    `);
  }

  function openDay(date) {
    const day = state.days.get(date);
    if (!day) return;

    const context = currentNightContext();
    const closure = state.data.calendar.closure_window || {};
    const status = STATUS_LABELS[day.status] || day.status_label || "Stato";
    const isCurrent = date === context.key;
    const explanation = day.night_closed
      ? `La SS34 è chiusa nella notte tra ${dateLong.format(new Date(`${date}T12:00:00Z`))} e il giorno successivo, dalle ${closure.start || "21:00"} alle ${closure.end || "05:00"}.`
      : day.status === "APERTA"
        ? "Nessuna chiusura notturna prevista: la strada resta aperta. La notte tra sabato e domenica è sempre esclusa dalle chiusure."
        : "Lo stato di questa notte non è definito dal calendario. Verifica la fonte ufficiale prima di partire.";

    openDialog(`
      <h2 id="detail-title">Notte di ${escapeHtml(dateLong.format(new Date(`${date}T12:00:00Z`)))}</h2>
      <div class="dialog-meta">
        <span class="status-badge status-${statusTone(day)}">${escapeHtml(status)}</span>
        ${isCurrent ? "<span>Notte corrente</span>" : `<span>${escapeHtml(datePlain.format(new Date(`${date}T12:00:00Z`)))}</span>`}
      </div>
      <div class="dialog-section">
        <h3>Stato della strada</h3>
        <p>${escapeHtml(explanation)}</p>
      </div>
      <div class="dialog-section">
        <h3>${day.night_closed ? "Chiusura prevista" : "Finestra notturna"}</h3>
        <div class="dialog-window">${escapeHtml(day.night_closed ? `${closure.start || "21:00"} → ${closure.end || "05:00"}` : "Nessuna chiusura")}</div>
      </div>
      <div class="dialog-section">
        <h3>Nota</h3>
        <p>La notte indicata è quella tra il giorno selezionato e il successivo. Dopo mezzanotte fa fede il giorno precedente.</p>
      </div>
      <a class="dialog-source" href="${escapeHtml(safeUrl(state.data.calendar.source_url))}" target="_blank" rel="noopener noreferrer">Apri la fonte ufficiale ↗</a>
    `);
  }

  function openDialog(html) {
    const dialog = $("#detail-dialog");
    const content = $("#detail-content");
    content.innerHTML = html;

    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }

    document.body.classList.add("modal-open");
    content.scrollTop = 0;
  }

  function setupDialog() {
    const dialog = $("#detail-dialog");
    if (!dialog) return;

    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });

    dialog.addEventListener("close", () => {
      document.body.classList.remove("modal-open");
    });
  }

  function setupNavigation() {
    const toggle = $("#menu-toggle");
    const nav = $("#main-nav");

    toggle?.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Chiudi il menu" : "Apri il menu");
    });

    $$("#main-nav a").forEach((link) => {
      link.addEventListener("click", () => {
        nav.classList.remove("is-open");
        toggle?.setAttribute("aria-expanded", "false");
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && nav.classList.contains("is-open")) {
        nav.classList.remove("is-open");
        toggle?.setAttribute("aria-expanded", "false");
        toggle?.focus();
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 820) {
        nav.classList.remove("is-open");
        toggle?.setAttribute("aria-expanded", "false");
      }
    });

    if ("IntersectionObserver" in window) {
      const links = new Map(
        $$("#main-nav a")
          .map((link) => {
            const href = link.getAttribute("href");
            if (!href?.startsWith("#")) return null;
            const target = $(href);
            return target ? [target, link] : null;
          })
          .filter(Boolean)
      );

      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            links.forEach((link) => {
              link.classList.remove("is-active");
              link.removeAttribute("aria-current");
            });
            const active = links.get(entry.target);
            if (active) {
              active.classList.add("is-active");
              active.setAttribute("aria-current", "location");
            }
          });
        },
        { rootMargin: "-25% 0px -62% 0px", threshold: 0 }
      );

      links.forEach((_, section) => observer.observe(section));
    }
  }

  function setupNoticeControls() {
    const search = $("#notice-search");
    const filters = $("#notice-filters");
    const list = $("#notice-list");

    search?.addEventListener("input", (event) => {
      state.noticeQuery = event.target.value.trim();
      renderNotices();
    });

    filters?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-filter]");
      if (!button) return;
      state.noticeFilter = button.dataset.filter;
      $$(".filter", filters).forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderNotices();
    });

    list?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-open-notice]");
      if (button) openNotice(button.dataset.openNotice);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
      const active = document.activeElement;
      if (active && ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName)) return;
      if (!search) return;
      event.preventDefault();
      search.focus();
      $("#avvisi")?.scrollIntoView({ block: "start" });
    });
  }

  function setupServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    const localHost = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
    if (location.protocol !== "https:" && !localHost) return;

    window.addEventListener("load", () => {
      navigator.serviceWorker.register("sw.js").catch((error) => {
        console.warn("Service worker non registrato", error);
      });
    });
  }

  function renderLoadError() {
    const isFile = window.location.protocol === "file:";
    const hint = isFile
      ? "Stai aprendo il file direttamente: il browser blocca data.json. Avvia un server locale e usa http://localhost:8000."
      : "Controlla la connessione e riprova. In alternativa apri la fonte ufficiale.";
    const card = $("#status-card");
    card.setAttribute("aria-busy", "false");
    card.innerHTML = `
      <div class="status-topline">
        <span class="status-kicker">Stato SS34</span>
        <span class="status-source">Dati non disponibili</span>
      </div>
      <div class="status-main">
        <span class="status-badge status-unknown">Offline</span>
        <h2>Impossibile caricare i dati</h2>
        <p>${hint}</p>
      </div>
      <div class="status-window">
        <span>Finestra notturna</span>
        <strong>21:00 → 05:00</strong>
      </div>
      <a class="status-link" href="https://www.comune.verbania.it/Novita/Comunicati/S.S.-34-a-Cannobio-il-calendario-delle-aperture-e-delle-chiusure-notturne" target="_blank" rel="noopener noreferrer">Apri il calendario ufficiale</a>
    `;

    $("#sync-line").classList.add("is-error");
    $("#sync-line").innerHTML = `<span class="sync-dot"></span><span>${hint}</span>`;
    $("#data-error").hidden = false;
    $("#night-grid").innerHTML = `<div class="empty-state"><strong>Calendario non disponibile.</strong><span>Usa il link alla fonte ufficiale qui sopra.</span></div>`;
    $("#calendar-grid").innerHTML = "";
    $("#services-grid").innerHTML = "";
    $("#notice-list").innerHTML = "";
    $("#notice-empty").hidden = true;
    $("#timetable-grid").innerHTML = "";
    $("#sources-list").innerHTML = "";
    $("#footer-updated").textContent = "Dati non disponibili.";
  }

  function formatDate(isoDate) {
    if (!isoDate) return "";
    return datePlain.format(new Date(`${isoDate}T12:00:00Z`));
  }

  function formatDateRange(from, to) {
    if (from && to) return `Dal ${formatDate(from)} al ${formatDate(to)}.`;
    if (from) return `Dal ${formatDate(from)}.`;
    if (to) return `Fino al ${formatDate(to)}.`;
    return "";
  }

  function formatDay(value) {
    if (!value) return "";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "" : dateNumeric.format(parsed);
  }

  function formatTimestamp(value) {
    if (!value) return "data non indicata";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "data non indicata";
    const time = timeShort.format(parsed);
    return time === "00:00" ? datePlain.format(parsed) : `${datePlain.format(parsed)}, ${time}`;
  }

  function statusClass(status) {
    if (status === "APERTA") return "aparta";
    if (status === "CHIUSA") return "chiusa";
    if (status === "CHIUSURA_NOTTURNA") return "notturna";
    return "non-definita";
  }

  function shortStatus(status) {
    if (status === "APERTA") return "Aperta";
    if (status === "CHIUSA") return "Chiusa";
    if (status === "CHIUSURA_NOTTURNA") return "Notturna";
    return "N.D.";
  }

  function normalize(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function safeUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : "#";
    } catch {
      return "#";
    }
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;"
        })[character]
    );
  }
})();
