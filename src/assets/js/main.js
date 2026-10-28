/* M-AUTO: прогрессивное улучшение. Без этого файла страница и форма тоже работают. */
(function () {
  "use strict";

  var doc = document;
  var root = doc.documentElement;
  root.classList.add("js");

  var env = root.getAttribute("data-env") || "prod";
  var metrikaId = root.getAttribute("data-ym") || "";
  var reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  /* ---------------------------------------------------------- цели Метрики */

  function goal(name, params) {
    try {
      if (metrikaId && typeof window.ym === "function") {
        window.ym(Number(metrikaId), "reachGoal", name, params || {});
      } else if (env === "preview" && window.console) {
        console.info("[цель Метрики]", name, params || {});
      }
    } catch (e) { /* аналитика не должна ломать страницу */ }
  }

  /* ---------------------------------------------------------- первое касание (UTM) */

  var TOUCH_KEY = "mauto_touch";
  var TOUCH_TTL = 30 * 24 * 60 * 60 * 1000;
  var UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "yclid"];

  function readStored() {
    try { return JSON.parse(window.localStorage.getItem(TOUCH_KEY) || "null"); } catch (e) { return null; }
  }

  function writeStored(value) {
    try { window.localStorage.setItem(TOUCH_KEY, JSON.stringify(value)); } catch (e) { /* приватный режим */ }
  }

  function firstTouch() {
    var params;
    try { params = new URLSearchParams(window.location.search); } catch (e) { params = null; }
    var current = { ts: Date.now(), referrer: (doc.referrer || "").slice(0, 500), landing_url: window.location.href.slice(0, 500) };
    var paid = false;
    UTM_KEYS.forEach(function (key) {
      var v = params ? params.get(key) : "";
      current[key] = v ? v.slice(0, 200) : "";
      if (v) paid = true;
    });
    var saved = readStored();
    var fresh = !!(saved && saved.ts && Date.now() - saved.ts < TOUCH_TTL);
    var savedPaid = fresh && UTM_KEYS.some(function (key) { return !!saved[key]; });
    // первое касание храним 30 дней; рекламный переход важнее пустого
    if (!fresh || (paid && !savedPaid)) {
      writeStored(current);
      return current;
    }
    return saved;
  }

  var touch = firstTouch();

  /* ---------------------------------------------------------- переход к форме */

  var formSection = doc.getElementById("form");
  var nameInput = doc.getElementById("f-name");
  var donePanel = doc.getElementById("form-done");
  var autoFocus = false; // фокус от кнопки CTA не считается началом заполнения

  function goToForm() {
    if (!formSection) return false;
    var target = donePanel && !donePanel.hidden ? donePanel : nameInput;
    if (target) {
      // фокус синхронно в обработчике клика: так iOS открывает клавиатуру
      autoFocus = true;
      try { target.focus({ preventScroll: true }); } catch (e) { target.focus(); }
      autoFocus = false;
    }
    formSection.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    return true;
  }

  doc.addEventListener("click", function (e) {
    var t = e.target;
    if (!t || !t.closest) return;

    var cta = t.closest("[data-cta]");
    if (cta) {
      goal("cta_click", { where: cta.getAttribute("data-cta") });
      if (cta.tagName === "A" && goToForm()) e.preventDefault();
    }

    var tracked = t.closest("[data-goal]");
    if (tracked) {
      goal(tracked.getAttribute("data-goal"), { where: tracked.getAttribute("data-where") || "" });
      // в превью ссылки-заглушки «#» никуда не ведут
      if (tracked.getAttribute("href") === "#") e.preventDefault();
    }
  });

  /* ---------------------------------------------------------- липкая кнопка */

  var sticky = doc.getElementById("sticky-cta");
  var heroCta = doc.querySelector(".hero__cta");
  var stickyState = { hero: true, form: false, done: false };

  function updateSticky() {
    if (!sticky) return;
    var show = !stickyState.hero && !stickyState.form && !stickyState.done;
    sticky.classList.toggle("is-visible", show);
  }

  if (sticky && heroCta && formSection && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.target === heroCta) stickyState.hero = entry.isIntersecting;
        else stickyState.form = entry.isIntersecting;
      });
      updateSticky();
    });
    io.observe(heroCta);
    io.observe(formSection);
  }

  /* ---------------------------------------------------------- форма */

  var form = doc.getElementById("lead-form");
  if (form) initForm(form);

  function initForm(form) {
    form.noValidate = true;

    var mode = form.getAttribute("data-mode") || "live";
    var byId = function (id) { return doc.getElementById(id); };
    var f = {
      name: byId("f-name"),
      car: byId("f-car"),
      yearFrom: byId("f-year-from"),
      yearTo: byId("f-year-to"),
      milFrom: byId("f-mileage-from"),
      milTo: byId("f-mileage-to"),
      contact: byId("f-contact"),
      consent: byId("f-consent")
    };
    var groups = {
      name: [f.name],
      car: [f.car],
      years: [f.yearFrom, f.yearTo],
      mileage: [f.milFrom, f.milTo],
      contact: [f.contact],
      consent: f.consent ? [f.consent] : []
    };
    var errors = {
      name: byId("f-name-error"),
      car: byId("f-car-error"),
      years: byId("f-years-error"),
      mileage: byId("f-mileage-error"),
      contact: byId("f-contact-error"),
      consent: byId("f-consent-error")
    };
    var ORDER = ["name", "car", "years", "mileage", "contact", "consent"];
    var status = byId("form-status");
    var alertBox = byId("form-alert");
    var button = form.querySelector('button[type="submit"]');
    var buttonText = button ? button.textContent : "";
    var contactLabel = byId("f-contact-label");
    var loadTs = Date.now();
    var dirty = {};
    var started = false;
    var sending = false;
    var sent = false;

    // скрытые поля заполняем сразу: пригодятся и при обычной отправке
    UTM_KEYS.concat(["referrer", "landing_url"]).forEach(function (key) {
      if (form.elements[key]) form.elements[key].value = touch[key] || "";
    });
    if (form.elements.form_ts) form.elements.form_ts.value = String(loadTs);

    /* --- разбор значений (те же правила в api/send.php) --- */

    function clean(input) {
      return input.value.replace(/\s+/g, " ").trim();
    }

    function digitsOf(value) {
      return String(value || "").replace(/\D/g, "");
    }

    function parsePhone(value) {
      var v = String(value).trim();
      if (!/^[+\d\s().-]+$/.test(v)) return null;
      var d = digitsOf(v);
      if (v.charAt(0) === "+") {
        if (d.length === 11 && d.charAt(0) === "7") return "+" + d;
        return d.length >= 10 && d.length <= 15 ? "+" + d : null;
      }
      if (d.length === 11 && (d.charAt(0) === "7" || d.charAt(0) === "8")) return "+7" + d.slice(1);
      if (d.length === 10 && d.charAt(0) === "9") return "+7" + d;
      return null;
    }

    var WA_LINK = /^(?:https?:\/\/)?(?:wa\.me\/|api\.whatsapp\.com\/send\/?\?phone=)\+?(\d{10,15})\/?$/i;
    var TG_LINK = /^(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/@?([a-z][a-z0-9_]{3,31})\/?$/i;
    var TG_USER = /^@?([a-z][a-z0-9_]{3,31})$/i;

    function parseContact(value) {
      var v = String(value).trim();
      var m = v.match(WA_LINK);
      if (m) {
        var wa = parsePhone(m[1]);
        return wa ? { type: "phone", value: wa } : null;
      }
      var phone = parsePhone(v);
      if (phone) return { type: "phone", value: phone };
      m = v.match(TG_LINK) || v.match(TG_USER);
      return m ? { type: "telegram", value: m[1] } : null;
    }

    function method() {
      var r = form.querySelector('input[name="contact_method"]:checked');
      return r ? r.value : "messenger";
    }

    /* --- проверки: строка ошибки или "" --- */

    var rules = {
      name: function () {
        var v = clean(f.name);
        if (!v) return "Напишите, как к вам обращаться";
        if (v.length < 2) return "Имя слишком короткое: нужно хотя бы 2 символа";
        if (v.length > 60) return "Имя слишком длинное: не больше 60 символов";
        return "";
      },
      car: function () {
        var v = clean(f.car);
        if (!v) return "Напишите марку и модель, например Volkswagen Tiguan";
        if (v.length < 2) return "Слишком коротко: напишите марку и модель";
        if (v.length > 80) return "Слишком длинно: не больше 80 символов";
        return "";
      },
      years: function () {
        var a = f.yearFrom.value;
        var b = f.yearTo.value;
        if (!a && !b) return { msg: "Выберите год выпуска «от» и «до»", bad: [f.yearFrom, f.yearTo] };
        if (!a) return { msg: "Выберите год выпуска «от»", bad: [f.yearFrom] };
        if (!b) return { msg: "Выберите год выпуска «до»", bad: [f.yearTo] };
        if (Number(b) < Number(a)) return { msg: "Год «до» не может быть раньше года «от»", bad: [f.yearTo] };
        return "";
      },
      mileage: function () {
        var a = digitsOf(f.milFrom.value);
        var b = digitsOf(f.milTo.value);
        if (a && b && Number(b) < Number(a)) return { msg: "Пробег «до» не может быть меньше пробега «от»", bad: [f.milTo] };
        return "";
      },
      contact: function () {
        var v = f.contact.value.trim();
        var call = method() === "call";
        if (!v) return call ? "Укажите телефон для звонка" : "Укажите телефон или ник в Telegram";
        var parsed = parseContact(v);
        if (call && (!parsed || parsed.type !== "phone")) return "Для звонка нужен номер телефона, например +7 999 123-45-67";
        if (!parsed) return "Не похоже на телефон или ник Telegram. Пример: +7 999 123-45-67 или @username";
        return "";
      },
      consent: function () {
        if (!f.consent || f.consent.checked) return "";
        return "Поставьте галочку: без согласия мы не можем принять заявку";
      }
    };

    function show(key, msg, bad) {
      if (errors[key]) errors[key].textContent = msg;
      groups[key].forEach(function (input) {
        if (bad.indexOf(input) > -1) input.setAttribute("aria-invalid", "true");
        else input.removeAttribute("aria-invalid");
      });
    }

    function validate(key) {
      var r = rules[key]();
      var msg = typeof r === "string" ? r : r.msg;
      var bad = typeof r === "string" ? (r ? groups[key] : []) : r.bad;
      show(key, msg, bad);
      return msg ? bad[0] : null;
    }

    function keyOf(input) {
      for (var i = 0; i < ORDER.length; i++) {
        if (groups[ORDER[i]].indexOf(input) > -1) return ORDER[i];
      }
      return null;
    }

    function hasError(key) {
      return !!(errors[key] && errors[key].textContent);
    }

    /* --- пробег: пробелы между разрядами --- */

    function formatMileage(input) {
      var caret = input.selectionStart || 0;
      var before = digitsOf(input.value.slice(0, caret)).length;
      var digits = digitsOf(input.value).replace(/^0+(?=\d)/, "").slice(0, 7);
      var out = digits.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
      if (out === input.value) return;
      input.value = out;
      var pos = 0;
      var seen = 0;
      while (pos < out.length && seen < before) {
        if (/\d/.test(out.charAt(pos))) seen++;
        pos++;
      }
      try { input.setSelectionRange(pos, pos); } catch (e) { /* не все типы полей */ }
    }

    /* --- способ связи меняет подпись поля --- */

    var CONTACT_MODES = {
      messenger: { label: "Telegram или WhatsApp для связи", placeholder: "+7 999 123-45-67 или @username", inputmode: "text" },
      call: { label: "Телефон для звонка", placeholder: "+7 999 123-45-67", inputmode: "tel" }
    };

    function applyMethod() {
      var m = CONTACT_MODES[method()];
      if (contactLabel) contactLabel.textContent = m.label;
      f.contact.placeholder = m.placeholder;
      f.contact.setAttribute("inputmode", m.inputmode);
      // ошибку показываем, только если поле уже заполняли
      if (dirty.contact || hasError("contact")) validate("contact");
    }

    /* --- события --- */

    function markStarted() {
      if (started) return;
      started = true;
      goal("form_start");
    }

    form.addEventListener("focusin", function () {
      if (!autoFocus) markStarted();
    });

    form.addEventListener("input", function (e) {
      markStarted();
      var t = e.target;
      if (t === f.milFrom || t === f.milTo) formatMileage(t);
      var key = keyOf(t);
      if (!key) return;
      dirty[key] = true;
      if (hasError(key)) validate(key); // ошибка уходит, как только поле исправлено
    });

    form.addEventListener("focusout", function (e) {
      var key = keyOf(e.target);
      if (!key || key === "years" || key === "consent") return;
      if (dirty[key]) validate(key);
    });

    form.addEventListener("change", function (e) {
      markStarted();
      var t = e.target;
      if (t.name === "contact_method") return applyMethod();
      var key = keyOf(t);
      if (key === "years") {
        dirty.years = true;
        if ((f.yearFrom.value && f.yearTo.value) || hasError("years")) validate("years");
      }
      if (key === "consent" && hasError("consent")) validate("consent");
    });

    // Enter в полях переводит к следующему, а не отправляет форму раньше времени
    var FLOW = [f.name, f.car, f.yearFrom, f.yearTo, f.milFrom, f.milTo, f.contact];
    form.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" || e.isComposing) return;
      var t = e.target;
      var i = FLOW.indexOf(t);
      if (i < 0 || t === f.contact) return;
      e.preventDefault();
      if (FLOW[i + 1]) FLOW[i + 1].focus();
    });

    /* --- отправка --- */

    function payload() {
      var data = {
        name: clean(f.name),
        car: clean(f.car),
        year_from: f.yearFrom.value,
        year_to: f.yearTo.value,
        mileage_from: digitsOf(f.milFrom.value),
        mileage_to: digitsOf(f.milTo.value),
        contact: f.contact.value.trim(),
        contact_method: method(),
        consent: f.consent ? (f.consent.checked ? "1" : "") : "1",
        form_ts: String(loadTs),
        form_elapsed: String(Date.now() - loadTs),
        company_site: form.elements.company_site ? form.elements.company_site.value : ""
      };
      UTM_KEYS.concat(["referrer", "landing_url"]).forEach(function (key) {
        data[key] = touch[key] || "";
      });
      return data;
    }

    function setSending(on) {
      sending = on;
      if (button) {
        button.disabled = on;
        button.textContent = on ? "Отправляем…" : buttonText;
      }
      form.setAttribute("aria-busy", on ? "true" : "false");
      if (on && status) status.textContent = "Отправляем заявку…";
    }

    function success() {
      sent = true;
      setSending(false);
      if (status) status.textContent = "";
      form.hidden = true;
      if (donePanel) {
        donePanel.hidden = false;
        donePanel.focus();
      }
      stickyState.done = true;
      updateSticky();
      goal("lead_success");
    }

    function failure() {
      setSending(false);
      if (status) status.textContent = "";
      if (alertBox) alertBox.hidden = false;
    }

    var SERVER_FIELDS = {
      name: "name", car: "car", year_from: "years", year_to: "years",
      mileage_from: "mileage", mileage_to: "mileage", contact: "contact", consent: "consent"
    };

    function serverErrors(list) {
      setSending(false);
      var first = null;
      ORDER.forEach(function (key) { show(key, "", []); });
      Object.keys(list).forEach(function (field) {
        var key = SERVER_FIELDS[field];
        if (!key) return;
        var input = field === "year_to" ? f.yearTo : field === "mileage_to" ? f.milTo : groups[key][0];
        show(key, String(list[field]), input ? [input] : []);
      });
      ORDER.some(function (key) {
        if (!hasError(key)) return false;
        first = groups[key].filter(function (i) { return i.getAttribute("aria-invalid") === "true"; })[0] || groups[key][0];
        return true;
      });
      if (status) status.textContent = "Заявка не отправлена: проверьте отмеченные поля";
      if (first) first.focus();
    }

    function send(data) {
      setSending(true);
      if (mode === "demo") {
        if (window.console) console.info("[демо] заявка никуда не отправлена. Данные:", data);
        window.setTimeout(success, 700);
        return;
      }
      var ctrl = "AbortController" in window ? new AbortController() : null;
      var timer = window.setTimeout(function () { if (ctrl) ctrl.abort(); }, 15000);
      window.fetch(form.getAttribute("action"), {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(data),
        credentials: "same-origin",
        signal: ctrl ? ctrl.signal : undefined
      }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          return { status: res.status, body: body || {} };
        });
      }).then(function (r) {
        window.clearTimeout(timer);
        if (r.status === 200 && r.body.ok) return success();
        if (r.status === 422 && r.body.errors) return serverErrors(r.body.errors);
        failure();
      }).catch(function () {
        window.clearTimeout(timer);
        failure();
      });
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (sending || sent) return;
      if (alertBox) alertBox.hidden = true;
      var first = null;
      ORDER.forEach(function (key) {
        var bad = validate(key);
        if (bad && !first) first = bad;
      });
      if (first) {
        if (status) status.textContent = "Заявка не отправлена: проверьте отмеченные поля";
        first.focus();
        return;
      }
      if (!window.fetch && mode !== "demo") {
        form.submit(); // очень старый браузер: обычная отправка
        return;
      }
      send(payload());
    });
  }
})();
